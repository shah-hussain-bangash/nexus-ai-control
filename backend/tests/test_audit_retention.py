"""Explicit payload retention in disposable databases; original events stay intact."""
import copy,time
import pytest
from sqlalchemy import select,func
from conftest import auth
from test_signed_audit import signing,create,download
from nexus import audit_retention as retention
from nexus.audit_signature import verify,canonical as signed_bytes
from nexus.db import WorkbenchRun,Audit

BASE='/v1/audit-retention'
NOTE='Reviewed disposable expired evidence retention.'


@pytest.fixture
def aged(ctx,signing,monkeypatch):
    first=create(ctx).json()
    monkeypatch.setattr(retention,'now',lambda:time.time()+60*86400)
    return first


def config(ctx,version=0,enabled=True,days=30,key='audit-retention-policy-0001',role='owner'):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].put(BASE+'/policy',headers=headers,json={'expected_version':version,'enabled':enabled,'minimum_age_days':days,'note':NOTE})


def preview(ctx,version=1,key='audit-retention-plan-0001'):
    headers,_=auth(ctx);headers['Idempotency-Key']=key
    return ctx['client'].post(BASE+'/plans',headers=headers,json={'expected_version':version,'note':NOTE})


def apply(ctx,plan,version=1,confirmation=retention.CONFIRM,note=NOTE):
    headers,_=auth(ctx)
    return ctx['client'].post(BASE+'/plans/'+plan['id']+'/apply',headers=headers,json={'expected_version':version,'confirmation':confirmation,'note':note})


def hold(ctx,snapshot,held=True,version=0):
    headers,_=auth(ctx)
    return ctx['client'].put(BASE+'/holds/'+snapshot['id'],headers=headers,json={'expected_version':version,'held':held,'note':NOTE})


def test_default_is_off_and_expiry_does_not_remove_payload(ctx,aged):
    auth(ctx);data=ctx['client'].get(BASE).json()
    assert not data['policy']['enabled'] and data['policy']['version']==0
    assert not data['items'][0]['eligible']
    assert preview(ctx,version=0).status_code==409
    with ctx['db']() as db:assert db.get(WorkbenchRun,aged['id']).result.get('envelope')


