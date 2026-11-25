"""Document-library grounding and current source access on inference delivery."""
import base64
from copy import deepcopy
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from conftest import auth, assign_staging
from nexus.db import User, KnowledgeDocument, InferenceCall, InferenceBudget, WorkspaceAsset
from nexus.documents import index_document
from nexus.security import digest

from test_inference import setup


CONTENT = 'Maintenance source document-only-marker-7421: the synthetic maintenance interval is 45 minutes.'


def upload(ctx, headers, content=CONTENT, key='inference-document-source-0001', roles=None):
    result = ctx['client'].post('/v1/documents', headers={**headers, 'Idempotency-Key': key}, json={
        'title': 'Synthetic maintenance evidence', 'filename': 'synthetic-maintenance.txt',
        'language': 'English', 'allowed_roles': roles or [],
        'content_base64': base64.b64encode(content.encode()).decode(),
    })
    assert result.status_code == 201, result.text
    return result.json()


def test_indexed_library_evidence_reaches_selected_model(ctx, monkeypatch):
    headers, body, sent = setup(ctx, monkeypatch)
    document = upload(ctx, headers)
    result = ctx['client'].post('/v1/inference', headers=headers, json={
        **body, 'query': 'maintenance interval', 'retrieve_evidence': True,
    })
    assert result.status_code == 200, result.text
    assert b'document-only-marker-7421' in sent[0].content
    citations = result.json()['result']['citations']
    assert citations[0]['document_id'] == document['id']
    assert citations[0]['document_version'] == document['version']


def engineer(ctx):
    with ctx['db'].begin() as db:
        user = User(org_id='northstar', role='engineer', name='Synthetic reviewer', email='doc-engineer@synthetic.invalid')
        db.add(user); db.flush(); assign_staging(db, user)
    headers=auth(ctx, 'engineer')[0]
    headers['Idempotency-Key']='document-actor-inference-0001'
    return headers


def grounded(ctx, monkeypatch, handler=None):
    owner, body, sent = setup(ctx, monkeypatch, handler)
    # These tests exercise DB-backed source changes, not the provider deadline.
    # Keep filesystem scheduling from turning a valid mocked completion unknown.
    with ctx['db'].begin() as db:
        model=db.get(WorkspaceAsset,body['model_id'])
        model.config={**model.config,'timeout_ms':120000}
    doc = upload(ctx, owner, roles=['engineer'])
    headers = engineer(ctx)
    body = {**body, 'query': 'maintenance interval', 'retrieve_evidence': True}
    return headers, body, sent, doc


def test_document_opt_out_never_sends_library_text(ctx, monkeypatch):
    headers, body, sent, _ = grounded(ctx, monkeypatch)
    result = ctx['client'].post('/v1/inference', headers=headers, json={**body, 'retrieve_evidence': False})
    assert result.status_code == 200 and result.json()['result']['citations'] == []
    assert b'document-only-marker-7421' not in sent[0].content


def test_library_is_preferred_but_legacy_sources_still_work_without_a_document_match(ctx, monkeypatch):
    headers, body, sent, _ = grounded(ctx, monkeypatch)
    with ctx['db'].begin() as db:
        db.add(WorkspaceAsset(org_id='northstar', kind='knowledge', name='Legacy design', author_id='test',
                              config={'content':'Legacy-only-marker maintenance interval legacyneedle',
                                      'source':'Synthetic design', 'language':'English','chunk_size':700}))
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).status_code == 200
    assert b'document-only-marker-7421' in sent[0].content and b'Legacy-only-marker' not in sent[0].content
    headers['Idempotency-Key'] = 'inference-legacy-fallback-0001'
    result = ctx['client'].post('/v1/inference', headers=headers, json={**body,'query':'legacyneedle'})
    assert result.status_code == 200 and b'Legacy-only-marker' in sent[1].content
    assert 'asset_id' in result.json()['result']['citations'][0]


def test_acl_workspace_and_environment_filter_sources_before_provider_dispatch(ctx, monkeypatch):
    headers, body, sent = setup(ctx, monkeypatch)
    public = upload(ctx, headers, roles=['engineer'])
    upload(ctx, headers, content='maintenance private-neighbor-marker-7421',key='private-document-neighbor-0001')
    other, _ = auth(ctx,org='other')
    upload(ctx, other, content='maintenance foreign-workspace-marker-7421',key='foreign-document-source-0001')
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
        text='maintenance production-only-marker-7421'
        doc=KnowledgeDocument(org_id='northstar',env='production',title='Production only',filename='production.txt',
            author_id=owner.id,content=text,content_hash=digest(text),byte_count=len(text),
            allowed_roles=['engineer'],idem_key='production-document-0001',request_digest='synthetic')
        db.add(doc);db.flush();index_document(db,doc)
    headers = engineer(ctx)
    result = ctx['client'].post('/v1/inference', headers=headers, json={**body,'query':'maintenance','retrieve_evidence':True})
    assert result.status_code == 200, result.text
    assert {c['document_id'] for c in result.json()['result']['citations']} == {public['id']}
    assert all(marker not in sent[0].content for marker in (
        b'private-neighbor-marker',b'foreign-workspace-marker',b'production-only-marker'))


