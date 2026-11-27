"""Bounded combined snapshot search, single query embedding, shared ACL fences."""
import pytest
from sqlalchemy import select
from conftest import auth
from test_hybrid import upload
from test_neural_index_runtime import setup,build
from test_indexed_search_reviews import review
from nexus import neural_index_runtime,neural_worker
from nexus.db import KnowledgeDocument,WorkbenchRun


def corpus(ctx,monkeypatch):
    first,payloads,calls=setup(ctx,monkeypatch);second=upload(ctx,'Synthetic second pump source')
    a=build(ctx,first).json()['index_id']
    b=build(ctx,second,key='second-combined-build-001',sources=[{'id':first['id'],'version':1},{'id':second['id'],'version':1}]).json()['index_id']
    return first,second,a,b,payloads,calls


def combined(ctx,ids,key='combined-index-query-001',**changes):
    headers,_=auth(ctx);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/neural-indexes/search',headers=headers,json={'index_ids':ids,'query':'synthetic combined query',**changes})


def test_combined_query_embeds_once_deduplicates_passages_and_replays_canonical_selection(ctx,monkeypatch):
    first,second,a,b,payloads,calls=corpus(ctx,monkeypatch);before=len(calls)
    response=combined(ctx,[b,a]);assert response.status_code==201,response.text
    value=response.json();assert value['status']=='completed',value
    assert value['index_count']==2 and value['source_count']==2 and value['corpus_chunks']==2
    assert {h['document_id'] for h in value['items']}=={first['id'],second['id']} and len(value['items'])==2
    assert value['provider_calls']==4 and len(calls)==before+4 and payloads[-1]['task']=='index_query'
    assert 'texts' not in payloads[-1] and 'vectors' not in payloads[-1]
    assert value['parameters']['index_ids']==sorted([a,b]) and len(value['parameters']['index_versions'])==2
    assert combined(ctx,[a,b]).json()['id']==value['id'] and len(calls)==before+4
    headers,_=auth(ctx)
    assert ctx['client'].post('/v1/hybrid-search/recover',headers=headers,json={'key':'combined-index-query-001'}).json()['id']==value['id']


@pytest.mark.parametrize('ids',['duplicates','empty','too_many','missing','mixed'])
def test_invalid_selections_cannot_dispatch_a_partial_search(ctx,monkeypatch,ids):
    _,_,a,b,payloads,calls=corpus(ctx,monkeypatch);before=len(calls)
    selected={'duplicates':[a,a],'empty':[],'too_many':['index-'+str(i) for i in range(9)],'missing':[a,'missing-index'],'mixed':[a,b]}[ids]
    response=combined(ctx,selected,**({'index_id':a} if ids=='mixed' else {}))
    assert response.status_code==(404 if ids=='missing' else 422),response.text
    assert len(calls)==before


def test_all_selected_snapshots_are_rechecked_after_query_embedding(ctx,monkeypatch):
    first,_,a,b,payloads,calls=corpus(ctx,monkeypatch)
    original=neural_index_runtime.compute
    def changed(payload):
        result=original(payload)
        with ctx['db'].begin() as db:db.get(KnowledgeDocument,first['id']).version+=1
        return result
    monkeypatch.setattr(neural_index_runtime,'compute',changed)
    result=combined(ctx,[a,b]).json();assert result['status']=='failed' and result['items']==[] and result['provider_calls'] is None


def test_combined_search_review_and_comparison_keep_every_snapshot(ctx,monkeypatch):
    first,second,a,b,payloads,calls=corpus(ctx,monkeypatch)
    left=combined(ctx,[a,b]).json();right=combined(ctx,[b,a],key='combined-index-query-002').json()
    before=len(calls)
    def forbidden(_):raise AssertionError('Saved review/comparison must not dispatch')
    monkeypatch.setattr(neural_index_runtime,'compute',forbidden)
    one=review(ctx,left,[first['id'],second['id']],key='combined-review-0001').json()
    two=review(ctx,right,[second['id'],first['id']],key='combined-review-0002').json()
    assert one['status']=='passed' and set(one['index_ids'])=={a,b}
    headers,_=auth(ctx)
    result=ctx['client'].post('/v1/indexed-search-reviews/compare',headers=headers,json={'baseline_id':one['id'],'candidate_id':two['id']}).json()
    assert result['change']=='unchanged' and not result['index_changed'] and len(calls)==before
    assert ctx['client'].request('DELETE','/v1/neural-indexes/'+b,headers=headers,json={'expected_version':1,'note':'Remove second synthetic snapshot.'}).status_code==200
    assert ctx['client'].get('/v1/indexed-search-reviews/'+one['id']).json()['stale'] is True


