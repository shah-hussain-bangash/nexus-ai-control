import copy
import pytest
from sqlalchemy import select, func
from conftest import auth
from test_arabic_search import upload
from test_document_lifecycle import run
from test_local_switching import current, headers, prepare, switch
from nexus.db import RetrievalCheck, Audit, User, KnowledgeDocument
from nexus.environments import assign_staging
from nexus.retrieval_checks import CheckInput, check_config
from nexus.retrieval_metrics import language_metrics
from nexus.security import digest
from nexus.service import canonical


def cases(ctx):
    en=upload(ctx,'Procurement invoices require review.')
    ar=upload(ctx,'إِدَارَة المَشْتَرَيَات موافقة')
    return {'name':'Labelled synthetic retrieval','top_k':5,'cases':[
        {'query':'procurement','expected_document_ids':[en['id']],'query_language':'English'},
        {'query':'unmatchedsyntheticpositive','expected_document_ids':[en['id']],'query_language':'English'},
        {'query':'ادارة المشتريات','expected_document_ids':[ar['id']],'query_language':'Arabic'},
        {'query':'موافقة','expectation':'no_results','query_language':'Arabic'},
        {'query':'procurement المشتريات','expected_document_ids':[en['id'],ar['id']],'query_language':'Bilingual'},
        {'query':'unmatchedsyntheticnegative','expectation':'no_results'}]}


def test_metrics_separate_languages_and_use_positive_and_negative_denominators(ctx):
    response=run(ctx,cases(ctx));assert response.status_code==201,response.text
    value=response.json();assert value['status']=='failed' and value['passed_cases']==4
    assert value['result']['mean_document_recall_at_k']==.75
    groups={g['language']:g for g in value['language_metrics']}
    assert set(groups)=={'English','Arabic','Bilingual','Unlabelled'}
    assert groups['English']=={'language':'English','case_count':2,'passed_cases':1,'retrieve_cases':2,'no_results_cases':0,
        'mean_document_recall_at_k':.5,'mean_reciprocal_rank':.5,'no_results_pass_rate':None}
    assert groups['Arabic']['mean_document_recall_at_k']==1 and groups['Arabic']['mean_reciprocal_rank']==1
    assert groups['Arabic']['no_results_pass_rate']==0 and groups['Arabic']['passed_cases']==1
    assert groups['Bilingual']['mean_document_recall_at_k']==1 and groups['Bilingual']['passed_cases']==1
    assert groups['Unlabelled']['mean_document_recall_at_k'] is None
    assert groups['Unlabelled']['mean_reciprocal_rank'] is None and groups['Unlabelled']['no_results_pass_rate']==1
    assert sum(g['case_count'] for g in groups.values())==6 and value['result']['provider_calls']==0


def test_language_labels_are_manual_and_omitted_labels_are_never_inferred(ctx):
    doc=upload(ctx,'إِدَارَة المَشْتَرَيَات')
    body={'name':'Manual language labels','cases':[{'query':'ادارة','expected_document_ids':[doc['id']]},
        {'query':'المشتريات','expected_document_ids':[doc['id']],'query_language':'English'}]}
    value=run(ctx,body).json();groups={g['language']:g for g in value['language_metrics']}
    assert set(groups)=={'English','Unlabelled'} and all(g['passed_cases']==1 for g in groups.values())
    assert 'query_language' not in value['config']['cases'][0] and 'query_language' not in value['result']['cases'][0]


