import pytest
from sqlalchemy import event,select,update,func
from test_durable import create
from nexus import durable
from nexus.db import DurableRun,Action,now
from nexus.worker import run_once


def tick(ctx):
    with ctx['db'].begin() as db:db.execute(update(DurableRun).values(next_poll=0))
    return durable.run_flow_once(ctx['db'],ctx['settings'])


def detail(ctx,run):return ctx['client'].get('/v1/agent-runs/'+run['id']).json()


@pytest.fixture
def claim_clock(ctx,monkeypatch):
    clock=[now()];monkeypatch.setattr(durable,'now',lambda:clock[0]);listeners=[]
    def install(id,offset):
        fired=[]
        def after_claim(session):
            if fired:return
            claimed=next((row for row in session.identity_map.values() if isinstance(row,DurableRun) and row.id==id and row.status=='processing'),None)
            if claimed is not None:
                fired.append(True);clock[0]=claimed.lease_until+offset
        event.listen(ctx['db'].class_,'after_commit',after_claim)
        listeners.append(after_claim)
        return fired
    yield clock,install
    for listener in listeners:event.remove(ctx['db'].class_,'after_commit',listener)


@pytest.mark.parametrize('kind',['checkpoint','governed_action'])
@pytest.mark.parametrize('offset',[0,1])
def test_late_claim_cannot_advance_cursor_or_submit_a_business_intent(ctx,claim_clock,kind,offset):
    run=create(ctx,review=False,purchase=False)
    if kind=='governed_action':assert tick(ctx)
    current=detail(ctx,run);assert current['steps'][current['cursor']]['kind']==kind
    clock,install=claim_clock;fired=install(run['id'],offset)
    assert tick(ctx);assert fired
    result=detail(ctx,run)
    assert result['status']=='queued' and result['cursor']==current['cursor']
    assert result['recoveries']==1 and result['error']=='WORKER_LEASE_EXPIRED'
    assert result['version']==current['version']+1
    with ctx['db']() as db:
        saved=db.get(DurableRun,run['id']);assert not saved.lease_token and saved.lease_until==0
        assert db.scalar(select(func.count()).select_from(Action))==0
    assert ctx['connector'].count()==0


def test_claim_just_before_deadline_can_complete_a_checkpoint(ctx,claim_clock):
    run=create(ctx,review=False,purchase=False);clock,install=claim_clock;fired=install(run['id'],-.01)
    assert tick(ctx) and fired
    result=detail(ctx,run)
    assert result['status']=='queued' and result['cursor']==1 and result['recoveries']==0 and not result['error']


def test_late_claim_obeys_existing_automatic_recovery_budget(ctx,claim_clock):
    run=create(ctx,review=False,purchase=False)
    with ctx['db'].begin() as db:db.get(DurableRun,run['id']).recoveries=3
    clock,install=claim_clock;install(run['id'],0)
    assert tick(ctx)
    result=detail(ctx,run)
    assert result['status']=='failed' and result['recoveries']==4 and result['cursor']==0
    assert result['error']=='WORKER_LEASE_EXPIRED' and ctx['connector'].count()==0


def test_recovered_claim_keeps_existing_action_and_never_resubmits_it(ctx,claim_clock):
    run=create(ctx,review=False,purchase=False);assert tick(ctx);assert tick(ctx)
    waiting=detail(ctx,run);assert waiting['status']=='waiting_action'
    action_id=waiting['steps'][waiting['cursor']]['action_id'];assert action_id
    clock,install=claim_clock;install(run['id'],0)
    assert tick(ctx)
    recovered=detail(ctx,run)
    assert recovered['status']=='queued' and recovered['cursor']==waiting['cursor'] and recovered['recoveries']==1
    assert recovered['steps'][recovered['cursor']]['action_id']==action_id
    assert tick(ctx);assert detail(ctx,run)['status']=='waiting_action'
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    assert tick(ctx);assert tick(ctx)
    assert detail(ctx,run)['status']=='succeeded' and ctx['connector'].count()==1
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==1


def test_idle_recovery_also_treats_exact_lease_equality_as_expired(ctx,claim_clock):
    run=create(ctx,review=False,purchase=False);clock,_=claim_clock
    with ctx['db'].begin() as db:
        row=db.get(DurableRun,run['id']);row.status='processing';row.lease_token='lost-worker';row.lease_until=clock[0]
    assert not durable.run_flow_once(ctx['db'],ctx['settings'])
    result=detail(ctx,run)
    assert result['status']=='queued' and result['recoveries']==1 and result['cursor']==0
