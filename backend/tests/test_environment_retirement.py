from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from conftest import auth
from test_local_switching import prepare,current,headers,switch,upload,selection
from test_environment_runtime import inventory,control,body,workload,request_workload
from nexus.db import Base,WorkspaceEnvironment,EnvironmentAssignment,KnowledgeDocument,Agent,Audit,InferenceCall

def paused(ctx):
    prepare(ctx)
    result=control(ctx,inventory(ctx));assert result.status_code==200,result.text
    return inventory(ctx)

def retained(db):
    return {table.name:[repr(dict(row)) for row in db.execute(select(table).where(table.c.org_id=='northstar',table.c.env=='production')).mappings()]
            for table in Base.metadata.sorted_tables if 'org_id' in table.c and 'env' in table.c}

def test_retirement_retains_all_environment_records_and_disables_runtime_permanently(ctx):
    target=prepare(ctx);prod=switch(ctx,target);document=upload(ctx,prod)
    auth(ctx);agent,tool,token=workload(ctx)
    assert control(ctx,inventory(ctx)).status_code==200
    row=inventory(ctx)
    with ctx['db']() as db:
        before=retained(db)
        assignments=db.scalar(select(func.count()).select_from(EnvironmentAssignment).where(EnvironmentAssignment.environment_key=='production'))
    result=control(ctx,row,'retire',confirmation_key='production');assert result.status_code==200,result.text
    assert result.json()=={'key':'production','state':'retired','version':row['version']+1,'sessions_revoked':0,'records_preserved':True}
    with ctx['db']() as db:
        assert retained(db)==before
        assert db.get(KnowledgeDocument,document['id']) and db.get(Agent,agent).credential_hash=='retained-test-hash'
        assert db.scalar(select(func.count()).select_from(EnvironmentAssignment).where(EnvironmentAssignment.environment_key=='production'))==assignments
        event=db.scalar(select(Audit).where(Audit.event=='environment.runtime_retire'))
        assert event.env=='staging' and event.detail['records_preserved']
    row=inventory(ctx)
    assert row['state']=='retired' and not row['human_runtime_enabled']
    assert request_workload(ctx['client'],tool,token).status_code==403
    assert ctx['client'].post('/v1/session-context/select',headers=headers(current(ctx)),json=selection(current(ctx),row)).status_code==403
    assert 'production' not in {r['key'] for r in ctx['client'].get('/v1/session-context/choices',headers=headers(current(ctx))).json()['items']}
    # Permanent here means no runtime-state reversal through any current API.
    for command in ('pause','resume','retire'):
        assert control(ctx,{**row,'selected_sessions':0},command,confirmation_key='production').status_code==409
    for command in ('archive','restore'):
        assert ctx['client'].post('/v1/workspace-environments/production/control',headers=headers(current(ctx)),json={'command':command,'expected_version':row['version'],'note':'Retired state must not be reversed.'}).status_code==409
    assert ctx['client'].post('/v1/workspace-environments/production/activate',headers=headers(current(ctx)),json={'expected_version':row['version'],'reviewed':True,'note':'Retired runtime must not be reactivated.'}).status_code==409
    assert ctx['client'].post('/v1/workspace-environments',headers=headers(current(ctx)),json={'key':'production','name':'Replacement','note':'Retired environment key stays reserved.'}).status_code==409
    snapshot=ctx['client'].get('/v1/workspace-environments/production/assignments',headers=headers(current(ctx))).json()
    assert snapshot['editing_enabled'] is False and snapshot['items']
    member=snapshot['items'][0]
    assert ctx['client'].post('/v1/workspace-environments/production/assignments/control',headers=headers(current(ctx)),json={'user_id':member['id'],'command':'revoke','expected_version':row['version'],'expected_member_revision':member['revision'],'reviewed':True,'note':'Retired assignments must remain retained.'}).status_code==409

@pytest.mark.parametrize('key',[None,'','Production','production ','other-env'])
def test_retirement_requires_exact_typed_key_and_keeps_paused_state_on_error(ctx,key):
    row=paused(ctx)
    result=control(ctx,row,'retire',confirmation_key=key)
    assert result.status_code==422 and result.json()['error']['code']=='RETIREMENT_CONFIRMATION_REQUIRED'
    assert inventory(ctx)['state']=='suspended'

def test_retirement_requires_pause_review_and_current_snapshot(ctx):
    prepare(ctx);row=inventory(ctx)
    assert control(ctx,row,'retire',confirmation_key='production').status_code==409
    assert control(ctx,row).status_code==200
    row=inventory(ctx)
    assert control(ctx,row,'retire',confirmation_key='production',reviewed=False).status_code==422
    assert control(ctx,row,'retire',confirmation_key='production',expected_version=row['version']-1).status_code==409
    assert control(ctx,row,'retire',confirmation_key='production',expected_selected_sessions=1).status_code==409
    assert ctx['client'].post('/v1/workspace-environments/production/runtime-control',json=body(row,'retire',confirmation_key='production')).status_code==403

def test_retirement_rechecks_unfinished_work_in_paused_environment(ctx):
    row=paused(ctx);owner=current(ctx)['user']['id']
    with ctx['db'].begin() as db:
        db.add(InferenceCall(org_id='northstar',env='production',key_hash='retire-unknown',request_hash='test',author_id=owner,asset_id='test',asset_version=1,period='2026-11',reserved=0,input_rate='0',output_rate='0',status='unknown'))
    result=control(ctx,row,'retire',confirmation_key='production')
    assert result.status_code==409 and result.json()['error']['code']=='ENVIRONMENT_BUSY'

def test_retirement_is_assigned_owner_local_workspace_scoped_and_staging_protected(ctx):
    row=paused(ctx);owner=current(ctx)['user']['id']
    with ctx['db'].begin() as db:db.delete(db.get(EnvironmentAssignment,(owner,'northstar','production')))
    assert control(ctx,row,'retire',confirmation_key='production').status_code==403
    auth(ctx,'auditor')
    assert ctx['client'].post('/v1/workspace-environments/production/runtime-control',headers=headers(current(ctx)),json=body(row,'retire',confirmation_key='production')).status_code==403
    auth(ctx,org='other');assert control(ctx,row,'retire',confirmation_key='production').status_code==404
    auth(ctx);assert control(ctx,inventory(ctx,'staging'),'retire',confirmation_key='staging').status_code==409
    ctx['settings'].mode='pilot';assert control(ctx,row,'retire',confirmation_key='production').status_code==403

def test_concurrent_retirement_has_one_version_and_one_audit_event(ctx):
    row=paused(ctx);me=current(ctx);cookie=ctx['client'].cookies.get('nexus_session')
    def retire(_):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post('/v1/workspace-environments/production/runtime-control',headers=headers(me),json=body(row,'retire',confirmation_key='production')).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(retire,[1,2]))
    assert sorted(statuses)==[200,409]
    with ctx['db']() as db:
        assert db.get(WorkspaceEnvironment,('northstar','production')).version==row['version']+1
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.event=='environment.runtime_retire'))==1
