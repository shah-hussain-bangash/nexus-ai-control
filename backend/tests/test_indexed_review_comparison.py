"""Same-query saved review comparisons; no model call during comparison."""
import pytest
from sqlalchemy import select
from conftest import auth
from test_neural_index_runtime import setup,build,search
from test_indexed_search_reviews import review
from nexus import neural_index_runtime
from nexus.db import WorkbenchRun,KnowledgeDocument
from nexus.indexed_review_comparison import query_identity


def pair(ctx,monkeypatch,*,query='same synthetic query',controls=None,labels=None,legacy=False):
    doc,payloads,_=setup(ctx,monkeypatch);index=build(ctx,doc).json()['index_id']
    first=search(ctx,index,key='comparison-search-0001',query='same synthetic query').json()
    second=search(ctx,index,key='comparison-search-0002',query=query,**(controls or {})).json()
    if legacy:
        with ctx['db'].begin() as db:
            row=db.get(WorkbenchRun,first['id']);value={k:v for k,v in row.result.items() if k!='query_identity'}
            if legacy=='malformed':value['query_identity']='invalid-'*8
            row.result=value
    left=review(ctx,first,[doc['id']],key='comparison-review-0001').json()
    right=review(ctx,second,[doc['id']],key='comparison-review-0002',**(labels or {})).json()
    def forbidden(_):raise AssertionError('Comparison must not execute a model')
    monkeypatch.setattr(neural_index_runtime,'compute',forbidden)
    return doc,first,second,left,right,payloads


def compare(ctx,left,right):
    headers,_=auth(ctx)
    return ctx['client'].post('/v1/indexed-search-reviews/compare',headers=headers,json={'baseline_id':left['id'],'candidate_id':right['id']})


def test_normal_api_uses_saved_measurements_and_keeps_query_identity_private(ctx,monkeypatch):
    doc,first,second,left,right,payloads=pair(ctx,monkeypatch,query='  same synthetic query  ')
    count=len(payloads);response=compare(ctx,left,right);assert response.status_code==200,response.text
    result=response.json();assert result['change']=='unchanged' and result['query_verified_same'] and result['provider_calls']==0
    assert not result['stale'] and not result['corpus_changed'] and not result['model_changed'] and not result['index_changed']
    assert result['delta']['document_recall_at_k']==result['delta']['document_precision_at_k']==result['delta']['reciprocal_rank']==0
    assert len(payloads)==count and 'same synthetic query' not in str(result)
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,first['id']);identity=saved.result['query_identity']
        assert 'same synthetic query' not in str(saved.result) and len(identity)==64
    assert identity not in str(result) and identity not in str(first) and identity not in str(left)


@pytest.mark.parametrize('changes,code',[
    ({'query':'different synthetic query'},'INDEX_COMPARE_QUERY_DIFFERENT'),
    ({'controls':{'top_k':3}},'INDEX_COMPARE_CONTROLS_DIFFERENT'),
    ({'controls':{'min_score':.3}},'INDEX_COMPARE_CONTROLS_DIFFERENT'),
    ({'controls':{'one_per_document':True}},'INDEX_COMPARE_CONTROLS_DIFFERENT'),
    ({'labels':{'query_language':'Arabic'}},'INDEX_COMPARE_LABELS_DIFFERENT'),
    ({'labels':{'minimum_precision_percent':100}},'INDEX_COMPARE_LABELS_DIFFERENT'),
    ({'legacy':True},'INDEX_COMPARE_QUERY_UNAVAILABLE'),
    ({'legacy':'malformed'},'INDEX_COMPARE_QUERY_UNAVAILABLE'),
])
def test_mismatched_or_legacy_evidence_fails_closed(ctx,monkeypatch,changes,code):
    _,_,_,left,right,_=pair(ctx,monkeypatch,**changes)
    response=compare(ctx,left,right);assert response.status_code==409,response.text
    assert response.json()['error']['code']==code


def test_same_review_or_same_search_cannot_appear_as_independent_comparison(ctx,monkeypatch):
    doc,first,_,left,right,_=pair(ctx,monkeypatch)
    assert compare(ctx,left,left).status_code==422
    duplicate=review(ctx,first,[doc['id']],key='another-review-same-search').json()
    response=compare(ctx,left,duplicate);assert response.status_code==409 and response.json()['error']['code']=='INDEX_COMPARE_SAME_SEARCH'


