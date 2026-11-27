"""Atomic bounded collection admission, existing checkpoint workers and whole-set readiness."""
import pytest
from sqlalchemy import select,func
from conftest import auth
from test_neural_index_jobs import context
from test_hybrid import upload
from test_multi_index_search import combined
from test_indexed_search_reviews import review
from nexus import index_collections as collections,neural_index_jobs as jobs
from nexus.db import WorkbenchRun,NeuralIndex,NeuralVector,now


def enqueue(ctx,docs,key='collection-build-intent-001',**changes):
    headers,_=auth(ctx);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/neural-index-collections',headers=headers,json={'name':'Synthetic larger collection','sources':[{'id':doc['id'],'version':doc['version']} for doc in docs],**changes})


def inspect(ctx,id):
    auth(ctx);response=ctx['client'].get('/v1/neural-index-collections/'+id);assert response.status_code==200,response.text;return response.json()


def larger(ctx,monkeypatch):
    _,calls=context(ctx,monkeypatch)
    return [upload(ctx,('Synthetic '+str(i)+' collection pump. ')*400) for i in range(2)],calls


def test_larger_corpus_partitions_without_dispatch_and_publishes_complete_searchable_set(ctx,monkeypatch):
    docs,calls=larger(ctx,monkeypatch);response=enqueue(ctx,docs);assert response.status_code==202,response.text
    group=response.json();assert group['snapshot_count']==2 and 32<group['total_passages']<=64 and not group['searchable'] and calls==[]
    assert all(child['total_passages']<=32 and child['collection_id']==group['id'] for child in group['children'])
    assert enqueue(ctx,docs).json()['id']==group['id'] and calls==[]
    for _ in range(12):jobs.run_index_job_once(ctx['db'],ctx['settings'])
    complete=inspect(ctx,group['id']);assert complete['status']=='completed' and complete['searchable'] and len(complete['index_ids'])==2
    assert complete['completed_passages']==complete['total_passages']
    result=combined(ctx,complete['index_ids'],one_per_document=True).json();assert result['status']=='completed' and result['corpus_chunks']==group['total_passages']
    assert {hit['document_id'] for hit in result['items']}=={doc['id'] for doc in docs}
    checked=review(ctx,result,[doc['id'] for doc in docs]).json();assert checked['status']=='passed' and len(checked['index_ids'])==2
    headers,_=auth(ctx);assert ctx['client'].post('/v1/neural-index-collections/recover',headers=headers,json={'key':'collection-build-intent-001'}).json()['id']==group['id']
    assert group['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


def test_collection_readiness_never_returns_a_partial_index_set(ctx,monkeypatch):
    docs,calls=larger(ctx,monkeypatch);group=enqueue(ctx,docs).json()
    for _ in range(4):jobs.run_index_job_once(ctx['db'],ctx['settings'])
    partial=inspect(ctx,group['id']);assert any(child['status']=='completed' for child in partial['children'])
    assert not partial['searchable'] and partial['index_ids']==[]


@pytest.mark.parametrize('capacity',['snapshots','rate','jobs'])
def test_failed_admission_rolls_back_entire_collection(ctx,monkeypatch,capacity):
    docs,calls=larger(ctx,monkeypatch)
    if capacity=='snapshots':monkeypatch.setattr(collections,'MAX_INDEXES',1)
    else:
        _,author=auth(ctx)
        with ctx['db'].begin() as db:
            for i in range(29 if capacity=='rate' else 19):
                db.add(WorkbenchRun(org_id='northstar',env='staging',author_id=author,kind='hybrid_search' if capacity=='rate' else 'neural_index_job',status='completed' if capacity=='rate' else 'queued',duration_ms=0,result={}))
    response=enqueue(ctx,docs);assert response.status_code==429,response.text
    assert calls==[]
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(NeuralIndex))==0
        assert db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind=='neural_index_collection'))==0


def test_cancel_only_unfinished_jobs_and_require_fresh_collection_token(ctx,monkeypatch):
    docs,calls=larger(ctx,monkeypatch);group=enqueue(ctx,docs).json()
    for _ in range(4):jobs.run_index_job_once(ctx['db'],ctx['settings'])
    headers,_=auth(ctx)
    path='/v1/neural-index-collections/'+group['id']+'/cancel'
    assert ctx['client'].post(path,headers=headers,json={'expected_token':group['control_token'],'note':'Stale collection review.'}).status_code==409
    current=inspect(ctx,group['id']);headers,_=auth(ctx)
    response=ctx['client'].post(path,headers=headers,json={'expected_token':current['control_token'],'note':'Cancel unfinished synthetic children.'})
    assert response.status_code==200,response.text
    value=response.json();assert value['status']=='incomplete' and value['index_ids']==[]
    assert {child['status'] for child in value['children']}=={'completed','cancelled'}
    assert enqueue(ctx,docs).json()['id']==group['id']


def test_source_change_makes_collection_stale_and_hides_full_set_selection(ctx,monkeypatch):
    docs,calls=larger(ctx,monkeypatch);group=enqueue(ctx,docs).json()
    for _ in range(12):jobs.run_index_job_once(ctx['db'],ctx['settings'])
    assert inspect(ctx,group['id'])['searchable']
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+docs[0]['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Change synthetic source membership.'}).status_code==200
    value=inspect(ctx,group['id']);assert value['status']=='stale' and not value['searchable'] and value['index_ids']==[]


def test_scope_permissions_source_versions_and_empty_selection(ctx,monkeypatch):
    docs,calls=larger(ctx,monkeypatch);group=enqueue(ctx,docs).json()
    assert enqueue(ctx,docs,name='Changed collection name').status_code==409
    for role,org in [('auditor','northstar'),('owner','other')]:
        headers,_=auth(ctx,role,org)
        assert ctx['client'].get('/v1/neural-index-collections/'+group['id']).status_code==404
        assert ctx['client'].get('/v1/neural-index-collections').json()['items']==[]
    assert enqueue(ctx,docs,key='stale-source-group-001',sources=[{'id':docs[0]['id'],'version':2}]).status_code==409
    assert enqueue(ctx,docs,key='empty-source-group-001',sources=[]).status_code==422 and calls==[]


@pytest.mark.parametrize('passages_per_document,accepted',[(42,True),(44,False)])
def test_eight_snapshot_boundary_and_oversized_selection_are_explicit(ctx,monkeypatch,passages_per_document,accepted):
    _,calls=context(ctx,monkeypatch)
    docs=[upload(ctx,(f'Synthetic source {i}. '+'x'*(passages_per_document*620))[:passages_per_document*620]) for i in range(6)]
    response=enqueue(ctx,docs)
    if accepted:
        assert response.status_code==202,response.text
        group=response.json();assert group['snapshot_count']==8 and group['total_passages']==252
        with ctx['db']() as db:
            children=[db.get(WorkbenchRun,child['id']) for child in group['children']]
            entries=[entry for child in children for entry in child.result['entries']]
            assert len(entries)==len({(e['document_id'],e['position']) for e in entries})==252
    else:
        assert response.status_code==422,response.text
        with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralIndex))==0
    assert calls==[]


def test_incompatible_child_dimensions_cannot_be_selected_as_complete_collection(ctx,monkeypatch):
    docs,calls=larger(ctx,monkeypatch);group=enqueue(ctx,docs).json()
    for _ in range(12):jobs.run_index_job_once(ctx['db'],ctx['settings'])
    with ctx['db'].begin() as db:db.get(NeuralIndex,group['children'][1]['index_id']).dimensions=3
    value=inspect(ctx,group['id']);assert value['status']=='stale' and not value['searchable'] and value['index_ids']==[]
