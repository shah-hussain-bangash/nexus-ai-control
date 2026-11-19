from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from conftest import auth
from test_local_switching import prepare,current,headers,switch,upload
from nexus.db import WorkspaceEnvironment,SessionRecord,SessionRuntimeContext,KnowledgeDocument,Policy,Agent,Tool,Grant,Action,DurableRun,InferenceCall,Audit
from nexus.security import workload_token,digest

def inventory(ctx,key='production'):
    result=ctx['client'].get('/v1/workspace-environments',headers=headers(current(ctx)))
    assert result.status_code==200,result.text
    return next(r for r in result.json()['items'] if r['key']==key)

def body(row,command='pause',**changes):
    return {'command':command,'expected_version':row['version'],'expected_selected_sessions':row['selected_sessions'],'reviewed':True,'note':'Reviewed idle runtime and selected-session sign-out.',**changes}

def control(ctx,row,command='pause',**changes):
    return ctx['client'].post('/v1/workspace-environments/'+row['key']+'/runtime-control',headers=headers(current(ctx)),json=body(row,command,**changes))

def workload(ctx):
    owner=current(ctx)['user']['id']
    with ctx['db'].begin() as db:
        a=Agent(org_id='northstar',env='production',name='Local supplier reader',owner_id=owner,risk='low',status='active',credential_hash='retained-test-hash')
        t=Tool(org_id='northstar',env='production',name='Supplier reader',kind='supplier',risk='low')
        db.add_all([a,t]);db.flush()
        db.add(Grant(org_id='northstar',env='production',agent_id=a.id,tool_id=t.id,scope='supplier:read'))
        return a.id,t.id,workload_token(a,ctx['settings'])

def request_workload(client,tool,token,key='runtime-pause-action-001'):
    return client.post('/v1/gateway/tools/'+tool+':execute',headers={'Authorization':'Bearer '+token,'Idempotency-Key':key},json={
        'action':'supplier:read','resource':'suppliers','arguments':{'supplier_id':'SUP-DEMO-104'},'tool_version':'1.0'})

def test_pause_resume_retains_records_and_only_revokes_selected_target_sessions(ctx):
    target=prepare(ctx);prod=switch(ctx,target);document=upload(ctx,prod);old_cookie=ctx['client'].cookies.get('nexus_session')
    auth(ctx);stage=current(ctx);stage_session=digest(ctx['client'].cookies.get('nexus_session'))
    agent,tool,token=workload(ctx)
    row=inventory(ctx);assert row['selected_sessions']==1 and not any(row['unfinished_work'].values())
    paused=control(ctx,row);assert paused.status_code==200,paused.text
    assert paused.json()['state']=='suspended' and paused.json()['sessions_revoked']==1
    assert 'production' not in {r['key'] for r in ctx['client'].get('/v1/session-context/choices',headers=headers(stage)).json()['items']}
    with TestClient(ctx['app']) as old:
        old.cookies.set('nexus_session',old_cookie)
        assert old.get('/v1/me').status_code==401
    assert request_workload(ctx['client'],tool,token).status_code==403
    with ctx['db']() as db:
        assert db.get(SessionRecord,stage_session) and not db.get(SessionRecord,digest(old_cookie))
        assert db.get(KnowledgeDocument,document['id']).env=='production'
        assert db.get(Agent,agent).credential_hash=='retained-test-hash'
        assert db.scalar(select(func.count()).select_from(Policy).where(Policy.env=='production'))==1
    resumed=control(ctx,inventory(ctx),'resume');assert resumed.status_code==200,resumed.text
    assert resumed.json()['state']=='active' and resumed.json()['sessions_revoked']==0
    prod=switch(ctx,inventory(ctx))
    assert ctx['client'].get('/v1/documents/'+document['id'],headers=headers(prod)).status_code==200
    with ctx['db']() as db:
        assert not db.get(SessionRecord,digest(old_cookie))
        assert set(db.scalars(select(Audit.event).where(Audit.event.like('environment.runtime_%'))))=={'environment.runtime_pause','environment.runtime_resume'}

@pytest.mark.parametrize('kind,status',[('actions','queued'),('actions','outcome_unknown'),('actions','future_state'),('durable_runs','paused'),('ingestion_jobs','queued'),('inference_calls','pending'),('inference_calls','unknown')])
def test_unfinished_or_unknown_work_blocks_pause_without_changing_state(ctx,kind,status):
    prepare(ctx);a,t,token=workload(ctx);me=current(ctx)
    if kind=='actions':
        result=request_workload(ctx['client'],t,token);assert result.status_code==202,result.text
        with ctx['db'].begin() as db:db.get(Action,result.json()['id']).status=status
    elif kind=='ingestion_jobs':
        from test_ingestion import payload
        prod=switch(ctx,inventory(ctx))
        result=ctx['client'].post('/v1/ingestion-jobs',headers={**headers(prod),'Idempotency-Key':'pause-intake-key-001'},json=payload())
        assert result.status_code==201,result.text
        auth(ctx)
    else:
        with ctx['db'].begin() as db:
            if kind=='durable_runs':db.add(DurableRun(org_id='northstar',env='production',name='Paused test flow',agent_id=a,generation=1,author_id=me['user']['id'],definition={'steps':[]},payload_hash='synthetic',idem_key='pause-flow-key-001',request_digest='synthetic',status=status))
            else:db.add(InferenceCall(org_id='northstar',env='production',key_hash='synthetic',request_hash='synthetic',author_id=me['user']['id'],asset_id='synthetic',asset_version=1,period='2026-11',reserved=0,input_rate='0',output_rate='0',status=status))
    row=inventory(ctx);assert row['unfinished_work'][kind]==1
    response=control(ctx,row)
    assert response.status_code==409 and response.json()['error']['code']=='ENVIRONMENT_BUSY'
    with ctx['db']() as db:assert db.get(WorkspaceEnvironment,('northstar','production')).state=='active'

