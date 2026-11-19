import httpx
import pytest
from sqlalchemy import select,delete,update,func
from conftest import auth,submit,assign_staging
from nexus.db import (User,Agent,Tool,Action,Audit,EnvironmentAssignment,WorkspaceEnvironment,
                      DurableRun,DurableStep,IngestionJob,InferenceCall,InferenceBudget,Export,now,uid)
from nexus.security import workload_token
from nexus.runtime_context import bind_runtime_context
from nexus.worker import run_once
from nexus.durable import run_flow_once
from nexus.ingestion import run_ingestion_once


def revoke(ctx,user_id):
    with ctx['db'].begin() as db:
        db.execute(delete(EnvironmentAssignment).where(EnvironmentAssignment.user_id==user_id,
                   EnvironmentAssignment.org_id=='northstar',EnvironmentAssignment.environment_key=='staging'))


@pytest.mark.parametrize('path',['/v1/me','/v1/overview','/v1/agents','/v1/audit-events','/v1/workbench',
                                '/v1/documents','/v1/hybrid-search/history','/v1/runtime',
                                '/v1/production-readiness','/v1/settings','/v1/workspace-environments'])
def test_existing_sessions_lose_access_when_assignment_is_removed(ctx,path):
    _,owner_id=auth(ctx)
    revoke(ctx,owner_id)
    response=ctx['client'].get(path)
    assert response.status_code==403,response.text
    assert response.json()['error']['code']=='ENVIRONMENT_ACCESS_DENIED'


def test_password_login_cannot_recreate_a_removed_assignment(ctx):
    _,owner_id=auth(ctx)
    revoke(ctx,owner_id)
    response=ctx['client'].post('/auth/local/login',json={'email':'owner@nexus.local','password':'Test-Only-Password-123!'})
    assert response.status_code==403
    with ctx['db']() as db:
        assert not db.get(EnvironmentAssignment,(owner_id,'northstar','staging'))


def test_environment_must_remain_active_even_for_owner(ctx):
    auth(ctx)
    with ctx['db'].begin() as db:db.get(WorkspaceEnvironment,('northstar','staging')).state='preparing'
    assert ctx['client'].get('/v1/me').status_code==403


@pytest.mark.parametrize('headers,query,status',[
    ({'X-Nexus-Environment':'production'},'',409),
    ({'X-Nexus-Workspace':'other'},'',403),
    ({},'?env=production',409),
    ({},'?environment=production',409),
    ({},'?workspace=other',403),
    ({},'?org_id=other',403),
    ({},'?env=staging&env=production',400),
    ({'X-Nexus-Environment':'staging'},'?environment=production',400),
])
def test_unsupported_or_conflicting_context_is_rejected(ctx,headers,query,status):
    auth(ctx)
    response=ctx['client'].get('/v1/agents'+query,headers=headers)
    assert response.status_code==status,response.text
    assert 'Procurement Atlas' not in response.text


def test_implicit_and_explicit_current_context_remain_compatible(ctx):
    auth(ctx)
    assert ctx['client'].get('/v1/runtime-context').json()=={
        'workspace_id':'northstar','environment':'staging','access_checked':True,'switching_enabled':True}
    response=ctx['client'].get('/v1/runtime-context?workspace=northstar&env=staging',headers={
        'X-Nexus-Workspace':'northstar','X-Nexus-Environment':'staging'})
    assert response.status_code==200


def test_collection_views_and_counts_hide_non_current_environment(ctx):
    _,owner_id=auth(ctx)
    stage_action=submit(ctx,amount='3000.00').json()
    with ctx['db'].begin() as db:
        agent=Agent(org_id='northstar',env='production',name='Private production agent',owner_id=owner_id,risk='low')
        tool=Tool(org_id='northstar',env='production',name='Private production tool',kind='purchase',risk='high',schema_json={})
        db.add_all([agent,tool]);db.flush()
        source=db.get(Action,stage_action['id'])
        values={c.name:getattr(source,c.name) for c in Action.__table__.columns if c.name not in ('id','agent_id','tool_id','env','principal','idem_key','trace_id')}
        db.add(Action(**values,env='production',agent_id=agent.id,tool_id=tool.id,principal='agent:'+agent.id,idem_key='private-production-key',trace_id=uid()))
        db.add(Audit(org_id='northstar',env='production',actor=owner_id,event='private.production.marker'))
        db.flush();agent_id=agent.id
    agents=ctx['client'].get('/v1/agents')
    assert agents.status_code==200 and len(agents.json())==3 and 'Private production' not in agents.text
    assert ctx['client'].get('/v1/overview').json()['agents']==3
    assert ctx['client'].get('/v1/overview').json()['actions']==1
    actions=ctx['client'].get('/v1/actions').json()
    assert len(actions)==1 and actions[0]['id']==stage_action['id']
    assert ctx['client'].get('/v1/audit-events?q=private.production.marker').json()==[]
    assert ctx['client'].get('/v1/agents/'+agent_id).status_code==404


