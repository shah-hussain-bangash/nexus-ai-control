"""Repeatable connector exercise against fresh synthetic databases, never operator settings."""
import argparse
from datetime import datetime, timezone
import gc
import json
import logging
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select
from . import __version__
from .app import create_app
from .cli import seed
from .config import Settings
from .db import Agent, Tool, Organization, User, Policy, CURRENT_SCHEMA, migrate
from .environments import assign_staging
from .evidence_verifier import verify_report
from .mock_connector import MockBusiness
from .security import password_hash
from .worker import run_once

BOUNDARY = ('Disposable synthetic exercise only. No customer system was contacted. '
            'This is not customer acceptance, authenticated evidence or production readiness.')


class DrillFailure(RuntimeError):
    pass


def run_drill(directory):
    """The directory must not exist. Every database and identity is created under it."""
    root = Path(directory).resolve()
    root.mkdir(exist_ok=False)
    settings = Settings(database_url='sqlite:///' + (root/'control.db').as_posix(),
        mock_database=str(root/'business.db'), secret=secrets.token_urlsafe(48),
        agent_secret=secrets.token_urlsafe(48), frontend_dir=str(root/'no-frontend'),
        mode='local', policy_mode='reference', business_connector='synthetic', live_inference=0)
    result = {'format': 'nexus-synthetic-connector-drill', 'format_version': 1,
        'release': __version__, 'schema_version': CURRENT_SCHEMA,
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'connector_mode': 'synthetic',
        'passed': False, 'customer_acceptance': False, 'production_ready': False,
        'steps': [], 'boundary': BOUNDARY}
    app = None

    def check(name, condition):
        result['steps'].append({'id': name, 'passed': bool(condition)})
        if not condition: raise DrillFailure(name)

    def expect(response, status):
        if response.status_code != status: raise DrillFailure('unexpected_api_response')
        return response.json()

    def login(client, email):
        expect(client.post('/auth/local/login', json={'email': email, 'password': password}), 200)

    def headers(client):
        me = expect(client.get('/v1/me'), 200); context = me['runtime_context']
        return {'X-CSRF-Token': me['csrf'], 'X-Nexus-Environment': me['environment'],
                'X-Nexus-Context-ID': context['binding_id'], 'X-Nexus-Context-Revision': str(context['revision'])}

    logger = logging.getLogger('nexus.http'); previously_disabled = logger.disabled
    logger.disabled = True
    try:
        app = create_app(settings)
        check('synthetic_adapter_only', type(app.state.connector) is MockBusiness)
        lookups = []; original_lookup = app.state.connector.lookup
        def lookup(intent, envelope):
            lookups.append(intent)
            return original_lookup(intent, envelope)
        app.state.connector.lookup = lookup
        migrate(app.state.engine, app.state.factory)
        password = secrets.token_urlsafe(32)
        seed(app.state.factory, password)
        with app.state.factory.begin() as db:
            db.add(Organization(id='drill-other', name='Disposable isolation workspace'))
            other = User(org_id='drill-other', email='other@drill.invalid', name='Synthetic owner',
                         role='owner', password_hash=password_hash(password))
            db.add(other); db.add(Policy(org_id='drill-other', version=1)); db.flush()
            assign_staging(db, other)
            agent = db.scalar(select(Agent).where(Agent.name=='Procurement Atlas'))
            tool = db.scalar(select(Tool).where(Tool.kind=='purchase'))
            agent_id, tool_id = agent.id, tool.id

        with TestClient(app) as client:
            login(client, 'owner@nexus.local')
            config = expect(client.get('/v1/connector-checks/config', headers=headers(client)), 200)
            route = config['choices'][0]
            body = {'agent_id': route['agent_id'], 'tool_id': route['tool_id'],
                'expected_grant_id': route['grant_id'], 'expected_agent_generation': route['agent_generation'],
                'expected_tool_version': route['tool_version'], 'expected_destination': config['connector']['destination'],
                'supplier_id': 'SUP-DEMO-104', 'note': 'Disposable synthetic connector exercise.', 'reviewed': True}
            key = 'synthetic-supplier-drill-001'
            admitted = expect(client.post('/v1/connector-checks', json=body,
                headers={**headers(client), 'Idempotency-Key': key}), 202)['check']
            check('supplier_intake_has_no_effect', app.state.connector.count()==0 and admitted['status']=='queued')
            check('supplier_worker_dispatch', run_once(app.state.factory, settings, app.state.connector))
            replay = expect(client.post('/v1/connector-checks', json=body,
                headers={**headers(client), 'Idempotency-Key': key}), 202)['check']
            recovered = expect(client.post('/v1/connector-checks/recover', json={'key':key}, headers=headers(client)), 200)['check']
            check('supplier_replay_and_recovery', replay['id']==admitted['id']==recovered['id'] and
                  replay['status']=='verified' and app.state.connector.count()==1)
            evidence = expect(client.get('/v1/connector-checks/'+admitted['id']+'/evidence', headers=headers(client)), 200)
            verified = verify_report(evidence)
            check('supplier_evidence_checksum', verified['file_integrity']=='valid' and verified['lookup_verified'] and
                  verified['connector_mode']=='synthetic' and not verified['authenticated_signature'])

            request = {'agent_id': agent_id, 'tool_id': tool_id, 'request': {'action':'purchase:create',
                'resource':'purchase_requests', 'arguments': {'supplier_id':'SUP-DEMO-104', 'amount':'12500.00',
                'currency':'USD', 'purpose':'Disposable synthetic recovery exercise'}, 'simulation':'timeout_after_commit'}}
            purchase_key = 'synthetic-purchase-drill-001'
            purchase = expect(client.post('/v1/console/actions', json=request,
                headers={**headers(client), 'Idempotency-Key':purchase_key}), 202)
            check('purchase_waits_for_approval', purchase['status']=='awaiting_approval' and
                  not run_once(app.state.factory, settings, app.state.connector) and app.state.connector.count()==1)
            approval = next(a for a in expect(client.get('/v1/approvals', headers=headers(client)),200) if a['action_id']==purchase['id'])
            decision = {'decision':'approve', 'expected_version':approval['version'],
                'request_hash':approval['payload_hash'], 'comment':'Independent review of disposable synthetic purchase.'}
            check('self_approval_rejected', client.post('/v1/approvals/'+approval['id']+'/decision',
                json=decision, headers=headers(client)).status_code==403)
            login(client, 'reviewer@nexus.local')
            check('changed_approval_payload_rejected', client.post('/v1/approvals/'+approval['id']+'/decision',
                json={**decision, 'request_hash':'0'*64}, headers=headers(client)).status_code==409)
            expect(client.post('/v1/approvals/'+approval['id']+'/decision', json=decision, headers=headers(client)),200)
            check('independent_approval_dispatch', run_once(app.state.factory, settings, app.state.connector))
            login(client, 'owner@nexus.local')
            unknown = expect(client.get('/v1/actions/'+purchase['id'], headers=headers(client)),200)
            check('timeout_after_commit_stays_unknown', unknown['status']=='outcome_unknown' and app.state.connector.count()==2)
            duplicate = expect(client.post('/v1/console/actions',json=request,
                headers={**headers(client),'Idempotency-Key':purchase_key}),202)
            check('uncertain_replay_does_not_dispatch_again', duplicate['id']==purchase['id'] and
                not run_once(app.state.factory, settings, app.state.connector) and app.state.connector.count()==2)
            changed = {**request, 'request':{**request['request'], 'arguments':{**request['request']['arguments'],'amount':'12501.00'}}}
            check('changed_body_under_same_key_rejected', client.post('/v1/console/actions',json=changed,
                headers={**headers(client),'Idempotency-Key':purchase_key}).status_code==409 and app.state.connector.count()==2)
            login(client, 'other@drill.invalid')
            check('workspace_read_isolation', client.get('/v1/actions/'+purchase['id'],headers=headers(client)).status_code==404 and
                client.get('/v1/connector-checks/'+admitted['id']+'/evidence',headers=headers(client)).status_code==404)
            check('workspace_recovery_isolation', client.post('/v1/actions/'+purchase['id']+'/reconcile',
                headers=headers(client)).status_code==404 and app.state.connector.count()==2 and not lookups)
            login(client, 'owner@nexus.local')
            reconciled = expect(client.post('/v1/actions/'+purchase['id']+'/reconcile',headers=headers(client)),200)
            check('authoritative_reconciliation_without_retry', reconciled['status']=='verified' and
                reconciled['verification'].get('reconciled') is True and app.state.connector.count()==2 and lookups==[purchase['id']])
            result['synthetic_effect_count'] = app.state.connector.count()
            result['passed'] = True
    except DrillFailure as exc:
        result['failure'] = str(exc)
    except Exception:
        result['failure'] = 'isolated_drill_could_not_finish'
    finally:
        if app is not None: app.state.engine.dispose()
        gc.collect()  # Close unreferenced synthetic SQLite connections before Windows cleanup.
        logger.disabled = previously_disabled
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run disposable synthetic connector drills; never loads operator settings.')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1]/'data/drills')
    args = parser.parse_args(argv)
    try:
        destination = args.output_dir.resolve(); destination.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.synthetic-', dir=destination) as scratch:
            if Path(scratch).resolve().parent != destination: raise ValueError('Invalid temporary directory')
            result = run_drill(Path(scratch)/'workspace')
        report = destination/('synthetic-connector-'+uuid.uuid4().hex+'.json')
        with report.open('x', encoding='utf-8') as target: json.dump(result, target, indent=2)
        print(json.dumps({'passed':result['passed'], 'steps_passed':sum(step['passed'] for step in result['steps']),
            'report':str(report), 'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError, ValueError):
        print(json.dumps({'passed':False, 'failure':'Could not create or clean up the disposable drill report.', 'boundary':BOUNDARY}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
