"""Review saved searches without model dispatch or query persistence."""
import pytest
from sqlalchemy import select,func
from conftest import auth
from test_hybrid import upload,search as direct_search
from test_neural_index_runtime import setup,build,search
from nexus.db import WorkbenchRun,KnowledgeDocument
from nexus import neural_index_runtime


def saved(ctx,monkeypatch):
    doc,payloads,_=setup(ctx,monkeypatch);index=build(ctx,doc).json()['index_id'];run=search(ctx,index).json()
    def forbidden(_):raise AssertionError('Review must not dispatch to a model')
    monkeypatch.setattr(neural_index_runtime,'compute',forbidden)
    return doc,index,run,payloads


def review(ctx,run,ids,key='saved-index-review-0001',role='owner',**changes):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/indexed-search-reviews',headers=headers,json={
        'search_id':run['id'],'expected_document_ids':ids,'note':'Reviewed synthetic expected sources.',**changes})


def test_normal_api_metrics_replay_recovery_and_no_model_execution(ctx,monkeypatch):
    doc,index,run,payloads=saved(ctx,monkeypatch)
    response=review(ctx,run,[doc['id']],query_language='Arabic',minimum_precision_percent=100)
    assert response.status_code==201,response.text
    result=response.json();assert result['status']=='passed' and not result['stale']
    assert result['measurements']['document_recall_at_k']==result['measurements']['document_precision_at_k']==result['measurements']['reciprocal_rank']==1
    assert result['review_provider_calls']==0 and result['original_search_provider_calls']==4
    assert result['labels']['query_language']=='Arabic' and 'query' not in result['labels'] and len(payloads)==2
    assert review(ctx,run,[doc['id']],query_language='Arabic',minimum_precision_percent=100).json()['id']==result['id']
    assert review(ctx,run,[doc['id']],note='Changed labels conflict.').status_code==409
    headers,_=auth(ctx)
    recovered=ctx['client'].post('/v1/indexed-search-reviews/recover',headers=headers,json={'key':'saved-index-review-0001'}).json()
    assert recovered['id']==result['id'] and len(payloads)==2
    with ctx['db']() as db:
        record=db.get(WorkbenchRun,result['id']);assert 'synthetic query kept transient' not in str(record.result)
        assert 'vectors' not in record.result and 'excerpt' not in record.result
    assert result['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


def test_negative_and_missing_expected_sources_are_measured_without_optimism(ctx,monkeypatch):
    doc,_,run,_=saved(ctx,monkeypatch);missing=upload(ctx,'Different synthetic expected source')
    positive=review(ctx,run,[doc['id'],missing['id']]).json()
    assert positive['status']=='failed' and positive['measurements']['document_recall_at_k']==.5
    negative=review(ctx,run,[],key='saved-negative-review-001',expectation='no_results').json()
    assert negative['status']=='failed' and negative['measurements']['document_precision_at_k'] is None
    # A successful empty saved result is a valid negative, rather than a failed search.
    with ctx['db'].begin() as db:
        row=db.get(WorkbenchRun,run['id']);row.result={**row.result,'hits':[]}
    assert review(ctx,run,[],key='saved-negative-review-002',expectation='no_results').json()['status']=='passed'


def test_precision_uses_complete_expected_set_not_only_recall(ctx,monkeypatch):
    doc,_,run,_=saved(ctx,monkeypatch);extra=upload(ctx,'Another synthetic retrieved source')
    from nexus.db import DocumentChunk
    with ctx['db'].begin() as db:
        chunk=db.scalar(select(DocumentChunk).where(DocumentChunk.document_id==extra['id']))
        row=db.get(WorkbenchRun,run['id']);hits=row.result['hits']+[{'document_id':extra['id'],'document_version':1,'position':chunk.position,'sha256':chunk.content_hash,'score':.5,'semantic_score':.5,'lexical_score':0}]
        row.result={**row.result,'hits':hits}
    result=review(ctx,run,[doc['id']],minimum_precision_percent=100).json()
    assert result['status']=='failed' and result['measurements']['document_recall_at_k']==1
    assert result['measurements']['document_precision_at_k']==.5 and result['measurements']['precision_threshold_passed'] is False


def test_access_revocation_filters_history_and_hides_saved_review(ctx,monkeypatch):
    doc,_,run,_=saved(ctx,monkeypatch);result=review(ctx,run,[doc['id']]).json()
    auth(ctx,'auditor');assert ctx['client'].get('/v1/indexed-search-reviews/'+result['id']).status_code==404
    assert review(ctx,run,[doc['id']],role='auditor').status_code==403
    auth(ctx,org='other');assert ctx['client'].get('/v1/indexed-search-reviews').json()['items']==[]
    headers,_=auth(ctx)
    assert ctx['client'].request('DELETE','/v1/documents/'+doc['id'],headers=headers,json={'expected_version':1,'note':'Remove synthetic review source.'}).status_code==200
    assert ctx['client'].get('/v1/indexed-search-reviews/'+result['id']).status_code==404
    assert ctx['client'].get('/v1/indexed-search-reviews').json()['items']==[]


def test_review_staleness_and_recovery_survive_index_removal(ctx,monkeypatch):
    doc,index,run,_=saved(ctx,monkeypatch);result=review(ctx,run,[doc['id']]).json();headers,_=auth(ctx)
    assert ctx['client'].request('DELETE','/v1/neural-indexes/'+index,headers=headers,json={'expected_version':1,'note':'Remove synthetic snapshot.'}).status_code==200
    ctx['settings'].ollama_embedding_enabled=0
    assert review(ctx,run,[doc['id']]).json()['stale'] is True
    assert ctx['client'].get('/v1/indexed-search-reviews/'+result['id']).json()['stale'] is True


@pytest.mark.parametrize('changes',[{'query':'Do not store this'}, {'expected_document_ids':[]}, {'expected_document_ids':['same','same']}, {'expectation':'no_results','minimum_precision_percent':50}, {'query_language':'Inferred'}, {'minimum_precision_percent':True}])
def test_invalid_or_query_bearing_reviews_are_rejected(ctx,monkeypatch,changes):
    doc,_,run,_=saved(ctx,monkeypatch)
    assert review(ctx,run,[doc['id']],**changes).status_code==422


def test_stale_failed_and_direct_searches_cannot_be_relabelled_as_index_reviews(ctx,monkeypatch):
    doc,index,run,_=saved(ctx,monkeypatch)
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).version+=1
    assert review(ctx,run,[doc['id']]).status_code==409
    direct=direct_search(ctx).json();assert review(ctx,direct,[doc['id']]).status_code==409


