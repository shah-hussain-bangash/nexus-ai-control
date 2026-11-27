"""Stored-index normal API acceptance using disposable data and mock transport."""
import json
import pytest
from sqlalchemy import select,func
from conftest import auth
from test_hybrid import upload
from test_authorized_neural_search import configure,transport
from nexus import neural_index_runtime as runtime,neural_worker
from nexus.db import NeuralIndex,NeuralVector,KnowledgeDocument,WorkbenchRun,now


def setup(ctx,monkeypatch):
    configure(ctx);doc=upload(ctx,'Synthetic pump inspection evidence')
    mock,calls=transport();payloads=[]
    def compute(payload):
        payloads.append(payload)
        return neural_worker.embedding_batch(payload,transport=mock)
    monkeypatch.setattr(runtime,'compute',compute)
    return doc,payloads,calls


def build(ctx,doc,key='synthetic-index-build-0001',role='owner',**changes):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/neural-indexes',headers=headers,json={
        'name':'Synthetic inspection index','sources':[{'id':doc['id'],'version':doc['version']}],**changes})


def search(ctx,id,key='synthetic-index-query-0001',**changes):
    headers,_=auth(ctx);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/neural-indexes/search',headers=headers,json={
        'index_id':id,'query':'synthetic query kept transient',**changes})


def test_build_query_and_recover_use_vectors_without_resending_source_text(ctx,monkeypatch):
    doc,payloads,calls=setup(ctx,monkeypatch)
    response=build(ctx,doc);assert response.status_code==201,response.text
    receipt=response.json();assert receipt['status']=='completed',receipt
    id=receipt['index_id'];assert receipt['provider_calls']==4
    result=search(ctx,id).json();assert result['status']=='completed',result
    assert result['items'][0]['document_id']==doc['id'] and result['provider_calls']==4
    assert set(payloads[1])=={'retrieval_mode','task','query','embedding_model','embedding_digest'}
    embedded=[json.loads(content)['input'] for path,content in calls if path=='/api/embed']
    assert embedded==[['Synthetic pump inspection evidence'],['synthetic query kept transient']]
    assert build(ctx,doc).json()['id']==receipt['id'] and search(ctx,id).json()['id']==result['id']
    headers,_=auth(ctx)
    assert ctx['client'].post('/v1/neural-indexes/recover',headers=headers,json={'key':'synthetic-index-build-0001'}).json()['id']==receipt['id']
    assert len(payloads)==2
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,result['id']);assert 'synthetic query kept transient' not in str(saved.result)
        assert 'vectors' not in saved.result
    workbench=ctx['client'].get('/v1/workbench');assert workbench.status_code==200
    assert receipt['id'] not in str(workbench.json()['runs'])


def test_deleted_snapshot_cannot_repeat_a_completed_build_intent(ctx,monkeypatch):
    doc,payloads,_=setup(ctx,monkeypatch);first=build(ctx,doc).json();id=first['index_id']
    headers,_=auth(ctx)
    response=ctx['client'].request('DELETE','/v1/neural-indexes/'+id,headers=headers,json={'expected_version':1,'note':'Remove disposable index.'})
    assert response.status_code==200,response.text
    ctx['settings'].ollama_embedding_enabled=0
    recovered=build(ctx,doc).json();assert recovered['id']==first['id'] and recovered['index_state']=='removed'
    assert len(payloads)==1
    assert build(ctx,doc,name='Changed request').status_code==409
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralVector))==0


@pytest.mark.parametrize('operation',['build','query'])
@pytest.mark.parametrize('change',['source','model','malformed'])
def test_completion_rechecks_sources_configuration_and_worker_protocol(ctx,monkeypatch,operation,change):
    doc,_,_=setup(ctx,monkeypatch)
    id=build(ctx,doc).json()['index_id'] if operation=='query' else None
    mock,_=transport()
    def compute(payload):
        result=neural_worker.embedding_batch(payload,transport=mock)
        if change=='source':
            with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).version+=1
        elif change=='model':ctx['settings'].ollama_embedding_digest='2'*64
        else:result['vectors']=[[0,0]]
        return result
    monkeypatch.setattr(runtime,'compute',compute)
    result=(search(ctx,id) if id else build(ctx,doc)).json()
    assert result['status']=='failed' and result['provider_calls'] is None,result
    if id:assert result['items']==[]
    else:
        with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralIndex))==0


def test_permissions_preflight_invalidation_and_reviewed_removal(ctx,monkeypatch):
    doc,payloads,_=setup(ctx,monkeypatch)
    assert build(ctx,doc,role='auditor').status_code==403
    id=build(ctx,doc).json()['index_id'];assert len(payloads)==1
    auth(ctx,'auditor');assert ctx['client'].get('/v1/neural-indexes').json()['items']==[]
    auth(ctx,org='other');assert ctx['client'].get('/v1/neural-indexes/builds').json()['items']==[]
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Invalidate disposable source.'}).status_code==200
    assert search(ctx,id).status_code==409 and len(payloads)==1
    headers,_=auth(ctx)
    assert ctx['client'].request('DELETE','/v1/neural-indexes/'+id,headers=headers,json={'expected_version':1,'note':'Stale reviewed version.'}).status_code==409
    listed=ctx['client'].get('/v1/neural-indexes').json()['items'][0]
    assert listed['status']=='invalidated' and listed['version']==2 and 'sources' not in listed


def test_build_and_search_share_concurrency_admission(ctx,monkeypatch):
    doc,payloads,_=setup(ctx,monkeypatch);_,author=auth(ctx)
    with ctx['db'].begin() as db:
        for kind in ('hybrid_search','neural_index_build'):
            db.add(WorkbenchRun(org_id='northstar',env='staging',author_id=author,kind=kind,status='processing',duration_ms=0,result={}))
    assert build(ctx,doc).status_code==429 and payloads==[]
    headers,_=auth(ctx);headers['Idempotency-Key']='shared-admission-search-001'
    assert ctx['client'].post('/v1/hybrid-search',headers=headers,json={'query':'pump'}).status_code==429


def test_disabled_model_and_stale_sources_do_not_dispatch(ctx,monkeypatch):
    doc,payloads,_=setup(ctx,monkeypatch);ctx['settings'].ollama_embedding_enabled=0
    assert build(ctx,doc).status_code==503
    configure(ctx)
    assert build(ctx,doc,sources=[{'id':doc['id'],'version':2}]).status_code==409
    assert payloads==[]


@pytest.mark.parametrize('field,value',[('vectors',[[1,0]]),('embedding_model','client-selected:test'),('embedding_digest','2'*64)])
def test_client_cannot_supply_embedding_results_or_model_identity(ctx,monkeypatch,field,value):
    doc,payloads,_=setup(ctx,monkeypatch)
    assert build(ctx,doc,**{field:value}).status_code==422 and payloads==[]


def test_timeout_receipt_recovers_without_repeating_and_counts_are_unknown(ctx,monkeypatch):
    doc,_,_=setup(ctx,monkeypatch);calls=[]
    def timeout(payload):calls.append(payload);return {'error_code':'SEARCH_TIMEOUT'}
    monkeypatch.setattr(runtime,'compute',timeout)
    result=build(ctx,doc).json();assert result['status']=='failed' and result['provider_calls'] is None
    assert build(ctx,doc).json()['id']==result['id'] and len(calls)==1
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralVector))==0
