"""Normal scoped APIs plus synthetic loopback transport; no real model calls."""
import hashlib,json,subprocess
from pathlib import Path
import httpx
import pytest
from sqlalchemy import select
from conftest import auth
from test_hybrid import upload
from test_local_embeddings import INFO
from nexus import hybrid,neural_worker
from nexus.db import User,KnowledgeDocument,WorkbenchRun
from nexus.environments import assign_staging
from nexus.local_embeddings import embed_texts,EmbeddingError
from nexus.neural_search import checked_result
from nexus.service import canonical

MODEL='synthetic-embedding:test';DIGEST='1'*64

def configure(ctx):
    ctx['settings'].ollama_embedding_enabled=1
    ctx['settings'].ollama_embedding_model=MODEL
    ctx['settings'].ollama_embedding_digest=DIGEST

def transport(after=None,digest=DIGEST):
    calls=[];tags=0
    def handle(request):
        nonlocal tags
        calls.append((request.url.path,request.content))
        if request.url.path=='/api/tags':
            tags+=1
            return httpx.Response(200,json={'models':[{'name':MODEL,'model':MODEL,'digest':digest if tags==1 or after is None else after}]})
        if request.url.path=='/api/show':return httpx.Response(200,json=INFO)
        value=json.loads(request.content)
        assert value['truncate'] is False
        return httpx.Response(200,json={'model':MODEL,'embeddings':[[1,0] for _ in value['input']],'prompt_eval_count':5})
    return httpx.MockTransport(handle),calls

def request(ctx,role='owner',key='neural-search-intent-001',**changes):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/hybrid-search',headers=headers,json={'query':'pump','retrieval_mode':'local_neural',**changes})

def fake_compute(monkeypatch):
    mock,calls=transport();payloads=[]
    def compute(payload):payloads.append(payload);return neural_worker.rank(payload,transport=mock)
    monkeypatch.setattr(hybrid,'compute',compute)
    return payloads,calls

def test_disabled_by_default_and_explicit_operator_settings(ctx,monkeypatch):
    def forbidden(_):raise AssertionError('Disabled search must not dispatch')
    monkeypatch.setattr(hybrid,'compute',forbidden)
    assert request(ctx).status_code==503
    assert ctx['client'].get('/v1/hybrid-search/capabilities').json()['neural_embeddings'] is False
    configure(ctx)
    ctx['settings'].validate()
    caps=ctx['client'].get('/v1/hybrid-search/capabilities').json()
    assert caps['neural_embeddings'] and caps['neural_model']==MODEL and caps['neural_max_chunks']==32
    assert not caps['persistent_vector_index']

def test_real_client_checks_digest_before_text_and_after_embedding():
    mock,calls=transport();value=embed_texts(MODEL,['approved synthetic text'],expected_digest=DIGEST,transport=mock)
    assert value['dimensions']==2
    assert [p for p,_ in calls]==['/api/tags','/api/show','/api/embed','/api/tags']
    mock,calls=transport(digest='2'*64)
    with pytest.raises(EmbeddingError,match='EMBEDDING_MODEL_CHANGED'):embed_texts(MODEL,['private text'],expected_digest=DIGEST,transport=mock)
    assert [p for p,_ in calls]==['/api/tags'] and 'private text' not in str(calls)
    mock,calls=transport(after='2'*64)
    with pytest.raises(EmbeddingError,match='EMBEDDING_MODEL_CHANGED'):embed_texts(MODEL,['approved text'],expected_digest=DIGEST,transport=mock)
    assert len(calls)==4