def test_changed_saved_run_cannot_silently_change_review_metrics(ctx,monkeypatch):
    doc,_,run,_=saved(ctx,monkeypatch);result=review(ctx,run,[doc['id']]).json()
    with ctx['db'].begin() as db:
        row=db.get(WorkbenchRun,run['id']);row.result={**row.result,'hits':[]}
    auth(ctx);assert ctx['client'].get('/v1/indexed-search-reviews/'+result['id']).status_code==409


def test_reader_revocation_hides_review_and_recovery_for_its_author(ctx,monkeypatch):
    from nexus.db import User
    from nexus.environments import assign_staging
    from test_authorized_neural_search import configure,transport
    from nexus import neural_worker
    configure(ctx);doc=upload(ctx,'Synthetic source with revocable reviewer access',['engineer'])
    with ctx['db'].begin() as db:
        user=User(id='review-engineer',org_id='northstar',email='review@test.invalid',name='Synthetic reviewer',role='engineer',password_hash='not-a-login-hash')
        db.add(user);db.flush();assign_staging(db,user)
    mock,calls=transport();monkeypatch.setattr(neural_index_runtime,'compute',lambda payload:neural_worker.embedding_batch(payload,transport=mock))
    index=build(ctx,doc,role='engineer').json()['index_id']
    headers,_=auth(ctx,'engineer');headers['Idempotency-Key']='engineer-index-query-001'
    run=ctx['client'].post('/v1/neural-indexes/search',headers=headers,json={'index_id':index,'query':'synthetic approved source'}).json()
    ctx['settings'].ollama_embedding_enabled=0
    result=review(ctx,run,[doc['id']],role='engineer').json();assert result['status']=='passed' and len(calls)==8
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Revoke synthetic reviewer access.'}).status_code==200
    assert ctx['client'].get('/v1/indexed-search-reviews/'+result['id']).json()['stale'] is True
    headers,_=auth(ctx,'engineer')
    assert ctx['client'].get('/v1/indexed-search-reviews/'+result['id']).status_code==404
    assert ctx['client'].get('/v1/indexed-search-reviews').json()['items']==[]
    assert ctx['client'].post('/v1/indexed-search-reviews/recover',headers=headers,json={'key':'saved-index-review-0001'}).status_code==404
    assert len(calls)==8


def test_changed_source_marks_saved_review_stale_and_blocks_new_measurement(ctx,monkeypatch):
    doc,_,run,_=saved(ctx,monkeypatch);result=review(ctx,run,[doc['id']]).json()
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).version+=1
    auth(ctx);assert ctx['client'].get('/v1/indexed-search-reviews/'+result['id']).json()['stale'] is True
    assert review(ctx,run,[doc['id']],key='stale-new-review-0001').status_code==409
