"""Bounded HTTP protocol and scoped saved-search ordering with synthetic models."""
import json
import httpx
import pytest
from sqlalchemy import select
from conftest import auth
from test_multi_index_search import corpus,combined
from test_indexed_search_reviews import review
from nexus import local_reranking as local,rerank_runtime
from nexus.db import WorkbenchRun,KnowledgeDocument

MODEL='synthetic-reranker:test';DIGEST='3'*64


def configure(ctx):
    ctx['settings'].ollama_rerank_enabled=1;ctx['settings'].ollama_rerank_model=MODEL;ctx['settings'].ollama_rerank_digest=DIGEST


def mock_transport(order=None,*,bad_digest=False,remote=False,content=None):
    calls=[]
    def handle(request):
        calls.append(request)
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':MODEL,'model':MODEL,'digest':'4'*64 if bad_digest else DIGEST}]})
        if request.url.path=='/api/show':return httpx.Response(200,json={'details':{'format':'gguf'},'model_info':{'general.architecture':'synthetic'},'capabilities':['completion','thinking'],**({'remote_host':'https://remote.invalid'} if remote else {})})
        assert request.url.path=='/api/chat';payload=json.loads(request.content)
        assert payload['stream'] is False and payload['think'] is False and 'tools' not in payload
        assert payload['options']['num_predict']==512 and payload['format']['additionalProperties'] is False
        return httpx.Response(200,json={'model':MODEL,'done':True,'done_reason':'stop','message':{'role':'assistant','content':content if content is not None else json.dumps({'order':order if order is not None else [1,0]})},'prompt_eval_count':100,'eval_count':10})
    return httpx.MockTransport(handle),calls


def context(ctx,monkeypatch):
    first,second,a,b,payloads,_=corpus(ctx,monkeypatch)
    base=combined(ctx,[a,b],query='original synthetic query').json();assert len(base['items'])==2
    configure(ctx);mock,calls=mock_transport()
    monkeypatch.setattr(rerank_runtime,'compute',lambda p:local.rerank(p['rerank_model'],p['rerank_digest'],p['query'],p['texts'],transport=mock))
    return base,calls


def request(ctx,base,key='local-rerank-intent-0001',**changes):
    headers,_=auth(ctx);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/neural-indexes/rerank',headers=headers,json={'search_id':base['id'],'query':'original synthetic query',**changes})


def test_protocol_checks_local_identity_before_sending_text_and_returns_only_permutation():
    mock,calls=mock_transport();value=local.rerank(MODEL,DIGEST,'query',['first passage','second passage'],transport=mock)
    assert value['order']==[1,0] and [r.url.path for r in calls]==['/api/tags','/api/show','/api/chat','/api/tags']
    assert all(r.url.host=='127.0.0.1' for r in calls)
    for flags in ({'bad_digest':True},{'remote':True}):
        mock,calls=mock_transport(**flags)
        with pytest.raises(local.RerankError):local.rerank(MODEL,DIGEST,'private query',['private one','private two'],transport=mock)
        assert all(r.url.path!='/api/chat' for r in calls) and 'private query' not in str([r.content for r in calls])


@pytest.mark.parametrize('order',[[0,0],[True,0],[-1,0],[0,2],[0],[0,1,2],{'order':[0,1]}])
def test_malformed_duplicate_or_hallucinated_positions_are_rejected(order):
    mock,_=mock_transport(order)
    with pytest.raises(local.RerankError):local.rerank(MODEL,DIGEST,'query',['a','b'],transport=mock)


@pytest.mark.parametrize('content',['{"order":[0,1],"order":[1,0]}','{"order":[0,1],"answer":"invented"}','not json','{"order":[NaN,1]}'])
def test_free_text_extra_fields_and_ambiguous_json_are_rejected(content):
    mock,_=mock_transport(content=content)
    with pytest.raises(local.RerankError):local.rerank(MODEL,DIGEST,'query',['a','b'],transport=mock)


def test_normal_api_reorders_only_original_hits_and_recovery_never_repeats_model(ctx,monkeypatch):
    base,calls=context(ctx,monkeypatch);response=request(ctx,base);assert response.status_code==201,response.text
    value=response.json();assert value['status']=='completed' and value['provider_calls']==4 and value['parent_provider_calls']==4
    assert [h['citation'] for h in value['items']]==[h['citation'] for h in reversed(base['items'])]
    assert [h['score'] for h in value['items']]==[h['score'] for h in reversed(base['items'])]
    assert [h['rerank_position'] for h in value['items']]==[1,2] and value['parameters']['parent_search_id']==base['id']
    assert request(ctx,base).json()['id']==value['id'] and len(calls)==4
    ctx['settings'].ollama_rerank_enabled=0
    headers,_=auth(ctx);recovered=ctx['client'].post('/v1/hybrid-search/recover',headers=headers,json={'key':'local-rerank-intent-0001'}).json()
    assert recovered['id']==value['id'] and len(calls)==4
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,value['id']);assert 'original synthetic query' not in str(saved.result)
        assert 'excerpt' not in str(saved.result) and 'answer' not in saved.result


def test_disabled_and_different_query_fail_before_dispatch(ctx,monkeypatch):
    base,calls=context(ctx,monkeypatch);ctx['settings'].ollama_rerank_enabled=0
    assert request(ctx,base).status_code==503 and calls==[]
    configure(ctx);assert request(ctx,base,query='different query').status_code==409 and calls==[]


