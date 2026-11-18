"""Database-specific concurrency evidence; explicitly skipped when using SQLite."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from conftest import auth, identifiers, submit
from nexus.db import Agent, Tool, Grant, User, Action, Policy, OIDCTransaction, SchemaVersion, migrate
from nexus.security import issue_session
from nexus.worker import run_once


@pytest.fixture
def pg(ctx):
    if ctx['app'].state.engine.dialect.name != 'postgresql': pytest.skip('PostgreSQL row-lock evidence requires a live PostgreSQL server.')
    return ctx


def test_parallel_workers_have_one_external_effect(pg):
    r=submit(pg,amount='3000.00')
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:run_once(pg['db'],pg['settings'],pg['connector']),range(2)))
    assert pg['connector'].count()==1
    with pg['db']() as db: assert db.get(Action,r.json()['id']).status=='verified'


def test_parallel_policy_changes_have_one_winner(pg):
    with pg['db'].begin() as db:
        owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        token,csrf=issue_session(db,owner,pg['settings'])
    def activate(_):
        with TestClient(pg['app']) as client:
            client.cookies.set('nexus_session',token)
            return client.post('/v1/policies/activate',headers={'X-CSRF-Token':csrf},json={
                'expected_version':1,'threshold':'6000.00','maximum':'30000.00','reason':'Parallel reviewed policy update'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: codes=list(pool.map(activate,range(2)))
    assert sorted(codes)==[200,409]
    with pg['db']() as db:
        rows=db.scalars(select(Policy).where(Policy.org_id=='northstar',Policy.active==1)).all()
        assert len(rows)==1 and rows[0].version==2


def test_parallel_same_key_resolves_same_action(pg):
    a,t=identifiers(pg)
    with pg['db'].begin() as db:
        owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        token,csrf=issue_session(db,owner,pg['settings'])
    body={'agent_id':a,'tool_id':t,'request':{'action':'purchase:create','resource':'purchase_requests',
          'arguments':{'supplier_id':'SUP-DEMO-104','amount':'3000.00','currency':'USD','purpose':'Concurrent identical intent'}}}
    def post(_):
        with TestClient(pg['app']) as client:
            client.cookies.set('nexus_session',token)
            r=client.post('/v1/console/actions',json=body,headers={'X-CSRF-Token':csrf,'Idempotency-Key':'same-business-intent-pg-test'})
            assert r.status_code==202
            return r.json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(post,range(2)))
    assert len(set(ids))==1
    run_once(pg['db'],pg['settings'],pg['connector']);assert pg['connector'].count()==1


def test_revocation_lock_prevents_later_dispatch(pg):
    r=submit(pg,amount='3000.00');a,_=identifiers(pg)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pg['db'].begin() as db:
            agent=db.scalar(select(Agent).where(Agent.id==a).with_for_update())
            agent.status='suspended';agent.generation+=1
            future=pool.submit(run_once,pg['db'],pg['settings'],pg['connector'])
        assert future.result(timeout=15)
    assert pg['connector'].count()==0
    with pg['db']() as db:assert db.get(Action,r.json()['id']).status=='blocked'


def test_cross_tenant_foreign_key_rejected(pg):
    a,t=identifiers(pg)
    with pytest.raises(IntegrityError):
        with pg['db'].begin() as db:
            db.add(Grant(org_id='other',agent_id=a,tool_id=t,scope='purchase:create'))


def test_parallel_schema_upgrade_preserves_data(pg):
    with pg['app'].state.engine.begin() as conn:
        OIDCTransaction.__table__.drop(conn)
        conn.execute(SchemaVersion.__table__.delete().where(SchemaVersion.version>=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:migrate(pg['app'].state.engine,pg['db']),range(2)))
    with pg['db']() as db:
        assert db.get(SchemaVersion,2)
        assert db.scalar(select(User).where(User.email=='owner@nexus.local'))
