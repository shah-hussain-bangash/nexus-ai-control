import hashlib
import pytest
from sqlalchemy import select
from conftest import auth
from test_hybrid import upload, search
from nexus.db import WorkbenchRun, KnowledgeDocument
from nexus.hybrid import Search, compute
from nexus.hybrid_worker import rank
from nexus.service import canonical


def payload(**changes):
    return {'texts':['pump pump pump','pump pump pump','pump spare'],'query':'pump','dimensions':2,
        'semantic_weight':0,'min_score':0,'top_k':2,'groups':[0,0,1],**changes}


def corpus(ctx,roles=None):
    return [upload(ctx,('pump '*160).strip(),roles),upload(ctx,'pump spare',roles)]


def test_diversity_keeps_best_chunk_per_document_without_changing_scores():
    ordinary=rank(payload());distinct=rank(payload(one_per_document=True))
    assert [r['position'] for r in ordinary['scores']]==[0,1]
    assert [r['position'] for r in distinct['scores']]==[0,2]
    all_scores=rank(payload(top_k=3))['scores']
    assert distinct['scores']==[all_scores[0],all_scores[2]]
    assert rank(payload(one_per_document=True,groups=[0,0,0]))['scores']==[all_scores[0]]


@pytest.mark.parametrize('groups',[None,[],[0,1],[True,0,1],[-1,0,1],[20,0,1],['zero',0,1]])
def test_worker_rejects_invalid_requested_document_groups(groups):
    with pytest.raises(ValueError,match='RANKING_FAILED'):rank(payload(one_per_document=True,groups=groups))


def test_real_child_process_honors_document_grouping():
    result=compute(payload(one_per_document=True))
    assert [r['position'] for r in result['scores']]==[0,2]


def test_api_records_diversity_mode_and_retains_legacy_default_fingerprint(ctx,monkeypatch):
    corpus(ctx);monkeypatch.setattr('nexus.hybrid.compute',rank)
    old=search(ctx,query='pump',semantic_weight=0,min_score=0,top_k=2).json()
    assert len(old['items'])==2 and len({r['document_id'] for r in old['items']})==1
    expected=Search(query='pump',dimensions=2,semantic_weight=0,min_score=0,top_k=2).model_dump();expected.pop('one_per_document')
    with ctx['db']() as db:assert db.get(WorkbenchRun,old['id']).result['fingerprint']==hashlib.sha256(canonical(expected).encode()).hexdigest()
    assert search(ctx,query='pump',semantic_weight=0,min_score=0,top_k=2,one_per_document=False).json()['id']==old['id']
    assert search(ctx,query='pump',semantic_weight=0,min_score=0,top_k=2,one_per_document=True).status_code==409
    response=search(ctx,query='pump',semantic_weight=0,min_score=0,top_k=2,one_per_document=True,key='source-diversity-new-key')
    assert response.status_code==201,response.text
    value=response.json();assert value['status']=='completed' and len(value['items'])==2
    assert len({r['document_id'] for r in value['items']})==2 and value['parameters']['one_per_document'] is True
    assert value['provider_calls']==0
    h,_=auth(ctx)
    recovered=ctx['client'].post('/v1/hybrid-search/recover',headers=h,json={'key':'source-diversity-new-key'})
    assert recovered.status_code==200 and recovered.json()['id']==value['id']
    assert recovered.json()['parameters']['one_per_document'] is True


def test_parent_refuses_worker_results_that_repeat_a_document(ctx,monkeypatch):
    corpus(ctx)
    monkeypatch.setattr('nexus.hybrid.compute',lambda p:rank({**p,'one_per_document':False}))
    value=search(ctx,query='pump',semantic_weight=0,min_score=0,top_k=2,one_per_document=True).json()
    assert value['status']=='failed' and value['error_code']=='RANKING_FAILED' and value['items']==[]


def test_acl_filtering_and_history_revocation_apply_to_diverse_searches(ctx,monkeypatch):
    docs=corpus(ctx,['auditor']);private=upload(ctx,'pump secret-private-source')
    captured=[]
    def compute_locally(p):captured.append(p);return rank(p)
    monkeypatch.setattr('nexus.hybrid.compute',compute_locally)
    h,_=auth(ctx,'auditor');h['Idempotency-Key']='auditor-diverse-search-01'
    response=ctx['client'].post('/v1/hybrid-search',headers=h,json={'query':'pump','semantic_weight':0,'min_score':0,'top_k':2,'one_per_document':True})
    assert response.status_code==201,response.text
    value=response.json();assert {hit['document_id'] for hit in value['items']}=={d['id'] for d in docs}
    assert private['id'] not in str(value['items']) and 'secret-private-source' not in str(captured)
    assert len(captured[0]['groups'])==len(captured[0]['texts'])
    with ctx['db'].begin() as db:
        for doc in docs:db.get(KnowledgeDocument,doc['id']).allowed_roles=[]
    history=ctx['client'].get('/v1/hybrid-search/history/'+value['id']).json()
    assert history['items']==[] and history['withheld_stale_or_inaccessible']==2


def test_source_revision_change_during_diverse_ranking_fails_closed(ctx,monkeypatch):
    docs=corpus(ctx)
    def changed(p):
        result=rank(p)
        with ctx['db'].begin() as db:db.get(KnowledgeDocument,docs[0]['id']).version+=1
        return result
    monkeypatch.setattr('nexus.hybrid.compute',changed)
    value=search(ctx,query='pump',one_per_document=True).json()
    assert value['status']=='failed' and value['error_code']=='SOURCE_SCOPE_CHANGED' and not value['items']


@pytest.mark.parametrize('value',[1,'true',None])
def test_public_option_requires_a_boolean_and_cannot_supply_worker_groups(ctx,value):
    assert search(ctx,one_per_document=value).status_code==422
    assert search(ctx,one_per_document=True,groups=[0]).status_code==422


def test_mode_does_not_store_query_text_or_internal_grouping(ctx,monkeypatch):
    corpus(ctx);monkeypatch.setattr('nexus.hybrid.compute',rank)
    value=search(ctx,query='pump private-query-sentinel',one_per_document=True).json()
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,value['id']).result
        assert 'private-query-sentinel' not in str(saved) and 'groups' not in saved
    assert ctx['client'].get('/v1/hybrid-search/capabilities').json()['one_per_document_supported'] is True
