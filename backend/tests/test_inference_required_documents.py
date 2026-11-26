"""Required document matches gate dispatch, not generated-answer correctness."""
import hashlib
import json
import pytest
from sqlalchemy import select
from nexus.db import InferenceCall, InferenceBudget, WorkspaceAsset, KnowledgeDocument
from conftest import auth
from nexus.documents import index_document
from nexus.security import digest
from test_inference import setup
from test_inference_documents import upload, engineer


def assert_no_admission(ctx, sent):
    assert not sent
    with ctx['db']() as db:
        assert db.scalar(select(InferenceCall)) is None
        assert db.scalar(select(InferenceBudget)) is None


@pytest.mark.parametrize('query', ['Synthetic question', 'متى تبدأ الصيانة؟'])
def test_no_document_match_stops_before_provider_or_reservation(ctx, monkeypatch, query):
    headers, body, sent = setup(ctx, monkeypatch)
    response = ctx['client'].post('/v1/inference', headers=headers, json={
        **body, 'query':query, 'retrieve_evidence': True, 'require_document_evidence': True,
    })
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DOCUMENT_EVIDENCE_REQUIRED'
    assert_no_admission(ctx, sent)


@pytest.mark.parametrize('mutation',['deleted','production','foreign'])
def test_out_of_scope_or_deleted_source_cannot_admit_request(ctx, monkeypatch, mutation):
    headers, body, sent = setup(ctx, monkeypatch)
    if mutation == 'foreign':
        other_headers, _ = auth(ctx,org='other')
        upload(ctx,other_headers)
        key = headers['Idempotency-Key']
        headers, _ = auth(ctx)
        headers['Idempotency-Key'] = key
    elif mutation == 'production':
        with ctx['db'].begin() as db:
            text = 'Synthetic maintenance interval is 45 minutes.'
            model = db.get(WorkspaceAsset,body['model_id'])
            # Create a correctly scoped source rather than mutating a parent
            # key that is protected by document/chunk foreign keys.
            from nexus.db import User
            owner = db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
            doc = KnowledgeDocument(org_id=model.org_id,env='production',author_id=owner.id,
                title='Production only',filename='production.txt',content=text,
                content_hash=digest(text),byte_count=len(text),allowed_roles=[],
                idem_key='production-required-doc-0001',request_digest='synthetic')
            db.add(doc); db.flush(); index_document(db,doc)
    else:
        document = upload(ctx,headers)
        with ctx['db'].begin() as db:
            db.get(KnowledgeDocument,document['id']).status = 'deleted'
    response = ctx['client'].post('/v1/inference',headers=headers,json={
        **body,'query':'maintenance interval','retrieve_evidence':True,'require_document_evidence':True})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DOCUMENT_EVIDENCE_REQUIRED'
    assert_no_admission(ctx,sent)


@pytest.mark.parametrize('has_source',[False,True])
def test_local_ollama_is_not_contacted_until_an_authorized_document_matches(ctx, has_source):
    from test_ollama import setup as local_setup
    headers, body, sent = local_setup(ctx)
    if has_source: upload(ctx,headers)
    response = ctx['client'].post('/v1/inference',headers=headers,json={
        **body,'query':'maintenance interval','retrieve_evidence':True,'require_document_evidence':True})
    if has_source:
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'completed'
        assert response.json()['result']['citations'][0]['source_kind'] == 'document_library'
        assert [request.url.path for request in sent] == ['/api/show','/api/chat']
    else:
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'DOCUMENT_EVIDENCE_REQUIRED'
        assert_no_admission(ctx,sent)


def test_required_documents_cannot_be_used_with_retrieval_off(ctx, monkeypatch):
    headers, body, sent = setup(ctx, monkeypatch)
    response = ctx['client'].post('/v1/inference', headers=headers, json={
        **body, 'require_document_evidence': True,
    })
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DOCUMENT_RETRIEVAL_REQUIRED'
    assert_no_admission(ctx, sent)


def test_legacy_design_match_does_not_satisfy_required_document_mode(ctx, monkeypatch):
    headers, body, sent = setup(ctx, monkeypatch)
    with ctx['db'].begin() as db:
        db.add(WorkspaceAsset(org_id='northstar', kind='knowledge', name='Design source',
            author_id='test', config={'content':'Synthetic question legacy marker',
            'source':'Synthetic design', 'language':'English','chunk_size':700}))
    response = ctx['client'].post('/v1/inference', headers=headers, json={
        **body, 'retrieve_evidence': True, 'require_document_evidence': True,
    })
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DOCUMENT_EVIDENCE_REQUIRED'
    assert_no_admission(ctx, sent)


def test_private_document_is_not_a_match_for_another_reader(ctx, monkeypatch):
    headers, body, sent = setup(ctx, monkeypatch)
    upload(ctx, headers)
    headers = engineer(ctx)
    response = ctx['client'].post('/v1/inference', headers=headers, json={
        **body, 'query':'maintenance interval', 'retrieve_evidence': True,
        'require_document_evidence': True,
    })
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DOCUMENT_EVIDENCE_REQUIRED'
    assert 'Synthetic maintenance evidence' not in response.text
    assert_no_admission(ctx, sent)


def test_matching_document_dispatches_once_and_mode_changes_conflict(ctx, monkeypatch):
    headers, body, sent = setup(ctx, monkeypatch)
    document = upload(ctx, headers)
    body = {**body, 'query':'maintenance interval', 'retrieve_evidence':True,
            'require_document_evidence':True}
    first = ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert first.status_code == 200, first.text
    assert first.json()['result']['citations'][0]['document_id'] == document['id']
    assert ctx['client'].post('/v1/inference',headers=headers,json=body).json()['id'] == first.json()['id']
    conflict = ctx['client'].post('/v1/inference',headers=headers,json={**body,'require_document_evidence':False})
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert len(sent) == 1


@pytest.mark.parametrize('explicit_false', [False, True])
def test_preexisting_request_fingerprint_still_replays_without_dispatch(ctx, monkeypatch, explicit_false):
    headers, body, sent = setup(ctx, monkeypatch)
    result = ctx['client'].post('/v1/inference',headers=headers,json=body).json()
    # Reconstruct the exact pre-feature fingerprint, including existing defaults.
    with ctx['db'].begin() as db:
        row = db.get(InferenceCall,result['id'])
        old_body = {'author':row.author_id, 'retrieve_evidence':False, **body}
        row.request_hash = hashlib.sha256(json.dumps(old_body,sort_keys=True).encode()).hexdigest()
    if explicit_false: body = {**body,'require_document_evidence':False}
    replay = ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['id'] == result['id'] and len(sent) == 1


def test_missing_source_can_be_added_and_original_unadmitted_intent_retried(ctx, monkeypatch):
    headers, body, sent = setup(ctx, monkeypatch)
    body = {**body,'query':'maintenance interval','retrieve_evidence':True,
            'require_document_evidence':True}
    response = ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code == 422
    assert_no_admission(ctx,sent)
    upload(ctx,headers)
    result = ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert result.status_code == 200 and result.json()['status'] == 'completed'
    assert len(sent) == 1
