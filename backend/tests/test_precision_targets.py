import copy
import pytest
from sqlalchemy import select, func
from conftest import auth
from test_arabic_search import upload
from test_document_lifecycle import run
from test_retrieval_precision import sample
from nexus.db import RetrievalCheck
from nexus.retrieval_checks import CheckInput, check_config
from nexus.retrieval_metrics import measure_case
from nexus.service import canonical
from nexus.security import digest


def dataset(ctx):
    expected=upload(ctx,'Procurement approved invoice policy')
    extra=upload(ctx,'Procurement unlisted training memo')
    return expected,extra


def body(identifier,minimum=None):
    case={'query':'procurement','expected_document_ids':[identifier],'query_language':'English'}
    if minimum is not None:case['minimum_precision_percent']=minimum
    return {'name':'Optional precision target','top_k':5,'cases':[case]}


@pytest.mark.parametrize('minimum,passed',[(0,True),(49,True),(50,True),(51,False),(100,False)])
def test_opted_target_changes_case_and_suite_status_without_changing_recall(ctx,minimum,passed):
    expected,extra=dataset(ctx);response=run(ctx,body(expected['id'],minimum));assert response.status_code==201,response.text
    value=response.json();case=value['result']['cases'][0]
    assert case['document_precision_at_k']==.5 and case['document_recall_at_k']==1
    assert case['minimum_precision_percent']==minimum and case['precision_threshold_passed'] is passed
    assert case['passed'] is passed and value['result']['all_cases_passed'] is passed
    assert value['status']==('passed' if passed else 'failed')
    assert value['language_metrics'][0]['passed_cases']==int(passed)
    assert case['unexpected_document_ids']==[extra['id']]
    with ctx['db']() as db:
        row=db.get(RetrievalCheck,value['id'])
        assert row.config['cases'][0]['minimum_precision_percent']==minimum
        assert row.result['cases'][0]['precision_threshold_passed'] is passed


def test_unset_and_null_targets_keep_legacy_fingerprint_and_replay_without_reranking(ctx,monkeypatch):
    expected,_=dataset(ctx);old=check_config(CheckInput.model_validate(body(expected['id'])))
    first=run(ctx,old).json();assert first['status']=='passed'
    explicit=copy.deepcopy(old);explicit['cases'][0]['minimum_precision_percent']=None
    assert check_config(CheckInput.model_validate(explicit))==old
    with ctx['db']() as db:
        row=db.get(RetrievalCheck,first['id']);before=canonical(row.result)
        assert row.request_digest==digest(canonical(old))
        assert 'minimum_precision_percent' not in row.config['cases'][0]
    def forbidden(*args):pytest.fail('Legacy replay must not rerank')
    monkeypatch.setattr('nexus.retrieval_checks.search_documents',forbidden)
    replay=run(ctx,explicit);assert replay.status_code==201 and replay.json()['id']==first['id']
    assert replay.json()['status']=='passed' and 'precision_threshold_passed' not in replay.json()['result']['cases'][0]
    with ctx['db']() as db:assert canonical(db.get(RetrievalCheck,first['id']).result)==before


def test_changing_target_requires_new_intent_and_recovery_retains_the_original(ctx):
    expected,_=dataset(ctx);old=body(expected['id']);first=run(ctx,old).json()
    assert run(ctx,body(expected['id'],100)).status_code==409
    strict=run(ctx,body(expected['id'],100),key='precision-target-strict-001')
    assert strict.status_code==201 and strict.json()['status']=='failed'
    h,_=auth(ctx);recovered=ctx['client'].post('/v1/retrieval-checks/recover',headers=h,json={'key':'retrieval-check-key-001'})
    assert recovered.status_code==200 and recovered.json()['id']==first['id'] and recovered.json()['status']=='passed'
    assert run(ctx,body(expected['id'],50),key='precision-target-strict-001').status_code==409


@pytest.mark.parametrize('minimum',[-1,101,50.5,50.0,True,False,'50',[],{},'NaN'])
def test_invalid_targets_are_rejected_before_any_record_is_created(ctx,minimum):
    expected=upload(ctx,'Procurement approved invoice policy')
    response=run(ctx,body(expected['id'],minimum))
    assert response.status_code==422
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(RetrievalCheck))==0


@pytest.mark.parametrize('minimum',[0,50,100])
def test_negative_cases_cannot_enable_a_precision_target(ctx,minimum):
    response=run(ctx,{'name':'Negative target','cases':[{'query':'unknownsyntheticword','expectation':'no_results','minimum_precision_percent':minimum}]})
    assert response.status_code==422


@pytest.mark.parametrize('minimum,expected',[(33,True),(34,False)])
def test_target_decisions_use_integer_counts_not_rounded_scores(minimum,expected):
    case={**sample(['a'],['a','x','y']),'minimum_precision_percent':minimum}
    measured=measure_case(case)
    assert measured['document_precision_at_k']==pytest.approx(1/3)
    assert measured['precision_threshold_passed'] is expected


@pytest.mark.parametrize('minimum,flag',[(0,True),(100,False)])
def test_empty_positive_results_never_pass_missing_source_expectation(ctx,minimum,flag):
    expected=upload(ctx,'Procurement approved invoice policy')
    request=body(expected['id'],minimum);request['cases'][0]['query']='missingwordsynthetic'
    response=run(ctx,request);assert response.status_code==201
    case=response.json()['result']['cases'][0]
    assert case['document_precision_at_k']==0 and case['precision_threshold_passed'] is flag
    assert not case['passed'] and response.json()['status']=='failed'


def test_derived_target_flag_is_recomputed_and_does_not_mutate_saved_case():
    case={**sample(['a'],['a','a','x']),'minimum_precision_percent':51,'precision_threshold_passed':True}
    before=copy.deepcopy(case);assert not measure_case(case)['precision_threshold_passed'] and case==before
    no_target={**sample(['a'],['a']),'precision_threshold_passed':True}
    assert 'precision_threshold_passed' not in measure_case(no_target)
