import copy
import pytest
from sqlalchemy import select, func
from conftest import auth, approve
from test_durable import create, advance, control, body
from test_local_switching import prepare, switch, headers, current
from nexus.db import DurableRun, DurableStep, Action, Approval, Audit, User
from nexus.environments import assign_staging
from nexus.security import digest
from nexus.service import canonical


def export(ctx, run):
    return ctx['client'].get('/v1/agent-runs/'+run['id']+'/evidence')


def test_completed_snapshot_is_checksummed_private_and_read_only(ctx, monkeypatch):
    run=create(ctx,review=False,purchase=False);run=advance(ctx,run['id'])
    assert run['status']=='succeeded'
    with ctx['db'].begin() as db:
        action=db.get(Action,run['steps'][1]['action_id'])
        action.verification={**action.verification,'private':'credential-sentinel',
            'result':{**action.verification['result'],'raw':'raw-response-sentinel'}}
        before=canonical(action.verification)
        count=db.scalar(select(func.count()).select_from(Audit))
    def forbidden(*args,**kwargs):pytest.fail('Export contacted connector')
    monkeypatch.setattr(ctx['connector'],'invoke',forbidden)
    monkeypatch.setattr(ctx['connector'],'lookup',forbidden)
    response=export(ctx,run);assert response.status_code==200,response.text
    report=response.json();p=report['payload']
    assert response.headers['cache-control']=='no-store'
    assert report['integrity']['digest']==digest(canonical(p))
    assert report['integrity']['authenticated_signature'] is False
    assert p['schema_version']==11 and p['run']['status']=='succeeded'
    assert p['steps'][1]['action']['verified'] and p['connector']['mode']=='synthetic'
    for private in ('SUP-DEMO-104','credential-sentinel','raw-response-sentinel','Supplier lookup','durable-test-key-001'):
        assert private not in response.text
    with ctx['db']() as db:
        assert canonical(db.get(Action,run['steps'][1]['action_id']).verification)==before
        assert db.scalar(select(func.count()).select_from(Audit))==count
    assert ctx['connector'].count()==1


def test_checkpoint_review_and_pending_purchase_remain_separate(ctx):
    run=create(ctx);run=advance(ctx,run['id']);h,_=auth(ctx,'approver')
    assert ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={
        'expected_version':run['version'],'decision':'approve','note':'private-checkpoint-note'}).status_code==200
    run=advance(ctx,run['id']);auth(ctx,'auditor')
    p=export(ctx,run).json()['payload']
    assert p['run']['status']=='waiting_action'
    assert p['steps'][2]['review']=={'decision':'approve','independent_reviewer_recorded':True}
    purchase=p['steps'][3]['action']
    assert purchase['status']=='awaiting_approval' and not purchase['verified']
    assert purchase['approval']=={'status':'pending','version':1}
    assert 'private-checkpoint-note' not in canonical(p)
    assert ctx['connector'].count()==1


def test_unknown_cancelled_and_reconciled_snapshots_never_dispatch(ctx):
    run=create(ctx,review=False,simulation='timeout_after_commit');run=advance(ctx,run['id'])
    assert approve(ctx).status_code==200
    run=advance(ctx,run['id']);auth(ctx)
    p=export(ctx,run).json()['payload']
    assert p['run']['status']=='outcome_unknown' and not p['steps'][2]['action']['verified']
    assert control(ctx,run,'cancel').status_code==200
    auth(ctx);p=export(ctx,run).json()['payload']
    assert p['run']['cancel_requested'] and p['run']['status']=='outcome_unknown'
    assert p['steps'][2]['action']['status']=='outcome_unknown' and ctx['connector'].count()==2
    h,_=auth(ctx);assert ctx['client'].post('/v1/actions/'+run['steps'][2]['action_id']+'/reconcile',headers=h).status_code==200
    run=advance(ctx,run['id']);auth(ctx);p=export(ctx,run).json()['payload']
    assert p['run']['status']=='cancelled' and p['steps'][2]['action']['verified']
    assert ctx['connector'].count()==2


