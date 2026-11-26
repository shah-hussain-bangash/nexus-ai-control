import copy
import pytest
from sqlalchemy import select, func
from conftest import auth, approve
from test_durable import body, advance, control
from nexus import durable
from nexus.app import create_app
from nexus.db import DurableRun, Action, Agent, User, now
from nexus.security import digest
from nexus.service import canonical


@pytest.fixture
def clock(monkeypatch):
    value=[int(now())]
    monkeypatch.setattr(durable,'now',lambda:value[0])
    return value


def submit(ctx,clock,delta=3600,key='scheduled-start-0001',**kwargs):
    request=body(ctx,**kwargs);request['start_at']=clock[0]+delta
    h,_=auth(ctx);h['Idempotency-Key']=key
    return ctx['client'].post('/v1/agent-runs',headers=h,json=request),request


def detail(ctx,run):return ctx['client'].get('/v1/agent-runs/'+run['id']).json()


def test_persisted_schedule_survives_new_app_and_never_starts_early(ctx,clock):
    response,_=submit(ctx,clock);assert response.status_code==201,response.text
    run=response.json();start=run['scheduled_start_at']
    restarted=create_app(ctx['settings'])
    try:
        assert not durable.run_flow_once(restarted.state.factory,ctx['settings'])
        # Even a premature wake-up hint cannot authorize a checkpoint.
        with restarted.state.factory.begin() as db:db.get(DurableRun,run['id']).next_poll=0
        assert durable.run_flow_once(restarted.state.factory,ctx['settings'])
        result=detail(ctx,run)
        assert result['cursor']==0 and result['next_poll']>=start and ctx['connector'].count()==0
        clock[0]=start-1;assert not durable.run_flow_once(restarted.state.factory,ctx['settings'])
        clock[0]=start;assert durable.run_flow_once(restarted.state.factory,ctx['settings'])
        assert detail(ctx,run)['cursor']==1 and ctx['connector'].count()==0
    finally:restarted.state.engine.dispose()


def test_pause_resume_retry_and_lease_recovery_keep_scheduled_floor(ctx,clock):
    response,_=submit(ctx,clock);run=response.json();start=run['scheduled_start_at']
    paused=control(ctx,run,'pause');assert paused.status_code==200
    resumed=control(ctx,paused.json(),'resume');assert resumed.status_code==200
    assert resumed.json()['next_poll']>=start and not durable.run_flow_once(ctx['db'],ctx['settings'])
    with ctx['db'].begin() as db:
        row=db.get(DurableRun,run['id']);row.status='processing';row.lease_token='expired';row.lease_until=clock[0]-1
    assert not durable.run_flow_once(ctx['db'],ctx['settings'])
    result=detail(ctx,run);assert result['recoveries']==1 and result['next_poll']>=start
    with ctx['db'].begin() as db:db.get(DurableRun,run['id']).status='failed'
    result=detail(ctx,run);retried=control(ctx,result,'retry')
    assert retried.status_code==200 and retried.json()['next_poll']>=start
    assert ctx['connector'].count()==0


def test_cancel_before_start_stays_cancelled_after_due_time(ctx,clock):
    response,_=submit(ctx,clock);run=response.json()
    assert control(ctx,run,'cancel').json()['status']=='cancelled'
    clock[0]+=7200
    assert not durable.run_flow_once(ctx['db'],ctx['settings'])
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0
    assert ctx['connector'].count()==0


def test_scheduled_replay_and_recovery_keep_original_time_even_after_it_passes(ctx,clock):
    response,request=submit(ctx,clock);run=response.json();clock[0]+=7200
    h,_=auth(ctx);h['Idempotency-Key']='scheduled-start-0001'
    replay=ctx['client'].post('/v1/agent-runs',headers=h,json=request)
    assert replay.status_code==201 and replay.json()['id']==run['id']
    changed=copy.deepcopy(request);changed['start_at']+=1
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=changed).status_code==409
    recovered=ctx['client'].post('/v1/agent-runs/recover',headers=h,json={'key':'scheduled-start-0001'})
    assert recovered.status_code==200 and recovered.json()['scheduled_start_at']==request['start_at']
    assert ctx['connector'].count()==0