def test_orm_bulk_operations_and_cached_queries_keep_context_scope(ctx):
    _,owner_id=auth(ctx)
    with ctx['db'].begin() as db:
        foreign=Agent(org_id='northstar',env='production',name='Production unchanged',owner_id=owner_id,risk='low')
        other=Agent(org_id='other',name='Other workspace agent',owner_id='other-user',risk='low')
        db.add_all([foreign,other]);db.flush();foreign_id=foreign.id;other_id=other.id
    with ctx['db'].begin() as db:
        bind_runtime_context(db,'northstar')
        assert len(db.scalars(select(Agent)).all())==3
        assert db.execute(update(Agent).where(Agent.id==foreign_id).values(name='Unauthorized edit')).rowcount==0
        assert db.execute(delete(Agent).where(Agent.id==foreign_id)).rowcount==0
        bind_runtime_context(db,'other')
        assert [a.id for a in db.scalars(select(Agent))]==[other_id]
        bind_runtime_context(db,'northstar')
        assert len(db.scalars(select(Agent)).all())==3
    with ctx['db']() as db:assert db.get(Agent,foreign_id).name=='Production unchanged'


def test_unit_of_work_rejects_cross_context_new_rows(ctx):
    with pytest.raises(RuntimeError,match='Cross-context'):
        with ctx['db'].begin() as db:
            bind_runtime_context(db,'northstar')
            db.add(Agent(org_id='other',name='Forbidden',owner_id='other-user',risk='low'))


def test_workload_gateway_rechecks_owner_environment_and_selectors(ctx):
    _,owner_id=auth(ctx)
    with ctx['db']() as db:
        agent=db.scalar(select(Agent).where(Agent.name=='Supplier Scout'))
        token=workload_token(agent,ctx['settings'])
    response=ctx['client'].get('/v1/gateway/actions/missing?env=production',headers={'Authorization':'Bearer '+token})
    assert response.status_code==409
    revoke(ctx,owner_id)
    assert ctx['client'].get('/v1/gateway/actions/missing',headers={'Authorization':'Bearer '+token}).status_code==403


def test_queued_business_effect_is_blocked_after_assignment_revocation(ctx):
    response=submit(ctx,amount='3000.00')
    assert response.status_code==202
    action_id=response.json()['id']
    with ctx['db']() as db:owner_id=db.get(Action,action_id).requester_id
    revoke(ctx,owner_id)
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    assert ctx['connector'].count()==0
    with ctx['db']() as db:
        row=db.get(Action,action_id)
        assert row.status=='blocked' and row.reason=='DISPATCH_ENVIRONMENT_ACCESS_CHANGED'


def production_action(ctx):
    source_id=submit(ctx,amount='12500.00').json()['id']
    with ctx['db'].begin() as db:
        source=db.get(Action,source_id)
        agent=Agent(org_id='northstar',env='production',name='Production-only agent',owner_id=source.requester_id,risk='low')
        tool=Tool(org_id='northstar',env='production',name='Production-only tool',kind='purchase',risk='high',schema_json={})
        db.add_all([agent,tool]);db.flush()
        values={c.name:getattr(source,c.name) for c in Action.__table__.columns if c.name not in ('id','agent_id','tool_id','env','principal','idem_key','trace_id','status')}
        row=Action(**values,env='production',agent_id=agent.id,tool_id=tool.id,principal='agent:'+agent.id,
                   idem_key='production-only-work',trace_id=uid(),status='queued')
        db.add(row);db.flush();return row.id


def test_blocked_background_work_keeps_its_audit_in_the_same_environment(ctx):
    action_id=production_action(ctx)
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    assert ctx['connector'].count()==0
    with ctx['db']() as db:
        assert db.get(Action,action_id).status=='blocked'
        events=db.scalars(select(Audit).where(Audit.action_id==action_id)).all()
        assert events and all(row.env=='production' for row in events)
    assert action_id not in ctx['client'].get('/v1/audit-events').text