def test_export_permissions_workspace_environment_and_missing_run(ctx):
    run=create(ctx,review=False,purchase=False)
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        for role in ('engineer','security'):
            user=User(org_id='northstar',email=role+'@test.invalid',name=role,role=role,password_hash=owner.password_hash)
            db.add(user);db.flush();assign_staging(db,user)
    ctx['client'].cookies.clear();assert export(ctx,run).status_code==401
    for role in ('engineer','approver'):
        auth(ctx,role);assert export(ctx,run).status_code==403
    for role in ('owner','security','auditor'):
        auth(ctx,role);assert export(ctx,run).status_code==200
    auth(ctx,org='other');assert export(ctx,run).status_code==404
    auth(ctx);assert export(ctx,{'id':'missing'}).status_code==404
    state=prepare(ctx,key='sandbox');switch(ctx,state)
    assert ctx['client'].get('/v1/agent-runs/'+run['id']+'/evidence',headers=headers(current(ctx))).status_code==404


@pytest.mark.parametrize('corruption',['definition','step','missing_step','linked_action','envelope','verification','review'])
def test_inconsistent_ledgers_cannot_export_valid_evidence(ctx,corruption):
    run=create(ctx);run=advance(ctx,run['id'])
    with ctx['db'].begin() as db:
        row=db.get(DurableRun,run['id'])
        step=db.scalar(select(DurableStep).where(DurableStep.run_id==row.id,DurableStep.position==1))
        action=db.get(Action,step.action_id)
        if corruption=='definition':
            definition=copy.deepcopy(row.definition);definition['name']='tampered';row.definition=definition
        elif corruption=='step':step.kind='output'
        elif corruption=='missing_step':db.delete(step)
        elif corruption=='linked_action':action.principal='different-principal'
        elif corruption=='envelope':
            action.envelope={**action.envelope,'destination':'wrong'};action.payload_hash=digest(canonical(action.envelope))
        elif corruption=='verification':action.verification={'matched':False}
        else:
            review=db.scalar(select(DurableStep).where(DurableStep.run_id==row.id,DurableStep.kind=='approval'))
            review.status='completed';review.result={'decision':'approve','reviewer_id':row.author_id}
    auth(ctx);response=export(ctx,run)
    assert response.status_code==409,response.text
    assert response.json()['error']['code']=='RUN_EVIDENCE_INCONSISTENT'


def test_recorded_connector_mode_is_not_replaced_by_current_configuration(ctx):
    run=create(ctx,review=False,purchase=False)
    ctx['settings'].business_connector='http'
    assert export(ctx,run).json()['payload']['connector']['mode']=='synthetic'


def test_dispatch_blocked_action_can_be_reported_without_claiming_completion(ctx):
    run=create(ctx,review=False,purchase=False);run=advance(ctx,run['id'])
    with ctx['db'].begin() as db:
        row=db.get(DurableRun,run['id']);row.status='failed'
        step=db.scalar(select(DurableStep).where(DurableStep.run_id==row.id,DurableStep.position==1))
        step.status='blocked';db.get(Action,step.action_id).status='blocked'
    response=export(ctx,run);assert response.status_code==200,response.text
    p=response.json()['payload'];assert p['steps'][1]['action']['status']=='blocked'
    assert not p['steps'][1]['action']['verified']


def test_normalized_purchase_and_completed_business_approval_are_exportable(ctx):
    request=body(ctx,review=False)
    request['steps'][2]['request']['arguments']['amount']='012500.00'
    h,_=auth(ctx);h['Idempotency-Key']='durable-normalized-amount'
    response=ctx['client'].post('/v1/agent-runs',headers=h,json=request)
    assert response.status_code==201,response.text
    run=advance(ctx,response.json()['id'])
    assert export(ctx,run).status_code==200
    assert approve(ctx).status_code==200
    run=advance(ctx,run['id']);auth(ctx)
    response=export(ctx,run);assert response.status_code==200,response.text
    p=response.json()['payload'];assert p['run']['status']=='succeeded'
    assert p['steps'][2]['action']['verified'] and p['steps'][2]['action']['approval']['status']=='approved'