def test_other_actor_and_workspace_cannot_query_selected_indexes(ctx,monkeypatch):
    _,_,a,b,payloads,calls=corpus(ctx,monkeypatch);before=len(calls)
    for args in [('auditor','northstar'),('owner','other')]:
        headers,_=auth(ctx,*args);headers['Idempotency-Key']='hidden-combined-query-001'
        response=ctx['client'].post('/v1/neural-indexes/search',headers=headers,json={'index_ids':[a,b],'query':'synthetic query'})
        assert response.status_code==404 and len(calls)==before


def test_global_document_diversity_and_top_k_apply_after_union(ctx,monkeypatch):
    first,second,a,b,_,_=corpus(ctx,monkeypatch)
    result=combined(ctx,[a,b],one_per_document=True,top_k=1).json()
    assert len(result['items'])==1 and result['items'][0]['document_id']==min(first['id'],second['id'])
    result=combined(ctx,[a,b],key='global-diversity-query-002',one_per_document=True,top_k=10).json()
    assert len(result['items'])==2


def test_legacy_single_index_request_fingerprint_remains_replayable(ctx,monkeypatch):
    from nexus.neural_index_runtime import SearchIndex,search_intent
    from nexus.service import canonical
    from nexus.security import digest
    first,_,a,b,_,_=corpus(ctx,monkeypatch)
    body={'index_id':a,'query':'legacy query','top_k':5,'min_score':.15,'one_per_document':False}
    assert search_intent(SearchIndex.model_validate(body))==body
    assert digest(canonical({'retrieval_mode':'local_indexed',**body}))==digest(canonical({'retrieval_mode':'local_indexed',**search_intent(SearchIndex.model_validate(body))}))


def test_eight_snapshots_are_supported_with_one_embedding_request(ctx,monkeypatch):
    doc,payloads,calls=setup(ctx,monkeypatch)
    ids=[build(ctx,doc,key='eight-index-build-'+str(i).zfill(4)).json()['index_id'] for i in range(8)]
    before=len(calls);value=combined(ctx,ids).json()
    assert value['status']=='completed' and value['index_count']==8 and value['corpus_chunks']==1
    assert len(value['items'])==1 and len(calls)==before+4


def test_combined_corpus_can_exceed_one_snapshot_without_resending_passages(ctx,monkeypatch):
    from nexus.db import DocumentChunk
    _,payloads,calls=setup(ctx,monkeypatch)
    docs=[upload(ctx,('Synthetic '+str(i)+' pump inspection. ')*400) for i in range(2)]
    ids=[build(ctx,doc,key='larger-snapshot-build-'+str(i)).json()['index_id'] for i,doc in enumerate(docs)]
    assert all(ids)
    value=combined(ctx,ids).json()
    assert value['status']=='completed' and 32<value['corpus_chunks']<=64
    assert payloads[-1]['task']=='index_query' and 'texts' not in payloads[-1]


@pytest.mark.parametrize('mismatch',['digest','dimensions'])
def test_incompatible_model_snapshots_fail_before_any_query_call(ctx,monkeypatch,mismatch):
    from test_authorized_neural_search import transport
    doc,payloads,calls=setup(ctx,monkeypatch);a=build(ctx,doc).json()['index_id']
    if mismatch=='digest':ctx['settings'].ollama_embedding_digest='2'*64
    mock,new_calls=transport(digest=ctx['settings'].ollama_embedding_digest)
    def compute(payload):
        result=neural_worker.embedding_batch(payload,transport=mock)
        if mismatch=='dimensions':result.update(dimensions=3,vectors=[[1,0,0] for _ in result['vectors']])
        return result
    monkeypatch.setattr(neural_index_runtime,'compute',compute)
    b=build(ctx,doc,key='different-model-build-001').json()['index_id'];before=len(new_calls)
    response=combined(ctx,[a,b]);assert response.status_code==409 and len(new_calls)==before
