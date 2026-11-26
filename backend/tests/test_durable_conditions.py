import copy
import pytest
from sqlalchemy import select, func
from conftest import auth, approve
from test_durable import body, advance, control
from nexus import durable
from nexus.db import DurableRun, DurableStep, Action
from nexus.service import canonical
from nexus.security import digest


def request(ctx,allowed=None,simulation='normal'):
    value=body(ctx,simulation=simulation)
    value['steps'].insert(2,{'kind':'condition','label':'Reviewed supplier allowlist','condition':{
        'kind':'supplier_allowlist','source_step':1,'supplier_ids':allowed or ['SUP-DEMO-104']}})
    return value


def create(ctx,allowed=None,simulation='normal'):
    h,_=auth(ctx);h['Idempotency-Key']='supplier-condition-0001'
    response=ctx['client'].post('/v1/agent-runs',headers=h,json=request(ctx,allowed,simulation))
    assert response.status_code==201,response.text
    return response.json()


def export(ctx,run):
    auth(ctx);return ctx['client'].get('/v1/agent-runs/'+run['id']+'/evidence')


def test_match_keeps_both_independent_approval_gates_and_one_purchase(ctx):
    run=create(ctx);run=advance(ctx,run['id'])
    assert run['status']=='waiting_review' and run['steps'][2]['result']['matched'] is True
    assert ctx['connector'].count()==1
    h,_=auth(ctx,'approver');assert ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={
        'expected_version':run['version'],'decision':'approve','note':'Reviewed conditional purchase.'}).status_code==200
    run=advance(ctx,run['id']);assert run['status']=='waiting_action'
    with ctx['db']() as db:assert db.get(Action,run['steps'][4]['action_id']).status=='awaiting_approval'
    assert approve(ctx).status_code==200
    run=advance(ctx,run['id']);assert run['status']=='succeeded' and ctx['connector'].count()==2
    report=export(ctx,run);assert report.status_code==200,report.text
    assert report.json()['payload']['steps'][2]['condition']['matched'] is True
    advance(ctx,run['id']);assert ctx['connector'].count()==2


def test_nonmatch_skips_purchase_and_reports_route_without_supplier_values(ctx):
    run=create(ctx,['SUP-PRIVATE-SENTINEL']);run=advance(ctx,run['id'])
    assert run['status']=='succeeded' and run['steps'][2]['result']['matched'] is False
    assert [s['status'] for s in run['steps']]==['completed','completed','completed','skipped','skipped','completed']
    assert not run['steps'][4]['action_id'] and ctx['connector'].count()==1
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==1
    report=export(ctx,run);assert report.status_code==200,report.text
    assert 'SUP-PRIVATE-SENTINEL' not in report.text and 'SUP-DEMO-104' not in report.text
    payload=report.json()['payload'];assert payload['steps'][4]['skipped_by']==2
    assert report.json()['integrity']['digest']==digest(canonical(payload))


@pytest.mark.parametrize('fault',['missing_action','scope','request','result','principal'])
def test_condition_refuses_inconsistent_verified_sources(ctx,fault):
    run=create(ctx)
    run=advance(ctx,run['id'],count=3);assert run['cursor']==2
    with ctx['db'].begin() as db:
        source=db.scalar(select(DurableStep).where(DurableStep.run_id==run['id'],DurableStep.position==1))
        action=db.get(Action,source.action_id)
        if fault=='missing_action':source.action_id=None
        elif fault=='scope':action.requester_id='other-requester'
        elif fault=='request':
            action.envelope={**action.envelope,'schema_version':999};action.payload_hash=digest(canonical(action.envelope))
        elif fault=='result':action.verification={'matched':True,'result':{'supplier_id':'OTHER','state':'found','external_ref':action.external_ref}}
        else:action.principal='other-principal'
    run=advance(ctx,run['id']);assert run['status']=='failed' and run['error']=='CONDITION_SOURCE_INCONSISTENT'
    assert ctx['connector'].count()==1