def test_durable_reconciliation_rejects_a_cross_environment_action_link(ctx):
    from test_durable import create
    run=create(ctx,review=False,purchase=False)
    action_id=production_action(ctx)
    with ctx['db'].begin() as db:
        step=db.scalar(select(DurableStep).where(DurableStep.run_id==run['id'],DurableStep.position==0))
        step.action_id=action_id
    assert run_flow_once(ctx['db'],ctx['settings'])
    with ctx['db']() as db:
        row=db.get(DurableRun,run['id'])
        assert row.status=='failed' and row.error=='ACTION_MISSING'


def test_historical_mixed_environment_export_cannot_be_downloaded(ctx):
    _,owner_id=auth(ctx)
    with ctx['db'].begin() as db:
        row=Export(org_id='northstar',owner_id=owner_id,expires=now()+3600,
                   records=[{'org_id':'northstar','env':'production','detail':'Private historical export marker'}])
        db.add(row);db.flush();export_id=row.id
    response=ctx['client'].get('/v1/audit-exports/'+export_id+'/download')
    assert response.status_code==409 and response.json()['error']['code']=='EXPORT_SCOPE_CHANGED'
    assert 'Private historical export marker' not in response.text


def test_durable_run_cannot_advance_a_new_step_after_revocation(ctx):
    from test_durable import create
    run=create(ctx,review=False,purchase=False)
    with ctx['db']() as db:owner_id=db.get(DurableRun,run['id']).author_id
    revoke(ctx,owner_id)
    assert run_flow_once(ctx['db'],ctx['settings'])
    with ctx['db']() as db:
        row=db.get(DurableRun,run['id'])
        assert row.status=='failed' and row.error=='REQUESTER_REVOKED'
    assert ctx['connector'].count()==0


def test_intake_discards_result_if_assignment_is_revoked_during_extraction(ctx):
    from test_ingestion import create
    job=create(ctx)
    def extract(data,record,settings):
        revoke(ctx,record.author_id)
        return {'text':'Private extracted marker','info':{'method':'synthetic'}}
    assert run_ingestion_once(ctx['db'],ctx['settings'],extract)
    with ctx['db']() as db:
        row=db.get(IngestionJob,job['id'])
        assert row.status=='failed' and row.error_code=='REQUESTER_REVOKED'
        assert row.extracted_text==''


def test_search_withholds_results_if_environment_access_changes_during_compute(ctx,monkeypatch):
    from test_hybrid import corpus,search
    corpus(ctx)
    def compute(payload):
        with ctx['db']() as db:owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        revoke(ctx,owner.id)
        return {'scores':[],'rank':0,'vocabulary':0}
    monkeypatch.setattr('nexus.hybrid.compute',compute)
    response=search(ctx)
    assert response.status_code==403 and 'items' not in response.json()


def test_inference_denies_delivery_after_revocation_but_keeps_actual_accounting(ctx,monkeypatch):
    from test_inference import setup
    def provider(request):
        with ctx['db']() as db:owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        revoke(ctx,owner.id)
        return httpx.Response(200,json={'id':'synthetic-provider','choices':[{'message':{'content':'Private answer marker'},'finish_reason':'stop'}],
                                      'usage':{'prompt_tokens':12,'completion_tokens':4}})
    headers,body,sent=setup(ctx,monkeypatch,provider)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==403 and 'Private answer marker' not in response.text
    assert len(sent)==1
    with ctx['db']() as db:
        call=db.scalar(select(InferenceCall));budget=db.scalar(select(InferenceBudget))
        assert call.status=='completed' and call.charged==24
        assert budget.held==0 and budget.spent==24


def test_inference_rechecks_access_before_admitting_provider_work(ctx,monkeypatch):
    from test_inference import setup
    from nexus import inference
    headers,body,sent=setup(ctx,monkeypatch)
    route=inference.route
    def revoke_before_admission(config,settings):
        result=route(config,settings)
        with ctx['db']() as db:owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        revoke(ctx,owner.id)
        return result
    monkeypatch.setattr(inference,'route',revoke_before_admission)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==403 and not sent
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(InferenceCall))==0


def test_uncertain_inference_retains_reservation_but_denies_revoked_delivery(ctx,monkeypatch):
    from test_inference import setup
    def provider(request):
        with ctx['db']() as db:owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        revoke(ctx,owner.id)
        raise httpx.ReadTimeout('Synthetic uncertain transport',request=request)
    headers,body,sent=setup(ctx,monkeypatch,provider)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==403 and len(sent)==1
    with ctx['db']() as db:
        call=db.scalar(select(InferenceCall));budget=db.scalar(select(InferenceBudget))
        assert call.status=='unknown' and budget.held==call.reserved and budget.spent==0
