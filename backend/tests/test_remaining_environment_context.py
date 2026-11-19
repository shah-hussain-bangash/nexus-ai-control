"""Internal resource propagation and identity binding; switching stays disabled."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import select, func
from conftest import auth, identifiers
from nexus.db import User, Agent, ReadinessEvidence, AssetRevision, SessionRecord, Audit
from nexus.readiness import register_readiness, readiness
from nexus.interfaces import register_interfaces
from nexus.workbench import register_workbench
from nexus.runtime_context import bind_runtime_context, bound_runtime_context
from nexus.security import session_user, issue_session, authenticate_agent, workload_token, permit


@pytest.fixture
def internal(ctx):
    headers,owner=auth(ctx)
    def human(request,db,write=False,permission=None):
        user=db.get(User,owner)
        bind_runtime_context(db,user.org_id,request.headers.get('X-Test-Context','staging'))
        if permission:permit(user,permission)
        return user
    app=FastAPI()
    register_readiness(app,ctx['db'],ctx['settings'],human)
    register_interfaces(app,ctx['db'],ctx['settings'],human)
    register_workbench(app,ctx['db'],ctx['settings'],human)
    with TestClient(app) as client:yield client


def evidence(version=0,outcome='passed'):
    return {'expected_version':version,'outcome':outcome,'summary':'Synthetic scoped admission test evidence; no production acceptance.','reference':'https://example.invalid/scoped-evidence'}


def test_readiness_evidence_versions_and_acceptance_stay_in_context(ctx,internal):
    url='/v1/production-readiness/traffic_controls'
    stage=internal.put(url,json=evidence(outcome='failed'));assert stage.status_code==200,stage.text
    prod=internal.put(url,headers={'X-Test-Context':'production'},json=evidence());assert prod.status_code==200,prod.text
    assert stage.json()['env']=='staging' and prod.json()['env']=='production'
    for environment,accepted in (('staging',0),('production',1)):
        report=internal.get('/v1/production-readiness',headers={'X-Test-Context':environment}).json()
        assert report['accepted']==accepted and report['production_ready'] is False
        records=[g['evidence'] for g in report['gates'] if g['evidence']]
        assert len(records)==1 and records[0]['env']==environment
    stale=internal.put(url,headers={'X-Test-Context':'production'},json=evidence());assert stale.status_code==409
    changed=internal.put(url,headers={'X-Test-Context':'production'},json=evidence(1,'failed'))
    assert changed.status_code==200 and changed.json()['version']==2
    # Operator evidence cannot turn missing lifecycle software into acceptance.
    assert internal.put('/v1/production-readiness/workspace_lifecycle',headers={'X-Test-Context':'production'},json=evidence()).status_code==422
    with ctx['db']() as db:
        rows=db.scalars(select(ReadinessEvidence)).all()
        assert {(r.env,r.version) for r in rows}=={('staging',1),('production',2)}
        events=db.scalars(select(Audit).where(Audit.event=='readiness.evidence_recorded')).all()
        assert sorted(r.env for r in events)==['production','production','staging']


def test_readiness_internal_helper_requires_bound_or_explicit_environment(ctx,internal):
    internal.put('/v1/production-readiness/traffic_controls',headers={'X-Test-Context':'production'},json=evidence())
    with ctx['db']() as db:
        with pytest.raises(RuntimeError):readiness(db,'northstar')
        assert readiness(db,'northstar','production')['accepted']==1
        bind_runtime_context(db,'northstar','staging')
        assert readiness(db,'northstar')['accepted']==0
        with pytest.raises(RuntimeError):readiness(db,'northstar','production')


def test_interface_starter_revisions_and_edits_are_separate_by_context(ctx,internal):
    ids={}
    for environment in ('staging','production'):
        h={'X-Test-Context':environment}
        created=internal.post('/v1/interface-starter',headers=h)
        assert created.status_code==200 and created.json()['created']==18
        assert internal.post('/v1/interface-starter',headers=h).json()['created']==0
        assets=internal.get('/v1/workbench',headers=h).json()['assets']
        assert len(assets)==18 and {a['env'] for a in assets}=={environment}
        ids[environment]=assets[0]['id']
        history=internal.get('/v1/workbench/'+assets[0]['id']+'/history',headers=h).json()
        assert len(history)==1 and history[0]['env']==history[0]['snapshot']['env']==environment
    assert ids['staging']!=ids['production']
    assert internal.get('/v1/workbench/'+ids['production']+'/history').status_code==404
    asset=next(a for a in internal.get('/v1/workbench').json()['assets'] if a['id']==ids['staging'])
    update={k:asset[k] for k in ('kind','name','description','config')};update.update(expected_version=1,name='Revised staging interface')
    changed=internal.put('/v1/workbench/'+ids['staging'],json=update);assert changed.status_code==200,changed.text
    prod_history=internal.get('/v1/workbench/'+ids['production']+'/history',headers={'X-Test-Context':'production'}).json()
    assert len(prod_history)==1 and prod_history[0]['snapshot']['name']!='Revised staging interface'
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(AssetRevision))==37


def request_with_session(ctx):
    return Request({'type':'http','method':'GET','path':'/v1/me','query_string':b'','headers':[(b'cookie',('nexus_session='+ctx['client'].cookies.get('nexus_session')).encode())]})


@pytest.mark.parametrize('context',[('northstar','production'),('other','staging')])
def test_human_auth_cannot_replace_a_different_bound_operation(ctx,context):
    _,owner=auth(ctx);request=request_with_session(ctx)
    with ctx['db']() as db:
        db.get(User,owner)  # Explicitly exercise the cached identity path.
        bind_runtime_context(db,*context)
        with pytest.raises(HTTPException) as denied:session_user(request,db)
        assert denied.value.status_code==409 and denied.value.detail['code']=='IDENTITY_CONTEXT_CHANGED'
        assert bound_runtime_context(db)==context and not db.new and not db.dirty


@pytest.mark.parametrize('context',[('northstar','production'),('other','staging')])
def test_session_issuance_cannot_cross_an_existing_binding(ctx,context):
    _,owner=auth(ctx)
    with ctx['db']() as db:
        user=db.get(User,owner);before=db.scalar(select(func.count()).select_from(SessionRecord))
        bind_runtime_context(db,*context)
        with pytest.raises(HTTPException) as denied:issue_session(db,user,ctx['settings'])
        assert denied.value.status_code==409 and not db.new
        assert bound_runtime_context(db)==context
        assert db.scalar(select(func.count()).select_from(SessionRecord))==before


@pytest.mark.parametrize('context',[('northstar','production'),('other','staging')])
def test_workload_auth_cannot_retarget_a_cached_operation(ctx,context):
    agent_id,_=identifiers(ctx)
    with ctx['db']() as db:
        agent=db.get(Agent,agent_id);token=workload_token(agent,ctx['settings'])
        bind_runtime_context(db,*context)
        with pytest.raises(HTTPException) as denied:authenticate_agent(token,db,ctx['settings'])
        assert denied.value.status_code==409
        assert bound_runtime_context(db)==context


def test_current_bound_session_auth_and_issuance_remain_compatible(ctx):
    _,owner=auth(ctx);request=request_with_session(ctx)
    with ctx['db'].begin() as db:
        bind_runtime_context(db,'northstar','staging')
        assert session_user(request,db).id==owner
        assert session_user(request,db).id==owner
        token,csrf=issue_session(db,db.get(User,owner),ctx['settings'])
        assert token and csrf and bound_runtime_context(db)==('northstar','staging')
        agent_id,_=identifiers(ctx)
        agent=db.get(Agent,agent_id)
        assert authenticate_agent(workload_token(agent,ctx['settings']),db,ctx['settings']).id==agent_id


@pytest.mark.parametrize('path',['/v1/production-readiness','/v1/interface-catalog'])
def test_remaining_public_resources_still_reject_production_selection(ctx,path):
    headers,_=auth(ctx);headers['X-Nexus-Environment']='production'
    assert ctx['client'].get(path,headers=headers).status_code==409