def test_preview_and_confirmed_apply_preserve_audit_and_replay_receipt(ctx,aged,signing):
    original=download(ctx,aged)
    assert config(ctx).status_code==201
    plan=preview(ctx).json();assert plan['status']=='previewed' and [t['id'] for t in plan['targets']]==[aged['id']]
    with ctx['db']() as db:
        assert db.get(WorkbenchRun,aged['id']).status=='ready'
        event_ids=set(db.scalars(select(Audit.id)))
    assert apply(ctx,plan,confirmation='yes').status_code==422
    result=apply(ctx,plan);assert result.status_code==200,result.text
    assert result.json()['purged_count']==1 and result.json()['status']=='applied'
    assert apply(ctx,plan).json()==result.json()
    assert apply(ctx,plan,note='Different apply confirmation reason.').status_code==409
    with ctx['db']() as db:
        row=db.get(WorkbenchRun,aged['id'])
        assert row.status=='purged' and 'envelope' not in row.result
        assert row.result['payload_sha256'] and row.result['metadata']['key_id']==aged['key_id']
        assert event_ids<=set(db.scalars(select(Audit.id)))
    assert ctx['client'].get('/v1/signed-audit-evidence/'+aged['id']).status_code==410
    replay=create(ctx).json();assert replay['id']==aged['id'] and replay['status']=='purged'
    headers,_=auth(ctx)
    recovered=ctx['client'].post('/v1/signed-audit-evidence/recover',headers=headers,json={'key':'signed-audit-intent-0001'}).json()
    assert recovered['status']=='purged' and recovered['id']==aged['id']
    assert verify(signed_bytes(original),signing,'northstar','staging')['authenticated_signature']
    assert ctx['client'].get(BASE).json()['items']==[]
    assert aged['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


def test_active_hold_blocks_selection_and_requires_versioned_release(ctx,aged):
    config(ctx);protected=hold(ctx,aged).json();assert protected['held'] and protected['version']==1
    assert hold(ctx,aged,False,0).status_code==409
    assert preview(ctx).json()['targets']==[]
    assert hold(ctx,aged,False,1).json()['version']==2
    plan=preview(ctx,key='audit-retention-plan-0002').json()
    assert plan['targets'][0]['hold_version']==2 and apply(ctx,plan).json()['purged_count']==1
    assert hold(ctx,aged,True,2).status_code==404


def test_hold_added_then_released_still_invalidates_existing_preview(ctx,aged):
    config(ctx);plan=preview(ctx).json();hold(ctx,aged);hold(ctx,aged,False,1)
    response=apply(ctx,plan);assert response.status_code==409 and response.json()['error']['code']=='RETENTION_PLAN_STALE'
    with ctx['db']() as db:assert db.get(WorkbenchRun,aged['id']).status=='ready'


@pytest.mark.parametrize('change',['policy','expiry','payload','hold'])
def test_stale_plan_never_partially_purges(ctx,aged,change,monkeypatch):
    second=create(ctx,key='signed-audit-intent-0002').json()
    config(ctx);plan=preview(ctx).json();assert len(plan['targets'])==2
    if change=='policy':config(ctx,version=1,enabled=False,key='audit-retention-policy-0002')
    if change=='expiry':monkeypatch.setattr(retention,'now',lambda:plan['expires'])
    if change=='hold':hold(ctx,second)
    if change=='payload':
        with ctx['db'].begin() as db:
            row=db.get(WorkbenchRun,second['id']);value=copy.deepcopy(row.result);value['expires']+=1;row.result=value
    response=apply(ctx,plan);assert response.status_code==409,response.text
    with ctx['db']() as db:
        assert db.get(WorkbenchRun,aged['id']).status=='ready' and db.get(WorkbenchRun,second['id']).status=='ready'
        assert db.get(WorkbenchRun,plan['id']).status=='previewed'


def test_newly_eligible_snapshot_is_not_added_to_saved_plan(ctx,aged):
    config(ctx);plan=preview(ctx).json();second=create(ctx,key='signed-audit-intent-0002').json()
    assert apply(ctx,plan).json()['purged_count']==1
    with ctx['db']() as db:assert db.get(WorkbenchRun,second['id']).status=='ready'


@pytest.mark.parametrize('reason',['unexpired','young','foreign_payload','future'])
def test_only_old_expired_current_scope_payloads_are_eligible(ctx,aged,reason):
    config(ctx)
    with ctx['db'].begin() as db:
        row=db.get(WorkbenchRun,aged['id']);value=copy.deepcopy(row.result)
        if reason=='unexpired':value['expires']=retention.now()+1
        if reason=='young':value['envelope']['payload']['created_at_us']=int(retention.now()*1000000)
        if reason=='foreign_payload':value['envelope']['payload']['environment']='development'
        if reason=='future':row.created=retention.now()+1
        row.result=value
    assert preview(ctx).json()['targets']==[]


def test_policy_and_plan_recovery_are_own_scoped_and_never_apply(ctx,aged):
    first=config(ctx).json();assert config(ctx).json()['id']==first['id']
    assert config(ctx,days=31).status_code==409
    plan=preview(ctx).json();assert preview(ctx).json()['id']==plan['id']
    config(ctx,version=1,enabled=False,key='audit-retention-policy-0002')
    headers,_=auth(ctx)
    recovered=ctx['client'].post(BASE+'/policy/recover',headers=headers,json={'key':'audit-retention-policy-0001'}).json()
    assert recovered['id']==first['id'] and recovered['status']=='superseded'
    assert ctx['client'].post(BASE+'/plan/recover',headers=headers,json={'key':'audit-retention-plan-0001'}).json()['status']=='previewed'
    assert ctx['client'].get(BASE).json()['policy']['enabled'] is False
    headers,_=auth(ctx,org='other')
    assert ctx['client'].get(BASE).json()['items']==[] and ctx['client'].get(BASE).json()['policy']['version']==0
    assert ctx['client'].post(BASE+'/plan/recover',headers=headers,json={'key':'audit-retention-plan-0001'}).status_code==404
    assert ctx['client'].post(BASE+'/plans/'+plan['id']+'/apply',headers=headers,json={'expected_version':1,'confirmation':retention.CONFIRM,'note':NOTE}).status_code==404
    assert ctx['client'].put(BASE+'/holds/'+aged['id'],headers=headers,json={'expected_version':0,'held':True,'note':NOTE}).status_code==404


@pytest.mark.parametrize('role',['auditor','approver'])
def test_only_owner_can_manage_retention(ctx,aged,role):
    assert config(ctx,role=role).status_code==403
    headers,_=auth(ctx,role)
    headers['Idempotency-Key']='audit-retention-unauthorized'
    assert ctx['client'].get(BASE).status_code==403
    assert ctx['client'].post(BASE+'/plans',headers=headers,json={'expected_version':0,'note':NOTE}).status_code==403
    assert ctx['client'].put(BASE+'/holds/'+aged['id'],headers=headers,json={'expected_version':0,'held':True,'note':NOTE}).status_code==403


@pytest.mark.parametrize('days',[0,6,3651,True,7.5])
def test_retention_minimum_and_strict_integer_bound(ctx,days):
    assert config(ctx,days=days).status_code==422


def test_csrf_stale_policy_and_revoked_environment_block_changes(ctx,aged):
    first=config(ctx).json();assert config(ctx,key='audit-retention-policy-stale').status_code==409
    plan=preview(ctx).json()
    assert ctx['client'].post(BASE+'/plans/'+plan['id']+'/apply',json={'expected_version':1,'confirmation':retention.CONFIRM,'note':NOTE}).status_code==403
    assert ctx['client'].get(BASE,headers={'X-Nexus-Environment':'production'}).status_code==409
    from test_runtime_context import revoke
    _,owner_id=auth(ctx);revoke(ctx,owner_id)
    assert ctx['client'].get(BASE).status_code==403


def test_purging_frees_payload_capacity_but_keeps_receipts(ctx,aged):
    config(ctx);plan=preview(ctx).json();apply(ctx,plan)
    with ctx['db'].begin() as db:
        for i in range(99):db.add(WorkbenchRun(org_id='northstar',env='staging',author_id='capacity-fixture',kind='signed_audit_metadata',status='ready',duration_ms=0,result={}))
    assert create(ctx,key='signed-audit-after-retention').status_code==201
    assert create(ctx,key='signed-audit-over-capacity').status_code==429
    with ctx['db']() as db:assert db.get(WorkbenchRun,aged['id']).status=='purged'


def test_final_policy_history_slot_is_reserved_for_disabling(ctx,aged):
    config(ctx)
    with ctx['db'].begin() as db:
        for i in range(198):
            db.add(WorkbenchRun(org_id='northstar',env='staging',author_id='capacity-fixture',kind=retention.POLICY,status='superseded',duration_ms=0,result={'version':i+2,'enabled':True,'minimum_age_days':30,'note':NOTE}))
    assert config(ctx,version=1,days=31,key='audit-retention-over-capacity').status_code==429
    assert config(ctx,version=1,enabled=False,key='audit-retention-disable-capacity').status_code==201
    assert ctx['client'].get(BASE).json()['policy']['enabled'] is False
    assert config(ctx,version=2,key='audit-retention-no-enable-capacity').status_code==429
