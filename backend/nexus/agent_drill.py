"""Disposable durable-workflow exercise with synthetic effects and deadline faults."""
import argparse
from datetime import datetime, timezone
import gc
import json
import logging
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from unittest.mock import patch
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import event,select,update,func
from . import __version__, durable
from .app import create_app
from .cli import seed
from .config import Settings
from .db import CURRENT_SCHEMA,Organization,Policy,User,Agent,Tool,DurableRun,Action,migrate,now
from .environments import assign_staging
from .mock_connector import MockBusiness
from .security import password_hash
from .synthetic_drill import DrillFailure
from .worker import run_once

BOUNDARY=('Disposable synthetic durable-agent exercise with simulated deadlines only. No customer system or model provider was contacted. '
          'This is not autonomous model planning, authenticated evidence or production readiness.')


def simulate_late_claim(app,run_id,tick):
    """Move only this process's durable-worker clock after its claim commits."""
    clock=[now()];fired=[]
    def after_claim(session):
        if fired:return
        row=next((item for item in session.identity_map.values() if isinstance(item,DurableRun) and item.id==run_id and item.status=='processing'),None)
        if row is not None:fired.append(True);clock[0]=row.lease_until
    with patch.object(durable,'now',lambda:clock[0]):
        event.listen(app.state.factory.class_,'after_commit',after_claim)
        try:tick(run_id)
        finally:event.remove(app.state.factory.class_,'after_commit',after_claim)
    return bool(fired)


