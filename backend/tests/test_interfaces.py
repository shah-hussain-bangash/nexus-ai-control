import copy
import pytest
from sqlalchemy import select,func
from conftest import auth
from nexus.interfaces import catalog,Blueprint
from nexus.readiness import GATES
from nexus.db import WorkspaceAsset,WorkbenchRun,Action,InferenceCall,ReadinessEvidence,User


def payload(spec):
    return {'kind':'blueprint','name':spec['sample_name'],'description':spec['description'],'config':{'module':spec['id'],'values':{f['id']:copy.deepcopy(f['default']) for f in spec['fields']},'phase':'planned','ui_checks':{},'surface_rows':[]}}


def create(ctx,spec):
    headers,_=auth(ctx)
    response=ctx['client'].post('/v1/workbench',headers=headers,json=payload(spec))
    assert response.status_code==201,response.text
    return headers,response.json()


def test_all_roadmap_modules_have_complete_interface_contracts(ctx):
    assert ctx['client'].get('/v1/interface-catalog').status_code==401
    auth(ctx);data=ctx['client'].get('/v1/interface-catalog').json()
    assert {m['id'] for m in data['modules']}=={g[0] for g in GATES}
    assert len(data['modules'])==18
    assert sum(len(m['fields']) for m in data['modules'])==161
    assert sum(len(m['actions']) for m in data['modules'])==54
    for spec in data['modules']:
        assert len(spec['stages'])==6 and len(spec['criteria'])==4 and len(spec['record_columns'])==4
        assert all(a['implementation']=='planned_contract' and a['path'].startswith('/v1/planned/') for a in spec['actions'])
        assert not any(f['type']=='password' for f in spec['fields'])


@pytest.mark.parametrize('module_id',[m['id'] for m in catalog()['modules']])
def test_each_module_persists_and_previews_without_runtime_effects(ctx,module_id):
    spec=next(m for m in catalog()['modules'] if m['id']==module_id)
    headers,row=create(ctx,spec)
    result=ctx['client'].post('/v1/workbench/'+row['id']+'/run',headers=headers,json={'variables':{'design_action':spec['actions'][0]['id'],'design_scenario':'dependency_unavailable'}})
    assert result.status_code==200,result.text
    preview=result.json()['result'];assert len(preview['steps'])==6 and preview['steps'][2]['status']=='simulated_stop'
    assert preview['provider_calls']==0 and preview['business_effects']==0 and not preview['runtime_activated']
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(Action))==0
        assert db.scalar(select(func.count()).select_from(InferenceCall))==0
        assert db.scalar(select(func.count()).select_from(ReadinessEvidence))==0


def test_interface_examples_are_opt_in_additive_and_idempotent(ctx):
    h,_=auth(ctx)
    first=ctx['client'].post('/v1/interface-starter',headers=h).json();assert first['created']==18 and not first['runtime_activated']
    assert ctx['client'].post('/v1/interface-starter',headers=h).json()['created']==0
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(WorkspaceAsset))==18
        assert db.scalar(select(func.count()).select_from(User))>=3
    ctx['settings'].mode='pilot'
    assert ctx['client'].post('/v1/interface-starter',headers=h).status_code==403


def test_interface_revision_review_rows_archive_and_history(ctx):
    spec=catalog()['modules'][0];h,row=create(ctx,spec)
    body=payload(spec);body['expected_version']=1
    body['config']['surface_rows']=[{'id':'synthetic-record','state':'review_requested','values':{c['id']:c['default'] for c in spec['record_columns']}}]
    body['config']['phase']='ui_reviewed';body['config']['ui_checks']={c['id']:True for c in spec['criteria']}
    changed=ctx['client'].put('/v1/workbench/'+row['id'],headers=h,json=body);assert changed.status_code==200 and changed.json()['version']==2
    assert ctx['client'].put('/v1/workbench/'+row['id'],headers=h,json=body).status_code==409
    checked=ctx['client'].post('/v1/workbench/'+row['id']+'/validate',headers=h,json={'expected_version':2});assert checked.json()['version']==3
    archived=ctx['client'].post('/v1/workbench/'+row['id']+'/archive',headers=h,json={'expected_version':3});assert archived.json()['status']=='archived'
    history=ctx['client'].get('/v1/workbench/'+row['id']+'/history').json();assert len(history)==4
    assert history[-1]['snapshot']['config']['surface_rows']==[]
    assert not ctx['client'].get('/v1/production-readiness').json()['production_ready']


def test_phase_and_reference_and_record_validation(ctx):
    spec=next(m for m in catalog()['modules'] if m['id']=='secrets_network');h,_=auth(ctx);body=payload(spec)
    wrong=copy.deepcopy(body);wrong['config']['phase']='ui_reviewed';assert ctx['client'].post('/v1/workbench',headers=h,json=wrong).status_code==422
    wrong=copy.deepcopy(body);wrong['config']['values']['secret_reference']='actual-credential-must-not-be-accepted';assert ctx['client'].post('/v1/workbench',headers=h,json=wrong).status_code==422
    wrong=copy.deepcopy(body);wrong['config']['values']['unexpected']='secret';assert ctx['client'].post('/v1/workbench',headers=h,json=wrong).status_code==422
    wrong=copy.deepcopy(body);wrong['config']['surface_rows']=[{'id':'row','state':'connected_live','values':{c['id']:c['default'] for c in spec['record_columns']}}];assert ctx['client'].post('/v1/workbench',headers=h,json=wrong).status_code==422
    wrong['config']['surface_rows'][0]['state']='draft';wrong['config']['surface_rows'][0]['values']['reference']='raw-token';assert ctx['client'].post('/v1/workbench',headers=h,json=wrong).status_code==422


def test_interface_scope_roles_and_undefined_scenarios(ctx):
    spec=catalog()['modules'][0];h,row=create(ctx,spec);body=payload(spec)
    assert ctx['client'].post('/v1/workbench',json=body).status_code==403
    reader,_=auth(ctx,'approver');assert ctx['client'].post('/v1/workbench',headers=reader,json=body).status_code==403
    other,_=auth(ctx,org='other');assert ctx['client'].get('/v1/workbench/'+row['id']+'/history').status_code==404
    assert ctx['client'].post('/v1/workbench/'+row['id']+'/run',headers=other,json={}).status_code==404
    h,_=auth(ctx)
    for variables in [{'design_action':'undefined-action'},{'design_scenario':'pretend-production-success'}]:
        assert ctx['client'].post('/v1/workbench/'+row['id']+'/run',headers=h,json={'variables':variables}).status_code==422
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkbenchRun))==0