def test_runtime_review_is_target_scoped_and_stale_snapshots_are_rejected(ctx):
    prepare(ctx);row=inventory(ctx)
    with ctx['db'].begin() as db:db.add(InferenceCall(org_id='northstar',env='staging',key_hash='stage-pending',request_hash='synthetic',author_id=current(ctx)['user']['id'],asset_id='synthetic',asset_version=1,period='2026-11',reserved=0,input_rate='0',output_rate='0'))
    assert control(ctx,row,expected_version=row['version']-1).status_code==409
    assert control(ctx,row,expected_selected_sessions=1).status_code==409
    assert control(ctx,row,reviewed=False).status_code==422
    assert control(ctx,row,note='  ').status_code==422
    assert control(ctx,row).status_code==200
    paused=inventory(ctx)
    for command in ('archive','restore'):
        assert ctx['client'].post('/v1/workspace-environments/production/control',headers=headers(current(ctx)),json={'command':command,'expected_version':paused['version'],'note':'Paused runtime must preserve its state.'}).status_code==409
    assert ctx['client'].post('/v1/workspace-environments/production/activate',headers=headers(current(ctx)),json={'expected_version':paused['version'],'reviewed':True,'note':'Must not reset an existing paused runtime.'}).status_code==409

def test_runtime_controls_require_assigned_owner_csrf_local_mode_and_other_environment(ctx):
    target=prepare(ctx);row=inventory(ctx)
    url='/v1/workspace-environments/production/runtime-control'
    assert ctx['client'].post(url,json=body(row)).status_code==403
    with ctx['db'].begin() as db:
        from nexus.db import EnvironmentAssignment
        db.delete(db.get(EnvironmentAssignment,(current(ctx)['user']['id'],'northstar','production')))
    assert control(ctx,row).status_code==403
    auth(ctx,'auditor');me=current(ctx)
    assert ctx['client'].post(url,headers=headers(me),json=body(row)).status_code==403
    auth(ctx,org='other');assert control(ctx,row).status_code==404
    auth(ctx);stage=inventory(ctx,'staging');assert control(ctx,stage).status_code==409
    ctx['settings'].mode='pilot'
    assert control(ctx,row).status_code==403

def test_cannot_pause_current_runtime(ctx):
    target=prepare(ctx);switch(ctx,target)
    assert control(ctx,inventory(ctx)).status_code==409

def test_gateway_admission_and_pause_share_one_ordering(ctx):
    prepare(ctx);a,t,token=workload(ctx);me=current(ctx);row=inventory(ctx);cookie=ctx['client'].cookies.get('nexus_session')
    def pause():
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post('/v1/workspace-environments/production/runtime-control',headers=headers(me),json=body(row))
    def submit():
        with TestClient(ctx['app']) as client:return request_workload(client,t,token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        p=pool.submit(pause);s=pool.submit(submit);paused,submitted=p.result(),s.result()
    assert (paused.status_code,submitted.status_code) in ((200,403),(409,202)),(paused.text,submitted.text)
    with ctx['db']() as db:
        state=db.get(WorkspaceEnvironment,('northstar','production')).state
        queued=db.scalar(select(func.count()).select_from(Action).where(Action.env=='production',Action.status=='queued'))
        assert (state,queued) in (('suspended',0),('active',1))


def test_workload_read_is_withheld_after_concurrent_pause(ctx,monkeypatch):
    prepare(ctx);a,t,token=workload(ctx)
    action=request_workload(ctx['client'],t,token);assert action.status_code==202,action.text
    with ctx['db'].begin() as db:db.get(Action,action.json()['id']).status='verified'
    row=inventory(ctx)
    from nexus import app as app_module
    original=app_module.scoped
    def scoped_then_pause(db,model,*args,**kwargs):
        result=original(db,model,*args,**kwargs)
        if model is Action:
            paused=control(ctx,row);assert paused.status_code==200,paused.text
        return result
    monkeypatch.setattr(app_module,'scoped',scoped_then_pause)
    response=ctx['client'].get('/v1/gateway/actions/'+action.json()['id'],headers={'Authorization':'Bearer '+token})
    assert response.status_code==409 and response.json()['error']['code']=='STALE_SESSION_CONTEXT'
