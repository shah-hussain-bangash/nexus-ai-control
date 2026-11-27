import copy
import pytest
from sqlalchemy import select,update,func
from conftest import auth,identifiers,approve
from nexus.db import DurableRun,DurableStep,Action,Approval,Agent,User,SchemaVersion,KnowledgeDocument,DocumentChunk,DocumentUpdate,RetrievalCheck,IngestionJob,NeuralVector,NeuralIndex,migrate,now
from nexus.durable import run_flow_once
from nexus.worker import run_once

def body(ctx,review=True,purchase=True,simulation='normal'):
    agent,lookup=identifiers(ctx,kind='supplier');_,buy=identifiers(ctx,kind='purchase')
    steps=[{'kind':'checkpoint','label':'Validate input'},{'kind':'governed_action','label':'Supplier lookup','tool_id':lookup,'request':{'action':'supplier:read','resource':'suppliers','arguments':{'supplier_id':'SUP-DEMO-104'}}}]
    if review:steps.append({'kind':'approval','label':'Independent workflow review'})
    if purchase:steps.append({'kind':'governed_action','label':'Purchase request','tool_id':buy,'request':{'action':'purchase:create','resource':'purchase_requests','arguments':{'supplier_id':'SUP-DEMO-104','amount':'12500.00','currency':'USD','purpose':'Durable synthetic procurement'},'simulation':simulation}})
    steps.append({'kind':'output','label':'Collect verified outcome'})
    return {'name':'Durable procurement','agent_id':agent,'steps':steps}

def create(ctx,**kwargs):
    h,_=auth(ctx);h['Idempotency-Key']='durable-test-key-001';response=ctx['client'].post('/v1/agent-runs',headers=h,json=body(ctx,**kwargs));assert response.status_code==201,response.text
    return response.json()

def advance(ctx,id,count=12):
    for _ in range(count):
        with ctx['db'].begin() as db:db.execute(update(DurableRun).values(next_poll=0))
        run_flow_once(ctx['db'],ctx['settings']);run_once(ctx['db'],ctx['settings'],ctx['connector'])
    return ctx['client'].get('/v1/agent-runs/'+id).json()

def control(ctx,run,command):
    h,_=auth(ctx);return ctx['client'].post('/v1/agent-runs/'+run['id']+'/control',headers=h,json={'expected_version':run['version'],'command':command,'note':'Reviewed durable workflow control.'})

def test_durable_procurement_waits_for_two_independent_gates_and_finishes(ctx):
    run=create(ctx);run=advance(ctx,run['id']);assert run['status']=='waiting_review'
    assert ctx['connector'].count()==1  # the read-only supplier lookup is already verified
    h,_=auth(ctx,'approver');review=ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={'expected_version':run['version'],'decision':'approve','note':'Reviewed supplier, amount and purchase purpose.'});assert review.status_code==200,review.text
    run=advance(ctx,run['id']);assert run['status']=='waiting_action'
    action=run['steps'][run['cursor']]['action_id']
    with ctx['db']() as db:assert db.get(Action,action).status=='awaiting_approval'
    assert approve(ctx).status_code==200
    run=advance(ctx,run['id']);assert run['status']=='succeeded'
    assert all(s['status']=='completed' for s in run['steps']) and ctx['connector'].count()==2
    advance(ctx,run['id']);assert ctx['connector'].count()==2

def test_run_idempotency_pins_payload_and_requires_csrf_role_tenant(ctx):
    run=create(ctx,review=False,purchase=False);h,_=auth(ctx);h['Idempotency-Key']='durable-test-key-001';b=body(ctx,review=False,purchase=False)
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=b).json()['id']==run['id']
    b['name']='Different intent';assert ctx['client'].post('/v1/agent-runs',headers=h,json=b).status_code==409
    assert ctx['client'].post('/v1/agent-runs',json=b).status_code==403
    h,_=auth(ctx,'auditor');assert ctx['client'].post('/v1/agent-runs',headers=h,json=b).status_code==403
    auth(ctx,org='other');assert ctx['client'].get('/v1/agent-runs/'+run['id']).status_code==404

