"""Disposable local alert policy and evaluation receipts; no transports."""
import pytest
from sqlalchemy import select, func
from conftest import auth, submit
from nexus.db import Action, WorkbenchRun, InferenceCall, IngestionJob, DurableRun, User
from nexus.security import password_hash
from nexus.environments import assign_staging
from nexus import operational_alerts as alerts

BASE='/v1/operational-alerts'
NOTE='Reviewed disposable operating thresholds.'


@pytest.fixture(autouse=True)
def operating_roles(ctx):
    with ctx['db'].begin() as db:
        for role in ('security','engineer'):
            user=User(org_id='northstar',email=role+'@synthetic.invalid',name='Synthetic '+role,role=role,password_hash=password_hash('synthetic-test-only'))
            db.add(user);db.flush();assign_staging(db,user)


def rule(metric='unknown_inference_count',threshold=1,enabled=True):
    return {'metric':metric,'threshold':threshold,'enabled':enabled,'severity':'critical'}


def save(ctx,rules=None,version=0,key='alert-policy-intent-0001',role='owner',org='northstar'):
    headers,_=auth(ctx,role,org);headers['Idempotency-Key']=key
    return ctx['client'].put(BASE+'/policy',json={'expected_version':version,'rules':[rule()] if rules is None else rules,'note':NOTE},headers=headers)


def sample(ctx,version=1,key='alert-sample-intent-0001',role='owner',org='northstar'):
    headers,_=auth(ctx,role,org);headers['Idempotency-Key']=key
    return ctx['client'].post(BASE+'/sample',json={'expected_version':version,'note':NOTE},headers=headers)


def call(ctx,status,created,org='northstar',env='staging',key='synthetic-call'):
    with ctx['db'].begin() as db:
        db.add(InferenceCall(org_id=org,env=env,author_id='synthetic',asset_id='synthetic',asset_version=1,period='2026-11',key_hash=key,request_hash='synthetic',status=status,created=created,reserved=1,input_rate='0',output_rate='0',result={'secret_prompt':'DO NOT EXPORT'}))


def test_default_disabled_gets_do_not_record_history(ctx):
    auth(ctx);data=ctx['client'].get(BASE).json()
    assert data['policy']['version']==0 and data['live']['status']=='disabled' and len(data['live']['values'])==7
    assert ctx['client'].get(BASE+'/history').json()['items']==[]
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkbenchRun))==0
    result=sample(ctx,version=0).json();assert result['status']=='disabled' and not result['stale_policy']


def test_threshold_boundary_snapshot_is_immutable_and_policy_history_is_explicit(ctx,monkeypatch):
    monkeypatch.setattr(alerts,'now',lambda:1000)
    call(ctx,'unknown',900)
    first=save(ctx);assert first.status_code==201,first.text
    result=sample(ctx);assert result.status_code==201,result.text
    recorded=result.json();assert recorded['status']=='firing' and recorded['rules'][0]['value']==1
    with ctx['db'].begin() as db:db.scalar(select(InferenceCall)).status='completed'
    assert ctx['client'].get(BASE).json()['live']['status']=='clear'
    assert save(ctx,[rule(threshold=2)],1,'alert-policy-intent-0002').status_code==201
    stored=ctx['client'].get(BASE+'/history').json()['items'][0]
    assert stored['id']==recorded['id'] and stored['status']=='firing' and stored['stale_policy']
    assert stored['values']['unknown_inference_count']==1 and stored['policy_version']==1
    revisions=ctx['client'].get(BASE+'/history?kind=policy').json()['items']
    assert {row['status'] for row in revisions}=={'active','superseded'}
    assert 'DO NOT EXPORT' not in str(stored) and 'fingerprint' not in str(stored)


def test_fixed_metrics_scope_cutoff_and_expired_lease_boundaries(ctx,monkeypatch):
    monkeypatch.setattr(alerts,'now',lambda:1000)
    call(ctx,'pending',700,key='at-cutoff');call(ctx,'pending',701,key='fresh')
    call(ctx,'unknown',0,org='other',key='other');call(ctx,'unknown',0,env='development',key='development')
    submitted=submit(ctx).json()
    with ctx['db'].begin() as db:
        action=db.get(Action,submitted['id']);action.status='queued';action.created=940
        db.add(IngestionJob(org_id='northstar',env='staging',author_id='synthetic',title='private-title',filename='private.pdf',format='pdf',language='eng',original_sha256='synthetic',original_bytes=0,idem_key='private',request_digest='synthetic',status='processing',lease_until=1000))
        db.add(WorkbenchRun(org_id='northstar',env='staging',author_id='synthetic',kind='neural_index_job',status='processing',result={'lease_until':999,'private':'not disclosed'},duration_ms=0))
        db.add(DurableRun(org_id='northstar',env='staging',author_id='synthetic',agent_id='synthetic',generation=1,name='private-run',definition={},payload_hash='synthetic',idem_key='synthetic',request_digest='synthetic',status='processing',lease_until=1001))
    auth(ctx);reading=ctx['client'].get(BASE).json()['live']
    assert reading['values']=={'oldest_queued_action_age_seconds':60,'unknown_action_count':0,'unknown_inference_count':0,'overdue_pending_inference_count':1,'expired_ingestion_lease_count':1,'expired_index_build_lease_count':1,'expired_agent_run_lease_count':0}
    assert 'private-title' not in str(reading) and 'private-run' not in str(reading)
    with ctx['db'].begin() as db:db.get(Action,submitted['id']).created=1001
    assert ctx['client'].get(BASE).json()['live']['values']['oldest_queued_action_age_seconds']==0