@pytest.mark.parametrize('fault',['submitted','missing'])
def test_nonmatch_cannot_skip_submitted_or_missing_steps(ctx,fault):
    run=create(ctx,['OTHER']);run=advance(ctx,run['id'],count=3)
    assert run['cursor']==2
    with ctx['db'].begin() as db:
        later=db.scalar(select(DurableStep).where(DurableStep.run_id==run['id'],DurableStep.position==4))
        if fault=='submitted':later.action_id='already-submitted-sentinel'
        else:db.delete(later)
    run=advance(ctx,run['id']);assert run['status']=='failed' and run['error']=='CONDITION_TARGET_CHANGED'
    assert ctx['connector'].count()==1


@pytest.mark.parametrize('change',['forward','purchase_source','different_supplier','empty','duplicate','expression','not_condition'])
def test_invalid_conditions_are_rejected_before_creating_runs(ctx,change):
    value=request(ctx)
    if change=='forward':value['steps'][2]['condition']['source_step']=4
    elif change=='purchase_source':value['steps'][1]=copy.deepcopy(value['steps'][4])
    elif change=='different_supplier':value['steps'][4]['request']['arguments']['supplier_id']='OTHER'
    elif change=='empty':value['steps'][2]['condition']['supplier_ids']=[]
    elif change=='duplicate':value['steps'][2]['condition']['supplier_ids']=['SAME','SAME']
    elif change=='expression':value['steps'][2]['condition']['expression']='execute anything'
    else:value['steps'][2]['kind']='checkpoint'
    h,_=auth(ctx);h['Idempotency-Key']='invalid-condition-001'
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=value).status_code==422
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(DurableRun))==0


def test_condition_rule_is_pinned_by_idempotency_and_recovery(ctx):
    run=create(ctx);h,_=auth(ctx);h['Idempotency-Key']='supplier-condition-0001'
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=request(ctx)).json()['id']==run['id']
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=request(ctx,['OTHER'])).status_code==409
    assert ctx['client'].post('/v1/agent-runs/recover',headers=h,json={'key':'supplier-condition-0001'}).json()['id']==run['id']
    assert ctx['connector'].count()==0


def test_paused_condition_does_not_select_a_route_until_resumed(ctx):
    run=create(ctx,['OTHER']);run=advance(ctx,run['id'],count=3);assert run['cursor']==2
    paused=control(ctx,run,'pause').json()
    assert advance(ctx,run['id'])['steps'][2]['status']=='pending'
    assert control(ctx,paused,'resume').status_code==200
    assert advance(ctx,run['id'])['status']=='succeeded' and ctx['connector'].count()==1


def test_uncertain_supplier_cannot_choose_a_route_until_original_action_is_reconciled(ctx):
    value=request(ctx,['OTHER']);value['steps'][1]['request']['simulation']='timeout_after_commit'
    h,_=auth(ctx);h['Idempotency-Key']='uncertain-supplier-condition'
    response=ctx['client'].post('/v1/agent-runs',headers=h,json=value);assert response.status_code==201
    run=advance(ctx,response.json()['id']);assert run['status']=='outcome_unknown'
    assert run['steps'][2]['status']=='pending' and ctx['connector'].count()==1
    assert control(ctx,run,'retry').status_code==409
    advance(ctx,run['id']);assert ctx['connector'].count()==1
    h,_=auth(ctx);assert ctx['client'].post('/v1/actions/'+run['steps'][1]['action_id']+'/reconcile',headers=h).status_code==200
    run=advance(ctx,run['id']);assert run['status']=='succeeded' and run['steps'][2]['result']['matched'] is False
    assert ctx['connector'].count()==1


@pytest.mark.parametrize('corrupt',['route','skipped_by'])
def test_evidence_rejects_false_branch_or_skip_claims(ctx,corrupt):
    run=create(ctx,['OTHER']);run=advance(ctx,run['id'])
    with ctx['db'].begin() as db:
        position=2 if corrupt=='route' else 4
        step=db.scalar(select(DurableStep).where(DurableStep.run_id==run['id'],DurableStep.position==position))
        step.result={**step.result,'matched':True} if corrupt=='route' else {'skipped_by':1}
    response=export(ctx,run);assert response.status_code==409
    assert response.json()['error']['code']=='RUN_EVIDENCE_INCONSISTENT'