def test_access_and_staleness_apply_to_both_sides(ctx,monkeypatch):
    doc,_,_,left,right,_=pair(ctx,monkeypatch)
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).version+=1
    assert compare(ctx,left,right).json()['stale'] is True
    headers,_=auth(ctx,'auditor')
    assert ctx['client'].post('/v1/indexed-search-reviews/compare',headers=headers,json={'baseline_id':left['id'],'candidate_id':right['id']}).status_code==404
    headers,_=auth(ctx,org='other')
    assert ctx['client'].post('/v1/indexed-search-reviews/compare',headers=headers,json={'baseline_id':left['id'],'candidate_id':right['id']}).status_code==404
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).status='deleted'
    assert compare(ctx,left,right).status_code==404


def test_query_identity_is_keyed_and_scope_bound():
    identity=query_identity('private-key','org','staging','actor','query')
    assert len(identity)==64 and identity!=query_identity('other-key','org','staging','actor','query')
    for args in [('other','staging','actor','query'),('org','production','actor','query'),('org','staging','other','query'),('org','staging','actor','different')]:
        assert identity!=query_identity('private-key',*args)


@pytest.mark.parametrize('baseline_miss',[False,True])
def test_model_change_is_reported_without_claiming_causal_improvement(ctx,monkeypatch,baseline_miss):
    from test_authorized_neural_search import transport
    from nexus import neural_worker
    doc,_,_=setup(ctx,monkeypatch)
    if baseline_miss:
        mock,_=transport()
        def missed(payload):
            result=neural_worker.embedding_batch(payload,transport=mock)
            if payload.get('task')=='index_query':result['vectors']=[[0,1]]
            return result
        monkeypatch.setattr(neural_index_runtime,'compute',missed)
    first_index=build(ctx,doc).json()['index_id']
    first=search(ctx,first_index,key='model-first-search-001',query='same model query').json()
    left=review(ctx,first,[doc['id']],key='model-first-review-001').json()
    ctx['settings'].ollama_embedding_digest='2'*64
    mock,_=transport(digest='2'*64)
    monkeypatch.setattr(neural_index_runtime,'compute',lambda payload:neural_worker.embedding_batch(payload,transport=mock))
    second_index=build(ctx,doc,key='model-second-build-001').json()['index_id']
    second=search(ctx,second_index,key='model-second-search-001',query='same model query').json()
    right=review(ctx,second,[doc['id']],key='model-second-review-001').json()
    ctx['settings'].ollama_embedding_enabled=0
    monkeypatch.setattr(neural_index_runtime,'compute',lambda _:pytest.fail('Comparison must not execute'))
    response=compare(ctx,left,right);assert response.status_code==200,response.text
    value=response.json();assert value['model_changed'] and value['index_changed'] and not value['corpus_changed'] and value['change']==('improved' if baseline_miss else 'unchanged')


def test_reversed_expected_order_and_notes_do_not_change_label_compatibility(ctx,monkeypatch):
    from test_hybrid import upload
    doc,first,second,_,_,_=pair(ctx,monkeypatch)
    extra=upload(ctx,'Synthetic additional expected document')
    left=review(ctx,first,[doc['id'],extra['id']],key='order-first-review-001').json()
    right=review(ctx,second,[extra['id'],doc['id']],key='order-second-review-001',note='Different reviewer note allowed.').json()
    assert compare(ctx,left,right).status_code==200


def test_negative_comparisons_keep_metrics_not_applicable(ctx,monkeypatch):
    _,first,second,_,_,_=pair(ctx,monkeypatch)
    left=review(ctx,first,[],key='negative-first-review-001',expectation='no_results').json()
    right=review(ctx,second,[],key='negative-second-review-001',expectation='no_results').json()
    value=compare(ctx,left,right).json();assert value['change']=='unchanged'
    assert all(value['delta'][key] is None for key in ('document_recall_at_k','document_precision_at_k','reciprocal_rank'))