def run_drill(directory):
    root=Path(directory).resolve();root.mkdir(exist_ok=False)
    settings=Settings(database_url='sqlite:///'+(root/'control.db').as_posix(),mock_database=str(root/'business.db'),
        secret=secrets.token_urlsafe(48),agent_secret=secrets.token_urlsafe(48),frontend_dir=str(root/'no-frontend'),
        mode='local',policy_mode='reference',business_connector='synthetic',live_inference=0)
    result={'format':'nexus-synthetic-agent-drill','format_version':1,'release':__version__,'schema_version':CURRENT_SCHEMA,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'connector_mode':'synthetic','passed':False,
        'customer_acceptance':False,'production_ready':False,'steps':[],'boundary':BOUNDARY}
    app=None;logger=logging.getLogger('nexus.http');previously_disabled=logger.disabled;logger.disabled=True
    def check(name,condition):
        result['steps'].append({'id':name,'passed':bool(condition)})
        if not condition:raise DrillFailure(name)
    def expect(response,status):
        if response.status_code!=status:raise DrillFailure('unexpected_api_response')
        return response.json()
    def login(email):expect(client.post('/auth/local/login',json={'email':email,'password':password}),200)
    def headers():
        me=expect(client.get('/v1/me'),200);context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'],'X-Nexus-Context-Revision':str(context['revision'])}
    def create(body,key):return client.post('/v1/agent-runs',headers={**headers(),'Idempotency-Key':key},json=body)
    def detail(id):return expect(client.get('/v1/agent-runs/'+id,headers=headers()),200)
    def control(run,command):return client.post('/v1/agent-runs/'+run['id']+'/control',headers=headers(),json={
        'expected_version':run['version'],'command':command,'note':'Reviewed disposable agent control.'})
    def tick(id):
        with app.state.factory.begin() as db:db.execute(update(DurableRun).where(DurableRun.id==id).values(next_poll=0))
        return durable.run_flow_once(app.state.factory,settings)
    def decide(run):return client.post('/v1/agent-runs/'+run['id']+'/decision',headers=headers(),json={
        'expected_version':run['version'],'decision':'approve','note':'Independent review of disposable workflow.'})
    try:
        app=create_app(settings)
        check('synthetic_runtime_only',type(app.state.connector) is MockBusiness and settings.live_inference==0)
        migrate(app.state.engine,app.state.factory);password=secrets.token_urlsafe(32);seed(app.state.factory,password)
        with app.state.factory.begin() as db:
            db.add(Organization(id='agents-other',name='Disposable isolated workspace'));db.add(Policy(org_id='agents-other',version=1))
            other=User(org_id='agents-other',name='Synthetic isolated owner',email='other@drill.invalid',role='owner',password_hash=password_hash(password))
            db.add(other);db.flush();assign_staging(db,other)
            agent=db.scalar(select(Agent).where(Agent.name=='Procurement Atlas'))
            supplier=db.scalar(select(Tool).where(Tool.kind=='supplier'));purchase=db.scalar(select(Tool).where(Tool.kind=='purchase'))
            agent_id,supplier_id,purchase_id=agent.id,supplier.id,purchase.id
        checkpoint={'kind':'checkpoint','label':'Validate synthetic input'};output={'kind':'output','label':'Record verified synthetic outcome'}
        review={'kind':'approval','label':'Independent workflow review'}
        body={'name':'Disposable governed agent workflow','agent_id':agent_id,'steps':[checkpoint,
            {'kind':'governed_action','label':'Read synthetic supplier','tool_id':supplier_id,'request':{
                'action':'supplier:read','resource':'suppliers','arguments':{'supplier_id':'SUP-DEMO-104'}}},review,
            {'kind':'governed_action','label':'Synthetic purchase timeout','tool_id':purchase_id,'request':{
                'action':'purchase:create','resource':'purchase_requests','arguments':{'supplier_id':'SUP-DEMO-104','amount':'12500.00',
                'currency':'USD','purpose':'Disposable durable recovery exercise'},'simulation':'timeout_after_commit'}},output]}
        key='synthetic-agent-main-001'
        with TestClient(app) as client:
            check('anonymous_run_access_blocked',client.get('/v1/agent-runs').status_code==401)
            login('owner@nexus.local')
            check('run_creation_requires_csrf',client.post('/v1/agent-runs',headers={'Idempotency-Key':key},json=body).status_code==403)
            run=expect(create(body,key),201);replay=expect(create(body,key),201)
            recovered=expect(client.post('/v1/agent-runs/recover',headers=headers(),json={'key':key}),200)
            check('run_replay_recovery_has_no_effect',run['id']==replay['id']==recovered['id'] and app.state.connector.count()==0)
            check('changed_run_intent_rejected',create({**body,'name':'Changed immutable intent'},key).status_code==409)
            paused=expect(control(run,'pause'),200);tick(run['id'])
            check('pause_prevents_checkpoint_advancement',detail(run['id'])['cursor']==0 and app.state.connector.count()==0)
            check('stale_resume_rejected',control(run,'resume').status_code==409)
            expect(control(paused,'resume'),200);tick(run['id'])
            current=detail(run['id'])
            check('resume_advances_only_checkpoint',current['cursor']==1 and current['status']=='queued' and app.state.connector.count()==0)
            tick(run['id']);current=detail(run['id'])
            check('supplier_intent_waits_for_business_worker',current['status']=='waiting_action' and current['steps'][1]['action_id'] and app.state.connector.count()==0)
            dispatched=run_once(app.state.factory,settings,app.state.connector);tick(run['id']);tick(run['id']);current=detail(run['id'])
            check('verified_supplier_reaches_independent_review',dispatched and current['status']=='waiting_review' and current['cursor']==2 and app.state.connector.count()==1)
            check('author_checkpoint_approval_blocked',decide(current).status_code==403)
            login('reviewer@nexus.local');approved=expect(decide(current),200)
            check('independent_checkpoint_approval',approved['status']=='queued' and approved['cursor']==3)
            tick(run['id']);waiting=detail(run['id']);action_id=waiting['steps'][3]['action_id']
            with app.state.factory() as db:action_status=db.get(Action,action_id).status
            check('purchase_still_requires_business_approval',waiting['status']=='waiting_action' and action_status=='awaiting_approval' and app.state.connector.count()==1)
            approvals=expect(client.get('/v1/approvals',headers=headers()),200)
            approval=next(item for item in approvals if item['action_id']==action_id)
            decision={'decision':'approve','expected_version':approval['version'],'request_hash':approval['payload_hash'],'comment':'Independent disposable purchase review.'}
            check('changed_business_approval_hash_rejected',client.post('/v1/approvals/'+approval['id']+'/decision',headers=headers(),json={**decision,'request_hash':'0'*64}).status_code==409)
            expect(client.post('/v1/approvals/'+approval['id']+'/decision',headers=headers(),json=decision),200)
            dispatched=run_once(app.state.factory,settings,app.state.connector);login('owner@nexus.local');tick(run['id']);unknown=detail(run['id'])
            check('timeout_after_commit_remains_unknown',dispatched and unknown['status']=='outcome_unknown' and app.state.connector.count()==2)
            check('uncertain_action_retry_blocked',control(unknown,'retry').status_code==409)
            tick(run['id']);tick(run['id']);replayed=expect(create(body,key),201)
            check('unknown_poll_and_replay_do_not_repeat_effect',replayed['id']==run['id'] and replayed['status']=='outcome_unknown' and app.state.connector.count()==2)
            cancelled=expect(control(replayed,'cancel'),200)
            check('cancel_does_not_claim_to_undo_unknown_effect',cancelled['status']=='outcome_unknown' and cancelled['cancel_requested']==1 and app.state.connector.count()==2)
            reconciled=expect(client.post('/v1/actions/'+action_id+'/reconcile',headers=headers()),200);tick(run['id']);finished=detail(run['id'])
            check('reconciliation_finishes_cancellation_without_retry',reconciled['status']=='verified' and finished['status']=='cancelled' and finished['steps'][-1]['status']=='cancelled' and app.state.connector.count()==2)
            login('other@drill.invalid')
            check('other_workspace_cannot_read_recover_or_control',client.get('/v1/agent-runs/'+run['id'],headers=headers()).status_code==404 and
                client.post('/v1/agent-runs/recover',headers=headers(),json={'key':key}).status_code==404 and control(finished,'cancel').status_code==404)
            login('owner@nexus.local')
            expiring=expect(create({'name':'Disposable paused review expiry','agent_id':agent_id,'steps':[checkpoint,review,output]},'synthetic-agent-expiry-001'),201)
            tick(expiring['id']);tick(expiring['id']);expiring=detail(expiring['id']);expect(control(expiring,'pause'),200)
            with app.state.factory.begin() as db:db.get(DurableRun,expiring['id']).review_until=now()-1
            tick(expiring['id']);expired=detail(expiring['id'])
            check('simulated_overdue_paused_review_expires',expired['status']=='expired' and expired['steps'][expired['cursor']]['status']=='expired' and app.state.connector.count()==2)
            leased=expect(create({'name':'Disposable late claim recovery','agent_id':agent_id,'steps':[checkpoint,output]},'synthetic-agent-lease-001'),201)
            injected=simulate_late_claim(app,leased['id'],tick);recovered=detail(leased['id'])
            check('simulated_late_claim_recovers_before_step',injected and recovered['status']=='queued' and recovered['cursor']==0 and recovered['recoveries']==1 and recovered['error']=='WORKER_LEASE_EXPIRED')
            tick(leased['id']);tick(leased['id']);completed=detail(leased['id'])
            check('recovered_workflow_can_finish',completed['status']=='succeeded' and completed['recoveries']==1 and app.state.connector.count()==2)
            with app.state.factory() as db:
                count=db.scalar(select(func.count()).select_from(Action));runs=db.scalar(select(func.count()).select_from(DurableRun))
            check('only_two_synthetic_effects_and_three_runs',count==2 and runs==3 and app.state.connector.count()==2)
            result['synthetic_effect_count']=2;result['run_count']=3;result['passed']=True
    except DrillFailure as exc:result['failure']=str(exc)
    except Exception:result['failure']='isolated_drill_could_not_finish'
    finally:
        if app is not None:app.state.engine.dispose()
        gc.collect();logger.disabled=previously_disabled
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run disposable synthetic durable-agent checks without operator settings.')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/drills')
    args=parser.parse_args(argv)
    try:
        destination=args.output_dir.resolve();destination.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.agents-',dir=destination) as scratch:
            if Path(scratch).resolve().parent!=destination:raise ValueError('Invalid temporary directory')
            result=run_drill(Path(scratch)/'workspace')
        report=destination/('synthetic-agents-'+uuid.uuid4().hex+'.json')
        with report.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2)
        print(json.dumps({'passed':result['passed'],'steps_passed':sum(row['passed'] for row in result['steps']),'report':str(report),'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError,ValueError):
        print(json.dumps({'passed':False,'failure':'Could not create or clean up the disposable drill report.','boundary':BOUNDARY}));return 1


if __name__=='__main__':raise SystemExit(main())
