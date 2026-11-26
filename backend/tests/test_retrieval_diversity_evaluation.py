"""Persisted quality checks pin document diversity without relabelling legacy runs."""
import copy
import pytest
from conftest import auth
from test_lexical_source_diversity import upload
from test_document_lifecycle import run
from test_retrieval_comparison import compare
from nexus.db import RetrievalCheck,User
from nexus.environments import assign_staging
from nexus.retrieval_checks import CheckInput,check_config
from nexus.security import digest
from nexus.service import canonical

def suite(ids,**changes):
    return {'name':'Diversity test suite','top_k':2,'cases':[{'query':'needle','expected_document_ids':ids,'query_language':'Bilingual'}],**changes}

def test_mode_is_measured_and_saved_while_default_hash_remains_legacy(ctx):
    first=upload(ctx,'needle '*650);second=upload(ctx,'needle '+'unrelated '*70)
    body=suite([first['id'],second['id']])
    legacy=run(ctx,body);assert legacy.status_code==201,legacy.text
    old=legacy.json();assert old['result']['one_per_document'] is False and old['passed_cases']==0
    expected=copy.deepcopy(body);expected['cases'][0]['expectation']='retrieve'
    assert check_config(CheckInput.model_validate(body))==expected
    assert check_config(CheckInput.model_validate({**body,'one_per_document':False}))==expected
    with ctx['db']() as db:assert db.get(RetrievalCheck,old['id']).request_digest==digest(canonical(expected))
    new=run(ctx,{**body,'one_per_document':True},key='diversity-mode-new-001')
    assert new.status_code==201,new.text
    value=new.json();assert value['passed_cases']==1 and value['config']['one_per_document'] is True
    assert value['result']['one_per_document'] is True and value['result']['provider_calls']==0
    assert value['result']['cases'][0]['retrieved_document_ids']==[first['id'],second['id']]
    assert ctx['client'].get('/v1/retrieval-checks/'+value['id']).json()['result']['one_per_document'] is True
    # Changing the mode cannot replay an existing request key.
    assert run(ctx,{**body,'one_per_document':True}).status_code==409
    assert run(ctx,{**body,'one_per_document':False}).json()['id']==old['id']

def test_matching_mode_comparison_and_mixed_mode_rejection(ctx):
    doc=upload(ctx,'needle indexed source')
    body=suite([doc['id']],one_per_document=True)
    a=run(ctx,body).json();b=run(ctx,{**body,'name':'Later same-mode check'},key='diversity-compare-key').json()
    response=compare(ctx,a,b);assert response.status_code==200,response.text
    value=response.json();assert value['baseline']['one_per_document'] is value['candidate']['one_per_document'] is True
    other=run(ctx,suite([doc['id']]),key='diversity-default-mode').json()
    response=compare(ctx,a,other);assert response.status_code==409
    assert response.json()['error']['code']=='COMPARISON_DEFINITION_CHANGED'

@pytest.mark.parametrize('defined,measured',[(True,None),(True,False),(False,True),(False,1),('true',True)])
def test_saved_mode_tampering_fails_closed(ctx,defined,measured):
    doc=upload(ctx,'needle indexed source');saved=run(ctx,suite([doc['id']])).json()
    with ctx['db'].begin() as db:
        row=db.get(RetrievalCheck,saved['id']);row.config={**row.config,'one_per_document':defined}
        result={**row.result}
        if measured is None:result.pop('one_per_document',None)
        else:result['one_per_document']=measured
        row.result=result
    response=ctx['client'].get('/v1/retrieval-checks/'+saved['id'])
    assert response.status_code==409 and response.json()['error']['code']=='EVIDENCE_FORMAT_UNSUPPORTED'

def test_legacy_missing_fields_stay_passage_mode_and_acl_is_rechecked(ctx):
    with ctx['db'].begin() as db:
        user=User(id='synthetic-evaluator',org_id='northstar',email='evaluator@test.invalid',name='Synthetic evaluator',role='engineer',password_hash='not-a-login-hash')
        db.add(user);db.flush();assign_staging(db,user)
    doc=upload(ctx,'needle shared source',['engineer']);body=suite([doc['id']])
    saved=run(ctx,body,role='engineer').json()
    with ctx['db'].begin() as db:
        row=db.get(RetrievalCheck,saved['id']);result={**row.result};result.pop('one_per_document');row.result=result
    assert ctx['client'].get('/v1/retrieval-checks/'+saved['id']).status_code==200
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Revoke synthetic evaluator access.'}).status_code==200
    auth(ctx,'engineer');assert ctx['client'].get('/v1/retrieval-checks/'+saved['id']).status_code==409

@pytest.mark.parametrize('mode',[1,0,'true','false',None,[]])
def test_mode_requires_a_json_boolean(ctx,mode):
    result=run(ctx,suite(['unreadable-source'],one_per_document=mode))
    assert result.status_code==422