def test_pre_label_fingerprint_and_explicit_null_preserve_legacy_replay(ctx,monkeypatch):
    doc=upload(ctx,'Procurement evidence')
    legacy={'name':'Legacy recovery','top_k':5,'cases':[{'query':'procurement','expected_document_ids':[doc['id']],'expectation':'retrieve'}]}
    assert check_config(CheckInput.model_validate(legacy))==legacy
    assert check_config(CheckInput.model_validate({**legacy,'cases':[{**legacy['cases'][0],'query_language':None}]}))==legacy
    first=run(ctx,legacy).json()
    with ctx['db']() as db:
        row=db.get(RetrievalCheck,first['id']);before=canonical(row.result)
        assert row.request_digest==digest(canonical(legacy)) and row.config==legacy
        audit_count=db.scalar(select(func.count()).select_from(Audit).where(Audit.event=='retrieval.checked'))
    def forbidden(*args):pytest.fail('Replaying or reading legacy evidence must not rerun retrieval')
    monkeypatch.setattr('nexus.retrieval_checks.search_documents',forbidden)
    replay=run(ctx,{**legacy,'cases':[{**legacy['cases'][0],'query_language':None}]})
    assert replay.status_code==201 and replay.json()['id']==first['id']
    assert replay.json()['language_metrics'][0]['language']=='Unlabelled'
    h,_=auth(ctx);recovered=ctx['client'].post('/v1/retrieval-checks/recover',headers=h,json={'key':'retrieval-check-key-001'})
    assert recovered.status_code==200 and recovered.json()['id']==first['id']
    with ctx['db']() as db:
        assert canonical(db.get(RetrievalCheck,first['id']).result)==before
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.event=='retrieval.checked'))==audit_count


def test_changing_language_under_a_saved_key_conflicts_and_recovery_retains_it(ctx):
    body=cases(ctx);first=run(ctx,body).json();changed=copy.deepcopy(body)
    changed['cases'][0]['query_language']='Arabic'
    response=run(ctx,changed);assert response.status_code==409
    h,_=auth(ctx);detail=ctx['client'].get('/v1/retrieval-checks/'+first['id'],headers=h).json()
    assert detail['config']['cases'][0]['query_language']=='English'
    assert detail['language_metrics']==first['language_metrics']
    second=run(ctx,changed,key='relabeled-retrieval-check')
    assert second.status_code==201 and second.json()['id']!=first['id']


@pytest.mark.parametrize('language',['French','english','',[],1,True,{'language':'Arabic'}])
def test_unknown_or_malformed_language_is_rejected(ctx,language):
    doc=upload(ctx,'Procurement evidence')
    response=run(ctx,{'name':'Invalid language','cases':[{'query':'procurement','expected_document_ids':[doc['id']],'query_language':language}]})
    assert response.status_code==422
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(RetrievalCheck))==0


def test_language_metrics_obey_account_workspace_environment_and_revoked_source_access(ctx):
    with ctx['db'].begin() as db:
        user=User(org_id='northstar',name='Synthetic engineer',email='language-engineer@test.invalid',role='engineer')
        db.add(user);db.flush();assign_staging(db,user)
    doc=upload(ctx,'إِدَارَة المَشْتَرَيَات',['engineer'])
    body={'name':'Scoped language evidence','cases':[{'query':'ادارة المشتريات','expected_document_ids':[doc['id']],'query_language':'Arabic'}]}
    response=run(ctx,body,role='engineer');assert response.status_code==201,response.text
    identifier=response.json()['id']
    auth(ctx,'auditor');assert ctx['client'].get('/v1/retrieval-checks/'+identifier).status_code==404
    auth(ctx,org='other');assert ctx['client'].get('/v1/retrieval-checks/'+identifier).status_code==404
    auth(ctx);target=prepare(ctx,key='language-sandbox');switch(ctx,target)
    assert ctx['client'].get('/v1/retrieval-checks/'+identifier,headers=headers(current(ctx))).status_code==404
    auth(ctx)
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).allowed_roles=[]
    auth(ctx,'engineer');blocked=ctx['client'].get('/v1/retrieval-checks/'+identifier)
    assert blocked.status_code==409 and 'language_metrics' not in blocked.json()


def test_group_math_does_not_average_no_result_cases_into_recall_or_rank():
    rows=[{'query_language':'Arabic','expectation':'retrieve','passed':False,'document_recall_at_k':.5,'reciprocal_rank':.25},
          {'query_language':'Arabic','expectation':'no_results','passed':True,'document_recall_at_k':None,'reciprocal_rank':0}]
    group=language_metrics(rows)[0]
    assert group['mean_document_recall_at_k']==.5 and group['mean_reciprocal_rank']==.25 and group['no_results_pass_rate']==1
    assert language_metrics([])==[]
    with pytest.raises(ValueError):language_metrics([{**rows[0],'query_language':'unknown'}])