def test_api_filters_before_embedding_pins_model_and_recovers_without_repeating(ctx,monkeypatch):
    configure(ctx)
    with ctx['db'].begin() as db:
        user=User(id='synthetic-neural-reader',org_id='northstar',email='neural@test.invalid',name='Neural evaluator',role='engineer',password_hash='not-a-login-hash')
        db.add(user);db.flush();assign_staging(db,user)
    visible=upload(ctx,'pump approved synthetic source',['engineer'])
    hidden=upload(ctx,'private hidden synthetic source')
    payloads,calls=fake_compute(monkeypatch)
    response=request(ctx,role='engineer',one_per_document=True);assert response.status_code==201,response.text
    result=response.json();assert result['status']=='completed' and result['provider_calls']==4 and result['embedding_dimensions']==2
    assert [r['document_id'] for r in result['items']]==[visible['id']]
    assert result['parameters']['embedding_digest']==DIGEST and result['parameters']['embedding_model']==MODEL
    assert 'dimensions' not in result['parameters'] and 'semantic_weight' not in result['parameters']
    assert result['query_text_stored'] is False and result['normalization_current']
    assert hidden['id'] not in str(result) and payloads[0]['texts']==['pump approved synthetic source']
    assert 'private hidden' not in str(calls)
    assert request(ctx,role='engineer',one_per_document=True).json()['id']==result['id'] and len(payloads)==1
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,result['id']);assert 'pump' not in str(saved.result)
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+visible['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Revoke neural reader after search.'}).status_code==200
    auth(ctx,'engineer');history=ctx['client'].get('/v1/hybrid-search/history/'+result['id']).json()
    assert history['items']==[] and history['withheld_stale_or_inaccessible']==1
    auth(ctx,org='other');assert ctx['client'].get('/v1/hybrid-search/history/'+result['id']).status_code==404

@pytest.mark.parametrize('change',['acl','model'])
def test_completion_rechecks_source_and_operator_configuration(ctx,monkeypatch,change):
    configure(ctx);doc=upload(ctx,'pump synthetic current source')
    mock,_=transport()
    def compute(payload):
        result=neural_worker.rank(payload,transport=mock)
        if change=='model':ctx['settings'].ollama_embedding_digest='2'*64
        else:
            with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).version+=1
        return result
    monkeypatch.setattr(hybrid,'compute',compute)
    result=request(ctx).json();assert result['status']=='failed' and result['items']==[] and result['provider_calls'] is None
    assert result['error_code']==('NEURAL_CONFIGURATION_CHANGED' if change=='model' else 'SOURCE_SCOPE_CHANGED')

def test_empty_corpus_no_provider_calls_and_worker_failure_is_not_zero_calls(ctx,monkeypatch):
    configure(ctx)
    def forbidden(_):raise AssertionError('Empty corpus must not dispatch')
    monkeypatch.setattr(hybrid,'compute',forbidden)
    result=request(ctx).json();assert result['status']=='completed' and result['provider_calls']==0
    upload(ctx,'pump source');monkeypatch.setattr(hybrid,'compute',lambda _: {'error_code':'SEARCH_TIMEOUT'})
    result=request(ctx,key='neural-timeout-intent-001').json()
    assert result['status']=='failed' and result['error_code']=='SEARCH_TIMEOUT' and result['provider_calls'] is None

def test_corpus_limit_and_server_only_model_fields(ctx,monkeypatch):
    configure(ctx);upload(ctx,('pump '*6000)[:26000])
    def forbidden(_):raise AssertionError('Invalid corpus must not dispatch')
    monkeypatch.setattr(hybrid,'compute',forbidden)
    assert request(ctx).status_code==422
    assert request(ctx,embedding_model='other:test').status_code==422
    assert request(ctx,dimensions=2).status_code==422

def test_worker_groups_before_top_k_and_parent_rejects_wrong_model_protocol():
    payload={'texts':['pump one','pump two','pump three'],'query':'pump','embedding_model':MODEL,'embedding_digest':DIGEST,'min_score':0,'top_k':2,'one_per_document':True,'groups':[0,0,1]}
    mock,_=transport();value=neural_worker.rank(payload,transport=mock)
    assert [s['position'] for s in value['scores']]==[0,2]
    assert checked_result(value,3,2,MODEL,DIGEST)==value
    assert checked_result({**value,'embedding_digest':'2'*64},3,2,MODEL,DIGEST)['error_code']=='RANKING_FAILED'
    assert checked_result({**value,'embedding_dimensions':True},3,2,MODEL,DIGEST)['error_code']=='RANKING_FAILED'