@pytest.mark.parametrize('mutation',['revoke','delete','replace'])
def test_source_changes_withhold_entire_answer_on_every_read_without_changing_usage(ctx, monkeypatch, mutation):
    headers, body, sent, doc = grounded(ctx, monkeypatch)
    call = ctx['client'].post('/v1/inference', headers=headers, json=body).json()
    assert call['status']=='completed' and call['result']['citations']
    with ctx['db'].begin() as db:
        source = db.get(KnowledgeDocument, doc['id'])
        if mutation=='revoke':source.allowed_roles=[]
        elif mutation=='delete':source.status='deleted'
        else:source.version+=1
    values = [
        ctx['client'].post('/v1/inference',headers=headers,json=body).json(),
        ctx['client'].post('/v1/inference/recover',headers=headers,json={'key':headers['Idempotency-Key']}).json(),
        ctx['client'].get('/v1/runtime').json()['calls'][0],
        ctx['client'].get('/v1/inference-calls').json()['items'][0],
    ]
    for value in values:
        assert value['id']==call['id'] and value['status']=='completed' and value['charged']==24
        assert value['result']['withheld'] is True and value['result']['citations']==[]
        assert 'answer' not in value['result'] and CONTENT not in str(value)
    assert len(sent)==1
    with ctx['db']() as db:
        saved=db.get(InferenceCall,call['id']);ledger=db.scalar(select(InferenceBudget))
        assert saved.result['answer'] and saved.result['citations']  # Historical row not rewritten.
        assert ledger.spent==24 and ledger.held==0


@pytest.mark.parametrize('mutation',['revoke','delete','replace'])
def test_source_change_while_model_runs_is_withheld_after_accounting(ctx, monkeypatch, mutation):
    ids={}
    def provider(request):
        with ctx['db'].begin() as db:
            source=db.get(KnowledgeDocument,ids['document'])
            if mutation=='revoke':source.allowed_roles=[]
            elif mutation=='delete':source.status='deleted'
            else:source.version+=1
        return httpx.Response(200,json={'choices':[{'message':{'content':'Private derived answer'}}],
                                       'usage':{'prompt_tokens':12,'completion_tokens':4}})
    headers,body,sent,doc=grounded(ctx,monkeypatch,provider);ids['document']=doc['id']
    result=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert result.status_code==200,result.text
    call=result.json()
    assert call['status']=='completed' and call['charged']==24 and call['result']['withheld']
    assert 'Private derived answer' not in result.text and len(sent)==1


def test_workspace_history_is_filtered_for_the_current_viewer(ctx, monkeypatch):
    headers,body,_,_=grounded(ctx,monkeypatch)
    call=ctx['client'].post('/v1/inference',headers=headers,json=body).json()
    auth(ctx,'auditor')
    for value in (ctx['client'].get('/v1/runtime').json()['calls'][0],
                  ctx['client'].get('/v1/inference-calls').json()['items'][0]):
        assert value['id']==call['id'] and value['result']['withheld']
        assert 'answer' not in value['result'] and CONTENT not in str(value)


@pytest.mark.parametrize('field,value',[('sha256','0'*64),('text','tampered'),('document_id','missing'),
                                        ('document_version',True),('chunk',True),('source_kind','unknown')])
def test_malformed_or_tampered_saved_source_proof_is_not_returned(ctx, monkeypatch, field, value):
    headers,body,_,_=grounded(ctx,monkeypatch)
    call=ctx['client'].post('/v1/inference',headers=headers,json=body).json()
    with ctx['db'].begin() as db:
        row=db.get(InferenceCall,call['id']);changed=deepcopy(row.result)
        changed['citations'][0][field]=value;row.result=changed
        flag_modified(row,'result')  # JSON true compares equal to Python integer 1.
    assert ctx['client'].get('/v1/inference-calls').json()['items'][0]['result']['withheld']


def test_mismatched_source_snapshot_is_rejected_before_budget_or_model(ctx, monkeypatch):
    import nexus.inference as inference
    headers,body,sent,_=grounded(ctx,monkeypatch)
    original=inference.retrieve_evidence
    def stale(db,user,query):
        rows=original(db,user,query);rows[0]['sha256']='0'*64;return rows
    monkeypatch.setattr(inference,'retrieve_evidence',stale)
    result=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert result.status_code==409 and result.json()['error']['code']=='EVIDENCE_CHANGED' and not sent
    with ctx['db']() as db:assert db.scalar(select(InferenceCall)) is None


def test_history_helper_without_a_viewer_fails_closed_for_document_answers(ctx, monkeypatch):
    from nexus.inference_history import page
    headers,body,_,_=grounded(ctx,monkeypatch)
    ctx['client'].post('/v1/inference',headers=headers,json=body)
    with ctx['db']() as db:
        result=page(db,ctx['settings'],'northstar',environment='staging')
        assert result['items'][0]['result']['withheld']
