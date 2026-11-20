import copy
import pytest
from sqlalchemy import select, func
from conftest import auth
from test_arabic_search import upload
from test_document_lifecycle import run, replace
from test_retrieval_precision import body
from test_local_switching import current, headers, prepare, switch
from nexus.db import RetrievalCheck, Audit, KnowledgeDocument, User
from nexus.environments import assign_staging
from nexus.service import canonical
from nexus.retrieval_comparison import classify


def compare(ctx, before, after, role='owner'):
    h,_=auth(ctx,role)
    return ctx['client'].post('/v1/retrieval-checks/compare',headers=h,json={'baseline_id':before['id'],'candidate_id':after['id']})


def pair(ctx):
    doc=upload(ctx,'Procurement approved invoice policy')
    request=body(doc['id']);first=run(ctx,request).json()
    second=run(ctx,{**request,'name':'Later matching suite'},key='comparison-second-key').json()
    return first,second


@pytest.mark.parametrize('values,expected',[([0,0],'unchanged'),([1,0],'improved'),([-1,0],'regressed'),([1,-1],'mixed'),([None,0],'unchanged')])
def test_direction(values,expected):assert classify(values)==expected


def test_new_unlisted_source_detects_regression_even_when_both_suites_pass(ctx):
    doc=upload(ctx,'Procurement approved invoice policy');request=body(doc['id'])
    first=run(ctx,request).json();upload(ctx,'Procurement unlisted training memo')
    second=run(ctx,{**request,'name':'After source change'},key='comparison-second-key').json()
    response=compare(ctx,first,second);assert response.status_code==200,response.text
    value=response.json();assert value['case_changes']=={'improved':0,'regressed':1,'mixed':0,'unchanged':0}
    assert value['baseline']['status']==value['candidate']['status']=='passed'
    assert value['baseline']['stale'] and not value['candidate']['stale'] and value['corpus_changed']
    assert value['delta']['mean_document_precision_at_k']==-.5 and value['delta']['passed_cases']==0
    case=value['cases'][0];assert case['returned_sources_changed'] and case['delta']['unexpected_document_count']==1
    assert not any(key in response.text for key in ['procurement','retrieved_document_ids','expected_document_ids','citations','idem_key'])


def test_source_replacement_improves_precision_and_retains_negative_case_na(ctx):
    doc=upload(ctx,'Procurement approved invoice policy');extra=upload(ctx,'Procurement unlisted training memo')
    request=body(doc['id']);request['cases'].append({'query':'missingwordsynthetic','expectation':'no_results'})
    first=run(ctx,request).json();assert replace(ctx,extra['id'],text='Garden flowers').status_code==200
    second=run(ctx,request,key='comparison-second-key').json();response=compare(ctx,first,second)
    assert response.status_code==200,response.text
    value=response.json();assert value['case_changes']['improved']==1 and value['case_changes']['unchanged']==1
    assert value['delta']['mean_document_precision_at_k']==.5
    assert value['cases'][1]['baseline']['document_precision_at_k'] is None


def test_comparison_does_not_rerun_or_persist_evidence_and_names_can_differ(ctx,monkeypatch):
    first,second=pair(ctx)
    def state():
        with ctx['db']() as db:
            return ([canonical(row.result) for row in db.scalars(select(RetrievalCheck).order_by(RetrievalCheck.id)).all()],
                db.scalar(select(func.count()).select_from(Audit)))
    before=state()
    def forbidden(*args):pytest.fail('Comparison must use saved measurements')
    monkeypatch.setattr('nexus.retrieval_checks.search_documents',forbidden)
    response=compare(ctx,first,second);assert response.status_code==200,response.text
    assert response.json()['case_changes']['unchanged']==1 and state()==before


@pytest.mark.parametrize('change',['query','order','top_k','sources','language','target'])
def test_definition_changes_are_rejected(ctx,change):
    doc=upload(ctx,'Procurement approved invoice policy');other=upload(ctx,'Procurement other source')
    request=body(doc['id']);request['cases'].append({'query':'missingwordsynthetic','expectation':'no_results'})
    first=run(ctx,request).json();changed=copy.deepcopy(request)
    if change=='query':changed['cases'][0]['query']='invoice'
    if change=='order':changed['cases'].reverse()
    if change=='top_k':changed['top_k']=4
    if change=='sources':changed['cases'][0]['expected_document_ids']=[other['id']]
    if change=='language':changed['cases'][0]['query_language']='Arabic'
    if change=='target':changed['cases'][0]['minimum_precision_percent']=50
    second=run(ctx,changed,key='comparison-second-key').json();response=compare(ctx,first,second)
    assert response.status_code==409 and response.json()['error']['code']=='COMPARISON_DEFINITION_CHANGED'