@pytest.mark.parametrize('delta',[-1,0,7*86400+1])
def test_new_out_of_window_schedules_are_rejected_without_records(ctx,clock,delta):
    response,_=submit(ctx,clock,delta=delta)
    assert response.status_code==422 and response.json()['error']['code']=='START_TIME_RANGE'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(DurableRun))==0


@pytest.mark.parametrize('value',[True,'1234567890',1.5])
def test_schedule_requires_a_strict_integer(ctx,clock,value):
    request=body(ctx);request['start_at']=value;h,_=auth(ctx);h['Idempotency-Key']='strict-schedule-001'
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=request).status_code==422


def test_seven_day_boundary_and_immediate_legacy_fingerprint(ctx,clock):
    response,_=submit(ctx,clock,delta=7*86400);assert response.status_code==201,response.text
    request=body(ctx,review=False,purchase=False);h,_=auth(ctx);h['Idempotency-Key']='legacy-immediate-001'
    immediate=ctx['client'].post('/v1/agent-runs',headers=h,json=request);assert immediate.status_code==201
    definition=immediate.json()['definition'];assert 'start_at' not in definition
    expected={**durable.RunInput.model_validate(request).model_dump(),'destination':'mock-business-v1'}
    expected.pop('start_at')
    with ctx['db']() as db:assert db.get(DurableRun,immediate.json()['id']).request_digest==digest(canonical(expected))
    request['start_at']=None
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=request).json()['id']==immediate.json()['id']


def test_due_scheduled_run_still_requires_independent_and_business_approval(ctx,clock):
    response,_=submit(ctx,clock);run=response.json();clock[0]=run['scheduled_start_at']
    run=advance(ctx,run['id']);assert run['status']=='waiting_review' and ctx['connector'].count()==1
    h,_=auth(ctx,'approver')
    assert ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={
        'expected_version':run['version'],'decision':'approve','note':'Review scheduled synthetic procurement.'}).status_code==200
    run=advance(ctx,run['id']);assert run['status']=='waiting_action'
    with ctx['db']() as db:assert db.get(Action,run['steps'][run['cursor']]['action_id']).status=='awaiting_approval'
    assert approve(ctx).status_code==200
    assert advance(ctx,run['id'])['status']=='succeeded' and ctx['connector'].count()==2


@pytest.mark.parametrize('change',['agent','author'])
def test_authorization_is_rechecked_at_due_time(ctx,clock,change):
    response,_=submit(ctx,clock);run=response.json()
    with ctx['db'].begin() as db:
        if change=='agent':db.get(Agent,run['agent_id']).generation+=1
        else:db.get(User,run['author_id']).role='auditor'
    clock[0]=run['scheduled_start_at'];assert durable.run_flow_once(ctx['db'],ctx['settings'])
    with ctx['db']() as db:
        row=db.get(DurableRun,run['id']);assert row.status=='failed'
        assert row.error==('AGENT_CHANGED' if change=='agent' else 'REQUESTER_REVOKED')
        assert db.scalar(select(func.count()).select_from(Action))==0


def test_scheduled_time_is_in_unsigned_evidence(ctx,clock):
    response,_=submit(ctx,clock);run=response.json()
    report=ctx['client'].get('/v1/agent-runs/'+run['id']+'/evidence')
    assert report.status_code==200,report.text
    value=report.json();assert value['payload']['run']['scheduled_start_at_utc'].endswith('Z')
    assert value['integrity']['digest']==digest(canonical(value['payload']))
    assert not value['integrity']['authenticated_signature'] and ctx['connector'].count()==0