def test_pause_resume_and_cancel_do_not_dispatch_new_steps(ctx):
    run=create(ctx,review=False,purchase=False);paused=control(ctx,run,'pause');assert paused.status_code==200
    assert advance(ctx,run['id'])['cursor']==0
    assert control(ctx,run,'resume').status_code==409
    resumed=control(ctx,paused.json(),'resume');assert resumed.status_code==200
    assert control(ctx,resumed.json(),'cancel').json()['status']=='cancelled'
    assert advance(ctx,run['id'])['status']=='cancelled'

def test_expired_worker_claim_recovers_persisted_cursor_without_duplicate_action(ctx):
    run=create(ctx,review=False,purchase=False)
    with ctx['db'].begin() as db:
        row=db.get(DurableRun,run['id']);row.status='processing';row.lease_token='expired-worker';row.lease_until=now()-1
    completed=advance(ctx,run['id']);assert completed['status']=='succeeded' and completed['recoveries']==1
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==1

def test_unknown_purchase_is_not_retried_and_can_finish_after_reconciliation(ctx):
    run=create(ctx,review=False,simulation='timeout_after_commit');run=advance(ctx,run['id']);assert approve(ctx).status_code==200
    run=advance(ctx,run['id']);assert run['status']=='outcome_unknown' and ctx['connector'].count()==2
    assert control(ctx,run,'retry').status_code==409
    run=advance(ctx,run['id']);assert ctx['connector'].count()==2
    h,_=auth(ctx);aid=run['steps'][run['cursor']]['action_id'];assert ctx['client'].post('/v1/actions/'+aid+'/reconcile',headers=h).status_code==200
    assert advance(ctx,run['id'])['status']=='succeeded' and ctx['connector'].count()==2

def test_cancel_queued_action_cancels_pending_approval_without_effect(ctx):
    run=create(ctx,review=False)
    # Drive workflow checkpoints while leaving the business worker stopped.
    for _ in range(3):
        with ctx['db'].begin() as db:db.execute(update(DurableRun).values(next_poll=0))
        run_flow_once(ctx['db'],ctx['settings'])
    run=ctx['client'].get('/v1/agent-runs/'+run['id']).json();aid=run['steps'][run['cursor']]['action_id'];assert aid
    cancelled=control(ctx,run,'cancel');assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
    run_once(ctx['db'],ctx['settings'],ctx['connector'])
    with ctx['db']() as db:assert db.get(Action,aid).status=='cancelled'
    assert ctx['connector'].count()==0

def test_agent_revocation_blocks_the_next_unsubmitted_step(ctx):
    run=create(ctx,review=False,purchase=False)
    with ctx['db'].begin() as db:db.get(Agent,run['agent_id']).generation+=1
    run=advance(ctx,run['id']);assert run['status']=='failed' and run['error']=='AGENT_CHANGED'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0

def test_expired_independent_review_cannot_be_reactivated(ctx):
    run=create(ctx);run=advance(ctx,run['id']);h,_=auth(ctx,'approver')
    with ctx['db'].begin() as db:db.get(DurableRun,run['id']).review_until=now()-1
    assert ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={'expected_version':run['version'],'decision':'approve','note':'Reviewed expired workflow.'}).status_code==409
    assert advance(ctx,run['id'])['status']=='expired'

def test_schema_five_upgrade_preserves_users_and_existing_assets(ctx):
    with ctx['app'].state.engine.begin() as connection:
        # Remove later-schema dependents before reconstructing schema five.
        for model in (NeuralVector,NeuralIndex,IngestionJob,RetrievalCheck,DocumentUpdate,DurableStep,DurableRun,DocumentChunk,KnowledgeDocument):model.__table__.drop(connection)
        connection.execute(SchemaVersion.__table__.delete().where(SchemaVersion.version>=6))
    migrate(ctx['app'].state.engine,ctx['db'])
    with ctx['db']() as db:assert db.get(SchemaVersion,6) and db.scalar(select(User).where(User.email=='owner@nexus.local'))