def test_legacy_request_fingerprint_and_defaults_remain_unchanged(ctx,monkeypatch):
    body=hybrid.Search(query='pump',dimensions=2)
    legacy=body.model_dump();legacy.pop('retrieval_mode');legacy.pop('one_per_document')
    configure(ctx);upload(ctx,'pump current source')
    monkeypatch.setattr(hybrid,'compute',lambda _: {'rank':1,'vocabulary':1,'scores':[]})
    headers,_=auth(ctx);headers['Idempotency-Key']='legacy-request-key-001'
    response=ctx['client'].post('/v1/hybrid-search',headers=headers,json={'query':'pump','dimensions':2})
    assert response.status_code==201,response.text
    with ctx['db']() as db:
        row=db.get(WorkbenchRun,response.json()['id']);assert row.result['fingerprint']==hashlib.sha256(canonical(legacy).encode()).hexdigest()
    assert ctx['client'].post('/v1/hybrid-search',headers=headers,json={'query':'pump','dimensions':2,'retrieval_mode':'local_lsa'}).json()['id']==response.json()['id']

def test_embedding_settings_load_from_environment_without_operator_file(monkeypatch):
    from nexus.config import Settings
    monkeypatch.setattr('nexus.config.load_env',lambda:None)
    monkeypatch.setenv('NEXUS_OLLAMA_EMBEDDING_ENABLED','1')
    monkeypatch.setenv('NEXUS_OLLAMA_EMBEDDING_MODEL',MODEL)
    monkeypatch.setenv('NEXUS_OLLAMA_EMBEDDING_DIGEST',DIGEST)
    settings=Settings.from_env()
    assert settings.ollama_embedding_enabled==1 and settings.ollama_embedding_model==MODEL and settings.ollama_embedding_digest==DIGEST

def test_neural_worker_dispatch_uses_hard_parent_deadline_without_real_process(monkeypatch):
    waits=[];commands=[];kills=[]
    class Process:
        pid=99999999;returncode=0
        def wait(self,timeout=None):
            waits.append(timeout)
            if timeout is not None:raise subprocess.TimeoutExpired('synthetic worker',timeout)
        def poll(self):return None
        def kill(self):kills.append('kill')
    monkeypatch.setattr(hybrid.subprocess,'Popen',lambda args,**kwargs:commands.append((args,kwargs)) or Process())
    monkeypatch.setattr(hybrid.subprocess,'run',lambda *args,**kwargs:kills.append('tree'))
    monkeypatch.setattr(hybrid.os,'killpg',lambda *args:kills.append('group'),raising=False)
    assert hybrid.compute({'retrieval_mode':'local_neural'})=={'error_code':'SEARCH_TIMEOUT'}
    assert waits==[12,None] and 'nexus.neural_worker' in commands[0][0] and kills
    assert 'NEXUS_SECRET' not in commands[0][1]['env']

def test_real_child_rejects_unpinned_payload_before_any_http():
    result=hybrid.compute({'retrieval_mode':'local_neural','embedding_digest':None})
    assert result=={'error_code':'RANKING_FAILED'}

@pytest.mark.parametrize('changes',[{'ollama_embedding_enabled':1},{'ollama_embedding_enabled':2},
    {'ollama_embedding_model':'cloud:cloud','ollama_embedding_digest':DIGEST},
    {'ollama_embedding_enabled':1,'ollama_embedding_model':MODEL,'ollama_embedding_digest':DIGEST,'mode':'pilot'}])
def test_operator_configuration_rejects_unsupported_inputs(ctx,changes):
    for key,value in changes.items():setattr(ctx['settings'],key,value)
    with pytest.raises(RuntimeError):ctx['settings'].validate()
