"""Synthetic internal contexts do not enable public environment switching."""
from contextlib import contextmanager
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update, func
from conftest import auth, submit
from nexus.db import User, Agent, WorkspaceAsset, AssetRevision, DurableRun, DurableStep, Action
from nexus.runtime_context import bind_runtime_context
from nexus.workbench import register_workbench, execute_preview, snapshot, RunInput as PreviewInput
from nexus.durable import register_durable, run_flow_once, serialize, step_for
from nexus.service import canonical
from nexus.security import digest


@pytest.fixture
def internal(ctx):
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
        owner_id=owner.id
        agent=Agent(org_id=owner.org_id,env='production',name='Synthetic production agent',owner_id=owner.id,status='active')
        db.add(agent);db.flush();agent_id=agent.id
    selected={'environment':'production'}
    def human(request,db,*args,**kwargs):
        user=db.get(User,owner_id);bind_runtime_context(db,user.org_id,selected['environment']);return user
    app=FastAPI();register_workbench(app,ctx['db'],ctx['settings'],human);register_durable(app,ctx['db'],ctx['settings'],human)
    with TestClient(app) as client:
        yield {'client':client,'selected':selected,'owner':owner_id,'agent':agent_id}


def asset(client,kind='knowledge',name='Production source',config=None):
    response=client.post('/v1/workbench',json={'kind':kind,'name':name,'config':config or {'content':'productiononly needle source text','source':'Synthetic','chunk_size':700,'language':'English'}})
    assert response.status_code==201,response.text
    return response.json()


def run(client,agent_id,key='production-run-key-001'):
    response=client.post('/v1/agent-runs',headers={'Idempotency-Key':key},json={'name':'Synthetic context run','agent_id':agent_id,'steps':[{'kind':'checkpoint','label':'Check context'},{'kind':'output','label':'Finish preview'}]})
    assert response.status_code==201,response.text
    return response.json()


def test_internal_asset_lifecycle_history_and_run_keep_environment(ctx,internal):
    client=internal['client'];doc=asset(client);url='/v1/workbench/'+doc['id']
    body={k:doc[k] for k in ('kind','name','description','config')};body['expected_version']=1
    changed=client.put(url,json=body);assert changed.status_code==200,changed.text
    assert changed.json()['env']=='production'
    validated=client.post(url+'/validate',json={'expected_version':2});assert validated.status_code==200,validated.text
    preview=client.post(url+'/run',json={'query':'needle'});assert preview.status_code==200,preview.text
    assert preview.json()['env']=='production'
    assert {h['asset_id'] for h in preview.json()['result']['citations']}=={doc['id']}
    history=client.get(url+'/history').json()
    assert [r['version'] for r in history]==[3,2,1]
    assert all(r['env']==r['snapshot']['env']=='production' for r in history)
    internal['selected']['environment']='staging'
    assert client.get('/v1/workbench').json()['assets']==[]
    assert client.get('/v1/workbench').json()['runs']==[]
    assert client.get(url+'/history').status_code==404
    assert client.post(url+'/archive',json={'expected_version':3}).status_code==404
    internal['selected']['environment']='production'
    assert client.post(url+'/archive',json={'expected_version':3}).status_code==200


def test_starter_is_idempotent_within_each_internal_environment(ctx,internal):
    client=internal['client']
    for environment in ('staging','production'):
        internal['selected']['environment']=environment
        assert client.post('/v1/workbench-starter').json()['created']==18
        assert client.post('/v1/workbench-starter').json()['created']==0
        listing=client.get('/v1/workbench').json()
        assert listing['schema_version']==9 and len(listing['assets'])==18
        assert {a['env'] for a in listing['assets']}=={environment}
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(AssetRevision))==36


def test_workflow_references_corpus_and_guardrails_use_internal_context(ctx,internal):
    client=internal['client'];prod=asset(client)
    internal['selected']['environment']='staging'
    stage=asset(client,name='Stage source',config={'content':'stagingonly needle evidence text'})
    asset(client,'guardrail','Stage blocker',{'blocked_terms':['needle'],'detect_email':False,'detect_override':False,'mode':'block'})
    internal['selected']['environment']='production'
    nodes=[{'id':'in','kind':'input','label':'Input'},{'id':'search','kind':'retrieve','label':'Retrieve','ref_id':stage['id'],'ref_version':1},{'id':'guard','kind':'guardrail','label':'Guard'},{'id':'out','kind':'output','label':'Output'}]
    rejected=client.post('/v1/workbench',json={'kind':'workflow','name':'Foreign source reference','config':{'nodes':nodes}})
    assert rejected.status_code==404,rejected.text
    nodes[1]['ref_id']=prod['id']
    flow=asset(client,'workflow','Scoped workflow',{'nodes':nodes})
    result=client.post('/v1/workbench/'+flow['id']+'/run',json={'query':'needle'}).json()
    assert result['status']=='completed'
    assert {h['asset_id'] for h in result['result']['citations']}=={prod['id']}
    assert 'stagingonly' not in str(result)