@pytest.mark.parametrize('role',['security','engineer','approver','auditor'])
def test_only_owner_changes_policy(ctx,role):
    assert save(ctx,role=role).status_code==403


@pytest.mark.parametrize('role',['approver','auditor'])
def test_sample_requires_operate_permission(ctx,role):
    assert sample(ctx,version=0,role=role).status_code==403


@pytest.mark.parametrize('role',['engineer','security'])
def test_operators_can_record_disabled_sample(ctx,role):
    assert sample(ctx,version=0,role=role).json()['status']=='disabled'


@pytest.mark.parametrize('bad',[rule(threshold=0),rule(threshold=True),rule(threshold=1.5),rule(metric='arbitrary_sql'),rule(enabled='true'),rule(metric='oldest_queued_action_age_seconds',threshold=604801)])
def test_invalid_rules_rejected(ctx,bad):
    assert save(ctx,[bad]).status_code==422


def test_duplicate_rules_and_missing_csrf_or_key_rejected(ctx):
    assert save(ctx,[rule(),rule()]).status_code==422
    headers,_=auth(ctx)
    body={'expected_version':0,'rules':[],'note':NOTE}
    assert ctx['client'].put(BASE+'/policy',json=body,headers=headers).status_code==422
    assert ctx['client'].put(BASE+'/policy',json=body,headers={'Idempotency-Key':'alert-policy-intent-0001'}).status_code==403


def test_idempotency_stale_version_and_own_recovery_never_reactivate(ctx):
    first=save(ctx).json();assert save(ctx).json()['id']==first['id']
    assert save(ctx,[rule(threshold=2)]).status_code==409
    assert save(ctx,[],version=0,key='alert-policy-intent-stale').status_code==409
    receipt=sample(ctx).json();assert sample(ctx).json()['id']==receipt['id']
    assert save(ctx,[],version=1,key='alert-policy-intent-0002').status_code==201
    assert sample(ctx,key='alert-sample-intent-stale').status_code==409
    headers,_=auth(ctx)
    recovered=ctx['client'].post(BASE+'/policy/recover',headers=headers,json={'key':'alert-policy-intent-0001'}).json()
    assert recovered['id']==first['id'] and recovered['status']=='superseded'
    recovered=ctx['client'].post(BASE+'/sample/recover',headers=headers,json={'key':'alert-sample-intent-0001'}).json()
    assert recovered['id']==receipt['id'] and recovered['stale_policy']
    assert sample(ctx).json()['id']==receipt['id']
    assert ctx['client'].get(BASE).json()['policy']['version']==2
    assert first['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])
    assert receipt['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])
    headers,_=auth(ctx,'security')
    assert ctx['client'].post(BASE+'/sample/recover',headers=headers,json={'key':'alert-sample-intent-0001'}).status_code==404
    headers,_=auth(ctx,org='other')
    assert ctx['client'].get(BASE).json()['policy']['version']==0
    assert ctx['client'].get(BASE+'/history').json()['items']==[]
    assert ctx['client'].post(BASE+'/policy/recover',headers=headers,json={'key':'alert-policy-intent-0001'}).status_code==404


def test_all_disabled_rules_remain_disabled_and_unconfigured_metrics_do_not_fire(ctx):
    call(ctx,'unknown',0)
    assert save(ctx,[rule(enabled=False)]).status_code==201
    assert sample(ctx).json()['status']=='disabled'
    assert save(ctx,[],1,'alert-policy-intent-0002').status_code==201
    assert sample(ctx,2,'alert-sample-intent-0002').json()['status']=='disabled'


@pytest.mark.parametrize('kind,capacity',[('policy',200),('sample',500)])
def test_bounded_history_refuses_new_writes_without_removing_old_receipts(ctx,kind,capacity):
    original=save(ctx).json()
    with ctx['db'].begin() as db:
        for i in range(capacity-(1 if kind=='policy' else 0)):
            db.add(WorkbenchRun(org_id='northstar',env='staging',author_id='synthetic',kind=alerts.POLICY if kind=='policy' else alerts.SAMPLE,status='superseded' if kind=='policy' else 'disabled',duration_ms=0,result={}))
    result=save(ctx,[],1,'alert-policy-capacity-0001') if kind=='policy' else sample(ctx)
    assert result.status_code==429 and result.json()['error']['code']=='ALERT_HISTORY_CAPACITY'
    assert ctx['client'].get(BASE).json()['policy']['id']==original['id']
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind==(alerts.POLICY if kind=='policy' else alerts.SAMPLE)))==capacity


def test_alert_receipts_reject_conflicting_context_and_revoked_environment(ctx):
    from test_runtime_context import revoke
    save(ctx);headers,user_id=auth(ctx)
    assert ctx['client'].get(BASE,headers={'X-Nexus-Workspace':'other'}).status_code==403
    assert ctx['client'].get(BASE+'/history',headers={'X-Nexus-Environment':'production'}).status_code==409
    revoke(ctx,user_id)
    assert ctx['client'].get(BASE).status_code==403
    assert ctx['client'].get(BASE+'/history').status_code==403
    assert ctx['client'].post(BASE+'/policy/recover',headers=headers,json={'key':'alert-policy-intent-0001'}).status_code==403