def test_expected_source_order_and_optional_nulls_do_not_change_definition(ctx):
    firstdoc=upload(ctx,'Procurement approved invoice policy');secondoc=upload(ctx,'Procurement second policy')
    request=body(firstdoc['id']);request['cases'][0]['expected_document_ids'].append(secondoc['id'])
    first=run(ctx,request).json();changed=copy.deepcopy(request)
    changed['cases'][0]['expected_document_ids'].reverse();changed['cases'][0]['minimum_precision_percent']=None
    second=run(ctx,changed,key='comparison-second-key').json()
    assert compare(ctx,first,second).status_code==200


def test_comparison_requires_two_existing_records_and_csrf(ctx):
    first,second=pair(ctx)
    payload={'baseline_id':first['id'],'candidate_id':second['id']}
    assert ctx['client'].post('/v1/retrieval-checks/compare',json=payload).status_code==403
    assert compare(ctx,first,first).status_code==422
    assert compare(ctx,first,{'id':'missing'}).status_code==404
    ctx['client'].cookies.clear()
    assert ctx['client'].post('/v1/retrieval-checks/compare',json=payload).status_code==401


def test_account_workspace_environment_and_recorded_role_are_checked(ctx):
    first,second=pair(ctx)
    assert compare(ctx,first,second,role='auditor').status_code==404
    h,_=auth(ctx,org='other')
    assert ctx['client'].post('/v1/retrieval-checks/compare',headers=h,json={'baseline_id':first['id'],'candidate_id':second['id']}).status_code==404
    auth(ctx);target=prepare(ctx,key='comparison-sandbox');switch(ctx,target)
    assert ctx['client'].post('/v1/retrieval-checks/compare',headers=headers(current(ctx)),json={'baseline_id':first['id'],'candidate_id':second['id']}).status_code==404


def test_owner_cannot_compare_another_authors_records(ctx):
    with ctx['db'].begin() as db:
        user=User(org_id='northstar',name='Synthetic engineer',email='comparison@test.invalid',role='engineer')
        db.add(user);db.flush();assign_staging(db,user)
    doc=upload(ctx,'Procurement approved invoice policy',['engineer']);request=body(doc['id'])
    first=run(ctx,request,role='engineer').json();second=run(ctx,request,key='comparison-second-key',role='engineer').json()
    assert compare(ctx,first,second).status_code==404
    assert compare(ctx,first,second,role='engineer').status_code==200
    with ctx['db'].begin() as db:
        row=db.get(RetrievalCheck,first['id']);row.result={**row.result,'actor_role':'owner'}
    response=compare(ctx,first,second,role='engineer')
    assert response.status_code==409 and response.json()['error']['code']=='COMPARISON_ROLE_CHANGED'


@pytest.mark.parametrize('change',['delete','revoke'])
def test_referenced_unlisted_sources_cannot_bypass_current_permissions(ctx,change):
    with ctx['db'].begin() as db:
        user=User(org_id='northstar',name='Synthetic engineer',email='comparison@test.invalid',role='engineer')
        db.add(user);db.flush();assign_staging(db,user)
    doc=upload(ctx,'Procurement approved invoice policy',['engineer']);extra=upload(ctx,'Procurement unlisted source',['engineer'])
    request=body(doc['id']);first=run(ctx,request,role='engineer').json();second=run(ctx,request,key='comparison-second-key',role='engineer').json()
    with ctx['db'].begin() as db:
        source=db.get(KnowledgeDocument,extra['id'])
        if change=='delete':source.status='deleted'
        else:source.allowed_roles=[]
    response=compare(ctx,first,second,role='engineer');assert response.status_code==409
    assert 'case_changes' not in response.text and doc['id'] not in response.text


def test_method_change_is_explicit_and_does_not_rewrite_history(ctx):
    first,second=pair(ctx)
    with ctx['db'].begin() as db:
        row=db.get(RetrievalCheck,first['id']);row.result={**row.result,'normalization_version':'older-synthetic-version'}
    response=compare(ctx,first,second);assert response.status_code==200
    assert response.json()['normalization_changed'] and response.json()['baseline']['stale']


@pytest.mark.parametrize('change',['count','score','query','passed','source_reference'])
def test_corrupt_saved_results_fail_closed(ctx,change):
    first,second=pair(ctx)
    with ctx['db'].begin() as db:
        row=db.get(RetrievalCheck,first['id']);result=copy.deepcopy(row.result)
        if change=='count':result['passed_cases']=0
        if change=='score':result['cases'][0]['document_recall_at_k']=2
        if change=='query':result['cases'][0]['query']='Different saved query'
        if change=='passed':result['cases'][0]['passed']='yes'
        if change=='source_reference':result['cases'][0]['retrieved_document_ids'].append('unrecorded-source')
        row.result=result
    response=compare(ctx,first,second);assert response.status_code==409,response.text
    assert response.json()['error']['code']=='EVIDENCE_FORMAT_UNSUPPORTED'
