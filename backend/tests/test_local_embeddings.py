"""Synthetic transports only: no installed model, provider or database required."""
import copy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from nexus.local_embeddings import EmbeddingError, embed_texts, rank_texts
import nexus.local_embeddings as module

MODEL='synthetic-embedding:test'
INFO={'details':{'format':'gguf'},'model_info':{'architecture':'synthetic'},'capabilities':['embedding']}

def transport(vectors=None,info=None,change=None):
    calls=[]
    def handle(request):
        value=json.loads(request.content);calls.append((request,value))
        assert str(request.url).startswith('http://127.0.0.1:11434/api/')
        assert 'authorization' not in request.headers
        if request.url.path=='/api/show':return httpx.Response(200,json=INFO if info is None else info)
        assert request.url.path=='/api/embed'
        reply={'model':MODEL,'embeddings':vectors if vectors is not None else [[1,0] for _ in value['input']],'prompt_eval_count':10}
        if change:reply.update(change)
        return httpx.Response(200,json=reply)
    return httpx.MockTransport(handle),calls

def test_exact_unicode_batch_no_truncation_no_redirects_no_proxies(monkeypatch):
    mock,calls=transport([[3,4],[0,2]])
    original=httpx.Client;options=[]
    def client(**kwargs):options.append(kwargs);return original(**kwargs)
    monkeypatch.setattr(module.httpx,'Client',client)
    value=embed_texts(MODEL,['English query','الموافقة على المشتريات'],transport=mock)
    assert value['vectors']==[[.6,.8],[0,1]] and value['dimensions']==2
    assert value['embedding_requests']==1 and len(calls)==2
    assert calls[0][1]=={'model':MODEL}
    assert calls[1][1]=={'model':MODEL,'input':['English query','الموافقة على المشتريات'],'truncate':False}
    assert options[0]['trust_env'] is options[0]['follow_redirects'] is False

@pytest.mark.parametrize('change',[{'remote_host':'https://private.invalid'},{'remote_model':'private-model'},
    {'details':{'format':'remote'}},{'model_info':{}},{'capabilities':['completion']},{'capabilities':['embedding',1]}])
def test_remote_or_nonembedding_metadata_blocks_text_before_transmission(change):
    mock,calls=transport(info={**INFO,**change})
    with pytest.raises(EmbeddingError,match='^EMBEDDING_LOCAL_WEIGHTS_REQUIRED$'):
        embed_texts(MODEL,['PRIVATE INPUT'],transport=mock)
    assert len(calls)==1 and 'PRIVATE INPUT' not in str(calls[0][1])

@pytest.mark.parametrize('texts',[[],[''],[' '],['x\x00y'],['\ud800'],['x'*4097],['x']*34,['ع'*2049],['x'*4096]*17])
def test_input_limits_are_checked_before_network(texts):
    mock,calls=transport()
    with pytest.raises(EmbeddingError):embed_texts(MODEL,texts,transport=mock)
    assert calls==[]

@pytest.mark.parametrize('model',['no-tag','model:cloud','model:latest-cloud','https://private.invalid/model:test','private\nmodel:test'])
def test_invalid_model_and_cloud_tags_never_make_requests(model):
    mock,calls=transport()
    with pytest.raises(EmbeddingError,match='^EMBEDDING_MODEL_INVALID$'):embed_texts(model,['x'],transport=mock)
    assert calls==[]

@pytest.mark.parametrize('vectors',[[[0,0]],[[True,0]],[[1,'private']],[[10**400,0]],[[1e7,0]],[[]],[[1]*4097],[],[[1],[1,2]]])
def test_invalid_vectors_fail_closed(vectors):
    mock,_=transport(vectors)
    texts=['a','b'] if len(vectors)==2 else ['a']
    with pytest.raises(EmbeddingError):embed_texts(MODEL,texts,transport=mock)

@pytest.mark.parametrize('change',[{'model':'other:test'},{'prompt_eval_count':True},{'prompt_eval_count':-1},{'prompt_eval_count':'private'}])
def test_model_binding_and_usage_require_supported_types(change):
    mock,_=transport(change=change)
    with pytest.raises(EmbeddingError,match='^EMBEDDING_RESPONSE_INVALID$'):embed_texts(MODEL,['a'],transport=mock)

@pytest.mark.parametrize('raw',[b'{"embeddings":[],"embeddings":[]}',b'{"embeddings":[[NaN]]}',b'{"embeddings":[[Infinity]]}',b'private provider error',b'['*1200+b']'*1200])
def test_bad_json_is_bounded_and_does_not_echo_provider_values(raw):
    def handle(request):
        return httpx.Response(200,json=INFO) if request.url.path=='/api/show' else httpx.Response(200,content=raw)
    with pytest.raises(EmbeddingError,match='^EMBEDDING_RESPONSE_INVALID$'):
        embed_texts(MODEL,['private query'],transport=httpx.MockTransport(handle))