def test_recovery_is_author_scoped_csrf_protected_and_never_dispatches(ctx):
    run=create(ctx,review=False,purchase=False);h,_=auth(ctx)
    response=ctx['client'].post('/v1/agent-runs/recover',headers=h,json={'key':'durable-test-key-001'})
    assert response.status_code==200 and response.json()['id']==run['id'] and ctx['connector'].count()==0
    assert ctx['client'].post('/v1/agent-runs/recover',json={'key':'durable-test-key-001'}).status_code==403
    h,_=auth(ctx,'auditor');assert ctx['client'].post('/v1/agent-runs/recover',headers=h,json={'key':'durable-test-key-001'}).status_code==404

def test_cancel_unknown_preserves_effect_until_reconciliation(ctx):
    run=create(ctx,review=False,simulation='timeout_after_commit');run=advance(ctx,run['id']);assert approve(ctx).status_code==200
    run=advance(ctx,run['id']);assert run['status']=='outcome_unknown'
    stopped=control(ctx,run,'cancel');assert stopped.status_code==200 and stopped.json()['status']=='outcome_unknown'
    aid=run['steps'][run['cursor']]['action_id'];h,_=auth(ctx);assert ctx['client'].post('/v1/actions/'+aid+'/reconcile',headers=h).status_code==200
    assert advance(ctx,run['id'])['status']=='cancelled' and ctx['connector'].count()==2

def test_cancel_pending_purchase_revokes_the_pending_business_approval(ctx):
    run=create(ctx,review=False);run=advance(ctx,run['id']);assert run['status']=='waiting_action'
    aid=run['steps'][run['cursor']]['action_id'];cancelled=control(ctx,run,'cancel');assert cancelled.status_code==200
    with ctx['db']() as db:assert db.scalar(select(Approval).where(Approval.action_id==aid)).status=='cancelled'
    assert approve(ctx).status_code==409
    assert ctx['connector'].count()==1

def test_waiting_action_polls_do_not_change_the_review_version(ctx):
    run=create(ctx,review=False);run=advance(ctx,run['id']);version=run['version']
    run=advance(ctx,run['id']);assert run['version']==version and run['status']=='waiting_action'

def test_independent_checkpoint_rejects_self_review_even_if_role_has_approval_permission(ctx,monkeypatch):
    from nexus.security import PERMISSIONS
    run=create(ctx);run=advance(ctx,run['id']);h,_=auth(ctx)
    monkeypatch.setitem(PERMISSIONS,'owner',PERMISSIONS['owner']|{'approve'})
    response=ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={'expected_version':run['version'],'decision':'approve','note':'Attempt to approve own request.'})
    assert response.status_code==403 and response.json()['error']['code']=='SELF_APPROVAL'

def test_tampered_definition_never_dispatches_a_business_action(ctx):
    run=create(ctx,review=False,purchase=False)
    with ctx['db'].begin() as db:
        row=db.get(DurableRun,run['id']);definition=copy.deepcopy(row.definition);definition['name']='Changed after submission';row.definition=definition
    result=advance(ctx,run['id']);assert result['status']=='failed' and result['error']=='PAYLOAD_CHANGED'
    assert ctx['connector'].count()==0

def test_concurrent_flow_workers_do_not_create_duplicate_governed_intents(ctx):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.exc import OperationalError
    run=create(ctx,review=False,purchase=False)
    def tick():
        try:return run_flow_once(ctx['db'],ctx['settings'])
        except OperationalError:return False  # SQLite writer contention is retried by the worker loop.
    for _ in range(8):
        with ctx['db'].begin() as db:db.execute(update(DurableRun).values(next_poll=0))
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda _:tick(),range(3)))
        run_once(ctx['db'],ctx['settings'],ctx['connector'])
    result=advance(ctx,run['id']);assert result['status']=='succeeded'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==1
    assert ctx['connector'].count()==1