@pytest.mark.parametrize('change',['source','config','bad_order','parent'])
def test_completion_fences_discard_all_reordered_hits(ctx,monkeypatch,change):
    base,calls=context(ctx,monkeypatch);original=rerank_runtime.compute
    def changed(payload):
        value=original(payload)
        if change=='config':ctx['settings'].ollama_rerank_digest='4'*64
        elif change=='bad_order':value['order']=[0,0]
        else:
            with ctx['db'].begin() as db:
                if change=='source':db.get(KnowledgeDocument,base['items'][0]['document_id']).version+=1
                else:
                    row=db.get(WorkbenchRun,base['id']);row.result={**row.result,'vocabulary':1}
        return value
    monkeypatch.setattr(rerank_runtime,'compute',changed)
    value=request(ctx,base).json();assert value['status']=='failed' and value['items']==[] and value['provider_calls'] is None


def test_review_comparison_can_measure_rank_change_and_discloses_reranking(ctx,monkeypatch):
    base,calls=context(ctx,monkeypatch);candidate=request(ctx,base).json();expected=[base['items'][1]['document_id']]
    left=review(ctx,base,expected,key='base-rank-review-0001').json();right=review(ctx,candidate,expected,key='new-rank-review-0001').json()
    headers,_=auth(ctx);value=ctx['client'].post('/v1/indexed-search-reviews/compare',headers=headers,json={'baseline_id':left['id'],'candidate_id':right['id']}).json()
    assert value['reranking_changed'] and value['model_changed'] and not value['index_changed'] and value['change']=='improved'
    assert value['delta']['reciprocal_rank']==.5 and value['delta']['document_recall_at_k']==0 and len(calls)==4


def test_scope_and_recursive_reranking_are_rejected(ctx,monkeypatch):
    base,calls=context(ctx,monkeypatch);value=request(ctx,base).json()
    assert request(ctx,value,key='recursive-rerank-0001').status_code==409 and len(calls)==4
    headers,_=auth(ctx,'auditor');headers['Idempotency-Key']='auditor-rerank-0001'
    assert ctx['client'].post('/v1/neural-indexes/rerank',headers=headers,json={'search_id':base['id'],'query':'original synthetic query'}).status_code==404
    headers,_=auth(ctx,org='other');headers['Idempotency-Key']='other-rerank-0001'
    assert ctx['client'].post('/v1/neural-indexes/rerank',headers=headers,json={'search_id':base['id'],'query':'original synthetic query'}).status_code==404


def test_operator_config_validation_and_default_are_explicit(ctx,monkeypatch):
    assert local.configuration(ctx['settings']) is None
    configure(ctx);ctx['settings'].validate()
    for field,value in [('ollama_rerank_digest','bad'),('ollama_rerank_model','model:cloud'),('ollama_rerank_enabled',2),('mode','production')]:
        configure(ctx);monkeypatch.setattr(ctx['settings'],field,value)
        with pytest.raises(RuntimeError):ctx['settings'].validate()
        monkeypatch.undo()


def test_deadline_and_response_byte_limit_are_enforced(monkeypatch):
    mock,_=mock_transport();clock=[0.0];monkeypatch.setattr(local.time,'monotonic',lambda:clock[0])
    def late(request):
        response=mock.handle_request(request)
        if request.url.path=='/api/chat':clock[0]=21.0
        return response
    with pytest.raises(local.RerankError,match='RERANK_TIMEOUT'):
        local.rerank(MODEL,DIGEST,'query',['a','b'],transport=httpx.MockTransport(late))
    clock[0]=0
    with pytest.raises(local.RerankError,match='RERANK_RESPONSE_LIMIT'):
        local.rerank(MODEL,DIGEST,'query',['a','b'],transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*262145)))


def test_digest_change_after_chat_discards_otherwise_valid_order():
    mock,_=mock_transport();tags=[0]
    def changed(request):
        if request.url.path=='/api/tags':
            tags[0]+=1
            if tags[0]==2:return httpx.Response(200,json={'models':[{'name':MODEL,'model':MODEL,'digest':'4'*64}]})
        return mock.handle_request(request)
    with pytest.raises(local.RerankError,match='RERANK_MODEL_CHANGED'):
        local.rerank(MODEL,DIGEST,'query',['a','b'],transport=httpx.MockTransport(changed))


def test_caller_list_mutation_during_metadata_cannot_change_authorized_input():
    texts=['approved first','approved second'];mock,calls=mock_transport()
    def changed(request):
        if request.url.path=='/api/tags':texts[:]=['injected text','injected text']
        return mock.handle_request(request)
    local.rerank(MODEL,DIGEST,'query',texts,transport=httpx.MockTransport(changed))
    prompt=json.loads(next(r.content for r in calls if r.url.path=='/api/chat'))['messages'][1]['content']
    assert 'injected text' not in prompt and 'approved first' in prompt


def test_isolated_child_rejects_unpinned_reranking_before_http():
    from nexus.hybrid import compute
    assert compute({'retrieval_mode':'local_neural','task':'rerank','rerank_model':MODEL,'rerank_digest':'invalid','query':'query','texts':['a','b']})=={'error_code':'RANKING_FAILED'}
