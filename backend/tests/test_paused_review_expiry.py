import pytest
from sqlalchemy import select,update,func
from conftest import auth,identifiers
from nexus import durable
from nexus.db import DurableRun,DurableStep,Action,Audit,now


def request_body(ctx,name='Synthetic review expiry'):
    agent,_=identifiers(ctx,kind='supplier')
    return {'name':name,'agent_id':agent,'steps':[
        {'kind':'checkpoint','label':'Prepare synthetic input'},
        {'kind':'approval','label':'Independent synthetic review'},
        {'kind':'output','label':'Record reviewed result'}]}


def create(ctx,key='paused-review-expiry-key'):
    h,_=auth(ctx);h['Idempotency-Key']=key
    response=ctx['client'].post('/v1/agent-runs',headers=h,json=request_body(ctx))
    assert response.status_code==201,response.text
    return response.json()


def detail(ctx,id):return ctx['client'].get('/v1/agent-runs/'+id).json()


def control(ctx,run,command):
    h,_=auth(ctx)
    return ctx['client'].post('/v1/agent-runs/'+run['id']+'/control',headers=h,json={
        'expected_version':run['version'],'command':command,'note':'Reviewed synthetic checkpoint control.'})


def waiting_review(ctx):
    run=create(ctx)
    for _ in range(2):
        with ctx['db'].begin() as db:db.execute(update(DurableRun).where(DurableRun.id==run['id']).values(next_poll=0))
        assert durable.run_flow_once(ctx['db'],ctx['settings'])
    run=detail(ctx,run['id']);assert run['status']=='waiting_review'
    return run


@pytest.mark.parametrize('paused',[True,False])
def test_due_review_expires_run_and_checkpoint_even_when_paused(ctx,monkeypatch,paused):
    run=waiting_review(ctx)
    if paused:
        response=control(ctx,run,'pause');assert response.status_code==200;run=response.json()
    deadline=run['review_until'];monkeypatch.setattr(durable,'now',lambda:deadline)
    durable.run_flow_once(ctx['db'],ctx['settings'])
    expired=detail(ctx,run['id'])
    assert expired['status']=='expired' and expired['version']==run['version']+1
    assert expired['cursor']==run['cursor'] and expired['review_until']==deadline
    assert expired['steps'][expired['cursor']]['status']=='expired' and not expired['can_retry']
    assert control(ctx,expired,'resume').status_code==409 and control(ctx,expired,'retry').status_code==409
    h,_=auth(ctx,'approver')
    response=ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={
        'expected_version':expired['version'],'decision':'approve','note':'Attempt a decision after synthetic expiry.'})
    assert response.status_code==409
    assert not durable.run_flow_once(ctx['db'],ctx['settings'])
    with ctx['db']() as db:
        saved=db.get(DurableRun,run['id']);assert saved.version==expired['version'] and not saved.lease_token
        assert db.scalar(select(func.count()).select_from(Action))==0
        events=db.scalars(select(Audit).where(Audit.event=='agent_run.review_expired')).all()
        assert len(events)==1 and events[0].detail['run_id']==run['id'] and events[0].env=='staging'
    assert ctx['connector'].count()==0


def test_timely_paused_review_resumes_without_extending_deadline(ctx,monkeypatch):
    run=waiting_review(ctx);paused=control(ctx,run,'pause').json();deadline=run['review_until']
    monkeypatch.setattr(durable,'now',lambda:deadline-.01)
    assert not durable.run_flow_once(ctx['db'],ctx['settings'])
    current=detail(ctx,run['id']);assert current['status']=='paused' and current['version']==paused['version']
    response=control(ctx,current,'resume');assert response.status_code==200
    resumed=response.json();assert resumed['status']=='waiting_review' and resumed['review_until']==deadline
    h,_=auth(ctx,'approver')
    response=ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={
        'expected_version':resumed['version'],'decision':'approve','note':'Reviewed timely synthetic checkpoint.'})
    assert response.status_code==200 and response.json()['status']=='queued'
    # Once approved, an old resume_state/deadline must not expire queued work.
    monkeypatch.setattr(durable,'now',lambda:deadline+2)
    assert durable.run_flow_once(ctx['db'],ctx['settings'])
    assert detail(ctx,run['id'])['status']=='succeeded' and ctx['connector'].count()==0


def test_paused_checkpoint_without_pending_review_does_not_expire(ctx,monkeypatch):
    run=create(ctx);paused=control(ctx,run,'pause').json()
    assert paused['resume_state']=='queued' and paused['review_until']==0
    monkeypatch.setattr(durable,'now',lambda:now()+3600)
    assert not durable.run_flow_once(ctx['db'],ctx['settings'])
    current=detail(ctx,run['id']);assert current['status']=='paused' and current['version']==paused['version']
    assert control(ctx,current,'resume').status_code==200


def test_paused_expired_review_stops_consuming_active_capacity(ctx,monkeypatch):
    run=waiting_review(ctx);paused=control(ctx,run,'pause').json()
    # Fill the other slots with legitimate paused-before-checkpoint runs.
    with ctx['db'].begin() as db:
        template=db.get(DurableRun,run['id'])
        for index in range(49):
            clone=DurableRun(org_id=template.org_id,env=template.env,name='Synthetic capacity placeholder',
                author_id=template.author_id,agent_id=template.agent_id,generation=template.generation,
                definition=template.definition,payload_hash=template.payload_hash,request_digest=template.request_digest,
                idem_key='paused-capacity-'+str(index),status='paused',resume_state='queued')
            db.add(clone);db.flush()
            for position,step in enumerate(template.definition['steps']):
                db.add(DurableStep(org_id=clone.org_id,env=clone.env,run_id=clone.id,position=position,label=step['label'],kind=step['kind']))
    h,_=auth(ctx);h['Idempotency-Key']='capacity-new-synthetic-run'
    assert ctx['client'].post('/v1/agent-runs',headers=h,json=request_body(ctx)).status_code==429
    monkeypatch.setattr(durable,'now',lambda:paused['review_until'])
    assert not durable.run_flow_once(ctx['db'],ctx['settings'])
    response=ctx['client'].post('/v1/agent-runs',headers=h,json=request_body(ctx))
    assert response.status_code==201,response.text
    assert detail(ctx,run['id'])['status']=='expired' and ctx['connector'].count()==0