def test_cached_foreign_asset_cannot_preview_or_snapshot(ctx,internal):
    doc=asset(internal['client'])
    with ctx['db']() as db:
        row=db.get(WorkspaceAsset,doc['id']);owner=db.get(User,internal['owner'])
        bind_runtime_context(db,owner.org_id,'staging')
        for operation in (lambda:execute_preview(db,owner,row,PreviewInput(query='needle'),ctx['settings']),lambda:snapshot(db,row,owner)):
            with pytest.raises(HTTPException) as denied:operation()
            assert denied.value.status_code==404


def test_internal_durable_creation_recovery_control_and_worker_gate(ctx,internal):
    client=internal['client'];created=run(client,internal['agent']);url='/v1/agent-runs/'+created['id']
    assert created['env']=='production' and {s['env'] for s in created['steps']}=={'production'}
    assert client.post('/v1/agent-runs/recover',json={'key':'production-run-key-001'}).json()['id']==created['id']
    paused=client.post(url+'/control',json={'expected_version':1,'command':'pause','note':'Pause synthetic context run.'})
    assert paused.status_code==200,paused.text
    resumed=client.post(url+'/control',json={'expected_version':paused.json()['version'],'command':'resume','note':'Resume synthetic context run.'})
    assert resumed.status_code==200,resumed.text
    internal['selected']['environment']='staging'
    assert client.get('/v1/agent-runs').json()['items']==[]
    assert client.get(url).status_code==404
    assert client.post('/v1/agent-runs/recover',json={'key':'production-run-key-001'}).status_code==404
    with ctx['db']() as db:
        cached=db.get(DurableRun,created['id']);bind_runtime_context(db,cached.org_id,'staging')
        with pytest.raises(RuntimeError):serialize(db,cached)
        with pytest.raises(RuntimeError):step_for(db,cached)
    # Internal binding is no runtime grant: the real worker still refuses production.
    assert run_flow_once(ctx['db'],ctx['settings'])
    internal['selected']['environment']='production'
    failed=client.get(url).json();assert failed['status']=='failed' and failed['error']=='REQUESTER_REVOKED'
    assert client.post(url+'/control',json={'expected_version':failed['version'],'command':'cancel','note':'Cancel synthetic context run.'}).status_code==409
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0


def test_cancellation_cannot_mutate_a_foreign_context_action(ctx,internal):
    action=submit(ctx).json();created=run(internal['client'],internal['agent'])
    with ctx['db'].begin() as db:
        step=db.scalar(select(DurableStep).where(DurableStep.run_id==created['id'],DurableStep.position==0));step.action_id=action['id']
    response=internal['client'].post('/v1/agent-runs/'+created['id']+'/control',json={'expected_version':1,'command':'cancel','note':'Reject a foreign linked action.'})
    assert response.status_code==409,response.text
    assert response.json()['detail']['code']=='ACTION_MISSING'
    with ctx['db']() as db:
        assert db.get(Action,action['id']).status==action['status']
        assert db.get(DurableRun,created['id']).cancel_requested==0


def test_worker_claim_context_fences_relabelled_run(ctx,internal):
    # A deliberately incomplete maintenance fixture has no step FK to relabel.
    with ctx['db'].begin() as db:
        definition={'steps':[{'kind':'checkpoint','label':'Do not execute'}]}
        record=DurableRun(org_id='northstar',env='staging',name='Maintenance fixture',agent_id=internal['agent'],generation=1,author_id=internal['owner'],definition=definition,payload_hash=digest(canonical(definition)),request_digest='synthetic',idem_key='claim-fence-001')
        db.add(record);db.flush();run_id=record.id
    class InterleavedFactory:
        calls=0
        @contextmanager
        def begin(self):
            self.calls+=1
            if self.calls==2:
                with ctx['db'].begin() as db:db.execute(update(DurableRun).where(DurableRun.id==run_id).values(env='production'))
            with ctx['db'].begin() as db:yield db
    assert run_flow_once(InterleavedFactory(),ctx['settings'])
    with ctx['db']() as db:
        record=db.get(DurableRun,run_id)
        assert record.env=='production' and record.status=='processing' and record.error==''
        assert db.scalar(select(func.count()).select_from(Action))==0


@pytest.mark.parametrize('route',['/v1/workbench','/v1/agent-runs'])
def test_public_context_selection_remains_disabled(ctx,route):
    headers,_=auth(ctx);headers['X-Nexus-Environment']='production'
    assert ctx['client'].get(route,headers=headers).status_code==409
