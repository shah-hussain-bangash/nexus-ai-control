import pytest
import os
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient
from sqlalchemy import select
from nexus.app import create_app
from nexus.config import Settings
from nexus.db import migrate, Agent, Tool, User, Organization, Policy, uid
from nexus.cli import seed
from nexus.security import issue_session, password_hash


@pytest.fixture
def ctx(tmp_path):
    base_url = os.environ.get('NEXUS_TEST_DATABASE_URL')
    admin_engine = None; test_schema = None
    database_url = 'sqlite:///' + str(tmp_path / 'control.db')
    if base_url:
        if os.environ.get('NEXUS_TEST_ALLOW_SCHEMA_CREATE') != '1':
            raise RuntimeError('PostgreSQL test runs require explicit schema-creation opt-in on a disposable database.')
        if make_url(base_url).get_backend_name() != 'postgresql':
            raise RuntimeError('NEXUS_TEST_DATABASE_URL must select PostgreSQL.')
        test_schema = 'nexus_test_' + uuid.uuid4().hex
        admin_engine = create_engine(base_url, isolation_level='AUTOCOMMIT')
        with admin_engine.connect() as conn: conn.execute(text('CREATE SCHEMA ' + test_schema))
        database_url = make_url(base_url).update_query_dict({'options': '-csearch_path=' + test_schema}).render_as_string(hide_password=False)
    settings = Settings(database_url=database_url, mock_database=str(tmp_path / 'business.db'),
                        secret='test-session-secret-' + 'x' * 48, agent_secret='test-agent-secret-' + 'y' * 48,
                        frontend_dir=str(tmp_path / 'no-frontend'))
    app = create_app(settings); factory = app.state.factory
    migrate(app.state.engine, factory); seed(factory, 'Test-Only-Password-123!')
    with factory.begin() as db:
        db.add(Organization(id='other', name='Other tenant'))
        db.add(User(id='other-user', org_id='other', email='other@test.invalid', name='Other Owner', role='owner', password_hash=password_hash('test')))
        db.add(Policy(org_id='other', version=1))
    with TestClient(app) as client:
        yield {'app': app, 'db': factory, 'client': client, 'settings': settings, 'connector': app.state.connector}
    app.state.engine.dispose()
    if admin_engine:
        with admin_engine.connect() as conn: conn.execute(text('DROP SCHEMA ' + test_schema + ' CASCADE'))
        admin_engine.dispose()


def auth(ctx, role='owner', org='northstar'):
    with ctx['db'].begin() as db:
        user = db.scalar(select(User).where(User.org_id == org, User.role == role))
        token, csrf = issue_session(db, user, ctx['settings'])
    ctx['client'].cookies.set('nexus_session', token)
    return {'X-CSRF-Token': csrf}, user.id


def identifiers(ctx, name='Procurement Atlas', kind='purchase'):
    with ctx['db']() as db:
        a = db.scalar(select(Agent).where(Agent.name == name))
        t = db.scalar(select(Tool).where(Tool.kind == kind))
        return a.id, t.id


def submit(ctx, amount='12500.00', name='Procurement Atlas', kind='purchase', simulation='normal', key='test-request-0001'):
    headers, _ = auth(ctx); headers['Idempotency-Key'] = key
    a, t = identifiers(ctx, name, kind)
    args = {'supplier_id': 'SUP-DEMO-104'}
    if kind == 'purchase': args.update(amount=amount, currency='USD', purpose='Synthetic test request')
    body = {'agent_id': a, 'tool_id': t, 'request': {'action': 'purchase:create' if kind == 'purchase' else 'supplier:read',
            'resource': 'purchase_requests' if kind == 'purchase' else 'suppliers', 'arguments': args, 'simulation': simulation}}
    return ctx['client'].post('/v1/console/actions', json=body, headers=headers)


def approve(ctx, override=None, role='approver'):
    headers, _ = auth(ctx, role)
    rows = ctx['client'].get('/v1/approvals').json(); row = rows[0]
    body = {'decision': 'approve', 'expected_version': row['version'], 'request_hash': row['payload_hash'], 'comment': 'Reviewed independent synthetic purchase'}
    body.update(override or {})
    return ctx['client'].post('/v1/approvals/' + row['id'] + '/decision', json=body, headers=headers)