def test_oversized_response_no_retries_and_late_completion(monkeypatch):
    monkeypatch.setattr(module,'MAX_RESPONSE_BYTES',200)
    calls=[]
    def oversized(request):
        calls.append(request.url.path)
        return httpx.Response(200,json=INFO) if request.url.path=='/api/show' else httpx.Response(200,content=b'x'*201)
    with pytest.raises(EmbeddingError,match='^EMBEDDING_RESPONSE_LIMIT$'):
        embed_texts(MODEL,['a'],transport=httpx.MockTransport(oversized))
    assert calls==['/api/show','/api/embed']
    clock=[0];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    def late(request):
        if request.url.path=='/api/show':return httpx.Response(200,json=INFO)
        clock[0]=11
        return httpx.Response(200,json={'model':MODEL,'embeddings':[[1]],'prompt_eval_count':1})
    with pytest.raises(EmbeddingError,match='^EMBEDDING_DEADLINE$'):
        embed_texts(MODEL,['a'],transport=httpx.MockTransport(late))

@pytest.mark.parametrize('status',[301,404,429,500])
def test_http_errors_do_not_follow_redirects_retry_or_echo(status):
    calls=[]
    def handle(request):calls.append(request);return httpx.Response(status,headers={'Location':'https://private.invalid'},text='private provider details')
    with pytest.raises(EmbeddingError,match='^EMBEDDING_HTTP_ERROR$'):
        embed_texts(MODEL,['private query'],transport=httpx.MockTransport(handle))
    assert len(calls)==1

def test_transport_timeout_is_sanitized():
    def handle(request):raise httpx.ReadTimeout('private socket details')
    with pytest.raises(EmbeddingError,match='^EMBEDDING_DEADLINE$'):
        embed_texts(MODEL,['a'],transport=httpx.MockTransport(handle))

def test_cosine_ranking_filters_negative_and_zero_and_breaks_ties_by_position():
    mock,_=transport([[1,0],[2,0],[3,0],[0,1],[-1,0]])
    result=rank_texts(MODEL,'query',['a','b','c','d'],top_k=2,transport=mock)
    assert result['scores']==[{'position':0,'score':1.0},{'position':1,'score':1.0}]
    assert result['corpus_passages']==4 and 'vectors' not in result and 'query' not in result

def test_cosine_threshold_and_top_k_are_applied_to_real_vectors():
    mock,_=transport([[1,0],[3,4],[1,0]])
    result=rank_texts(MODEL,'query',['a','b'],min_score=.7,transport=mock)
    assert result['scores']==[{'position':1,'score':1.0}]

@pytest.mark.parametrize('args',[{'top_k':True},{'top_k':0},{'top_k':11},{'min_score':True},{'min_score':float('nan')},{'min_score':-1},{'timeout_seconds':False},{'timeout_seconds':31}])
def test_invalid_ranking_controls_do_not_make_requests(args):
    mock,calls=transport()
    with pytest.raises(EmbeddingError):rank_texts(MODEL,'query',['a'],transport=mock,**args)
    assert calls==[]

def tool():
    path=Path(__file__).resolve().parents[2]/'scripts/check_local_embeddings.py'
    spec=importlib.util.spec_from_file_location('embedding_exercise',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def test_default_exercise_has_no_network_and_receipt_contains_no_text_or_vectors(tmp_path,monkeypatch,capsys):
    script=tool()
    def forbidden(*args,**kwargs):raise AssertionError('No model call allowed by default')
    monkeypatch.setattr(script,'rank_texts',forbidden)
    assert script.main([])==0
    assert json.loads(capsys.readouterr().out)['local_call_requested'] is False
    script=tool();mock,_=transport([[1,0]]*4)
    report=script.exercise(MODEL,tmp_path,transport=mock)
    assert report['completed'] and not report['semantic_quality_accepted'] and not report['production_ready']
    saved=json.loads(Path(report['report']).read_text(encoding='utf-8'))
    assert saved['dimensions']==2 and saved['embedding_requests']==1
    assert set(saved).isdisjoint({'vectors','texts','query','scores','answer','credentials'})
    assert len(list(tmp_path.iterdir()))==1 and len(saved['source_sha256'])==64

def test_publication_failure_leaves_no_success_or_temporary_receipt(tmp_path,monkeypatch):
    script=tool();mock,_=transport([[1,0]]*4)
    def fail(*args,**kwargs):raise OSError('private publication detail')
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(OSError):script.exercise(MODEL,tmp_path,transport=mock)
    assert list(tmp_path.iterdir())==[]
