import copy
import pytest
from sqlalchemy import select
from conftest import auth
from test_arabic_search import upload
from test_document_lifecycle import run
from test_local_switching import current, headers, prepare, switch
from nexus.db import KnowledgeDocument, RetrievalCheck, User
from nexus.environments import assign_staging
from nexus.retrieval_metrics import measure_case, result_with_precision, language_metrics
from nexus.service import canonical


def sample(expected,returned,expectation='retrieve',language=None):
    return {'expectation':expectation,'expected_document_ids':expected,'retrieved_document_ids':returned,
        'passed':True,'query_language':language,'document_recall_at_k':1 if expectation=='retrieve' else None,'reciprocal_rank':1}


@pytest.mark.parametrize('expected,returned,precision,unexpected',[
    (['a'],['a'],1,[]),(['a'],['a','x'],.5,['x']),(['a'],['x'],0,['x']),
    (['a'],[],0,[]),(['a','b'],['a','a','x','x'],.5,['x']),
    (['a','a'],['a'],1,[]),(['a','b'],['a'],1,[]),
])
def test_precision_counts_distinct_returned_documents_and_preserves_order(expected,returned,precision,unexpected):
    row=sample(expected,returned);before=copy.deepcopy(row);measured=measure_case(row)
    assert measured['document_precision_at_k']==precision and measured['unexpected_document_ids']==unexpected
    assert measured['retrieved_document_count']==len(set(returned))
    assert measured['matched_expected_document_count']==len(set(expected).intersection(returned))
    assert row==before and measured is not row


@pytest.mark.parametrize('returned',[[],['x','x','y']])
def test_negative_cases_have_no_precision_but_preserve_unlisted_sources(returned):
    result=measure_case(sample([],returned,'no_results'))
    assert result['document_precision_at_k'] is None
    assert result['unexpected_document_ids']==list(dict.fromkeys(returned))


def test_precision_means_exclude_negatives_and_empty_positive_results_count_as_zero():
    rows=[sample(['a'],['a','x'],language='English'),sample(['a'],[],language='English'),
        sample([],[],'no_results','English'),sample(['b'],['b'],language='Arabic')]
    original={'cases':rows,'all_cases_passed':True};before=copy.deepcopy(original)
    result=result_with_precision(original)
    assert result['mean_document_precision_at_k']==.5 and original==before
    grouped={g['language']:g for g in language_metrics(result['cases'])}
    assert grouped['English']['mean_document_precision_at_k']==.25
    assert grouped['Arabic']['mean_document_precision_at_k']==1
    assert result_with_precision({'cases':[sample([],[],'no_results')]})['mean_document_precision_at_k'] is None


def body(identifier,language='English'):
    return {'name':'Precision review','top_k':5,'cases':[{'query':'procurement','expected_document_ids':[identifier],
        'query_language':language}]}


def test_extra_sources_reduce_precision_even_when_all_expected_sources_are_found(ctx):
    expected=upload(ctx,'Procurement approved invoice policy')
    extra=upload(ctx,'Procurement unlisted training memo')
    response=run(ctx,body(expected['id']));assert response.status_code==201,response.text
    value=response.json();case=value['result']['cases'][0]
    assert value['status']=='passed' and value['result']['mean_document_recall_at_k']==1
    assert value['result']['mean_document_precision_at_k']==.5
    assert case['unexpected_document_ids']==[extra['id']] and case['retrieved_document_count']==2
    assert value['language_metrics'][0]['mean_document_precision_at_k']==.5
    assert 'excerpt' not in str(value['result']) and value['result']['provider_calls']==0


def test_historical_metrics_are_derived_without_rerun_or_stored_json_changes(ctx,monkeypatch):
    expected=upload(ctx,'Procurement approved invoice policy');upload(ctx,'Procurement unlisted training memo')
    first=run(ctx,body(expected['id'])).json();identifier=first['id']
    with ctx['db'].begin() as db:
        row=db.get(RetrievalCheck,identifier)
        # Any cached precision fields are overridden by the saved source identifiers.
        row.result={**row.result,'mean_document_precision_at_k':1,
            'cases':[{**case,'document_precision_at_k':1,'unexpected_document_ids':[]} for case in row.result['cases']]}
    with ctx['db']() as db:before=canonical(db.get(RetrievalCheck,identifier).result)
    def forbidden(*args):pytest.fail('Historical precision must not rerun retrieval')
    monkeypatch.setattr('nexus.retrieval_checks.search_documents',forbidden)
    response=ctx['client'].get('/v1/retrieval-checks/'+identifier)
    assert response.status_code==200 and response.json()['result']['mean_document_precision_at_k']==.5
    replay=run(ctx,body(expected['id']))
    assert replay.status_code==201 and replay.json()['id']==identifier
    assert replay.json()['result']['cases'][0]['document_precision_at_k']==.5
    with ctx['db']() as db:assert canonical(db.get(RetrievalCheck,identifier).result)==before


@pytest.mark.parametrize('change',['revoke','delete'])
def test_unlisted_sources_still_obey_current_access_and_deletion_checks(ctx,change):
    with ctx['db'].begin() as db:
        user=User(org_id='northstar',name='Synthetic engineer',email='precision@test.invalid',role='engineer')
        db.add(user);db.flush();assign_staging(db,user)
    expected=upload(ctx,'Procurement approved invoice policy',['engineer'])
    extra=upload(ctx,'Procurement unlisted training memo',['engineer'])
    first=run(ctx,body(expected['id']),role='engineer').json()
    assert first['result']['cases'][0]['unexpected_document_ids']==[extra['id']]
    auth(ctx)
    with ctx['db'].begin() as db:
        row=db.get(KnowledgeDocument,extra['id'])
        if change=='revoke':row.allowed_roles=[]
        else:row.status='deleted'
    auth(ctx,'engineer');response=ctx['client'].get('/v1/retrieval-checks/'+first['id'])
    assert response.status_code==409 and 'unexpected_document_ids' not in response.text and 'document_precision' not in response.text


def test_precision_detail_stays_scoped_to_account_workspace_and_selected_environment(ctx):
    expected=upload(ctx,'Procurement approved invoice policy')
    first=run(ctx,body(expected['id'])).json();identifier=first['id']
    auth(ctx,'auditor');assert ctx['client'].get('/v1/retrieval-checks/'+identifier).status_code==404
    auth(ctx,org='other');assert ctx['client'].get('/v1/retrieval-checks/'+identifier).status_code==404
    auth(ctx);target=prepare(ctx,key='precision-sandbox');switch(ctx,target)
    response=ctx['client'].get('/v1/retrieval-checks/'+identifier,headers=headers(current(ctx)))
    assert response.status_code==404
