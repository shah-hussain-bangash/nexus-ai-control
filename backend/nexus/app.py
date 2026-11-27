import csv
import io
import json
import secrets
import time
import hashlib
import base64
from decimal import Decimal
from pathlib import Path
from collections import Counter
from contextlib import asynccontextmanager
from urllib.parse import urlencode
import httpx
import jwt
from fastapi import FastAPI, Request, Response, Header, Query
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from .config import Settings
from . import __version__
from .db import (database, User, SessionRecord, Agent, Tool, Grant, Policy, Action, Approval, Audit,
                 Export, Evaluation, Incident, SchemaVersion, now, public, uid, CURRENT_SCHEMA)
from .schemas import SupplierArguments, PurchaseArguments, Login, AgentInput, Reason, GrantInput, ConsoleAction, ActionInput, ApprovalDecision, PolicyInput
from .security import (session_user, issue_session, password_valid, digest, fail, permit,
                       workload_token, authenticate_agent, PERMISSIONS, get_session_context, public_session_context)
from .service import scoped, submit_action, active_policy, decide, audit, verify
from .policy import evaluate
from .runtime_context import CURRENT_ENVIRONMENT, runtime_environment, switching_enabled
from .mock_connector import UncertainOutcome
from .business_connector import business_connector, connector_identity, connector_profile


def create_app(settings=None):
    settings = settings or Settings.from_env(); settings.validate()
    if settings.database_url.startswith('sqlite:///'):
        Path(settings.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
    engine, factory = database(settings.database_url)
    @asynccontextmanager
    async def lifespan(application):
        try:
            with factory() as db:
                version = db.scalar(select(func.max(SchemaVersion.version)))
                if version != CURRENT_SCHEMA: raise RuntimeError(f'Run python -m nexus.cli migrate before starting release {__version__}.')
        except __import__('sqlalchemy').exc.SQLAlchemyError as exc:
            raise RuntimeError('Initialize or upgrade the database before starting NEXUS.') from exc
        yield

    app = FastAPI(title='NEXUS AI Control', version=__version__, docs_url='/api/docs', lifespan=lifespan)
    app.state.settings = settings; app.state.factory = factory; app.state.engine = engine
    app.state.connector = business_connector(settings)
    from .http_controls import RequestControls
    app.add_middleware(RequestControls)
    login_attempts = {}

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        if response.status_code<400 and not response_context_valid(request,factory,settings):
            replacement=JSONResponse({'error':{'code':'STALE_SESSION_CONTEXT','message':'Your workspace access or context changed. Refresh before continuing.'}},409)
            if response.headers.get('X-Request-ID'):replacement.headers['X-Request-ID']=response.headers['X-Request-ID']
            response=replacement
        if settings.mode != 'local': response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        if request.url.path.startswith(('/v1', '/auth')): response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(IntegrityError)
    async def conflicts(request, exc):
        return JSONResponse({'error': {'code': 'CONFLICT', 'message': 'A concurrent change or duplicate record conflicts with this request.'}}, 409)

    from fastapi import HTTPException
    @app.exception_handler(HTTPException)
    async def errors(request, exc):
        return JSONResponse({'error': exc.detail if isinstance(exc.detail, dict) else {'code': 'REQUEST_FAILED', 'message': str(exc.detail)}}, exc.status_code)

    def human(request, db, write=False, permission=None,serialize=True):
        u = session_user(request, db, write,serialize=serialize)
        if permission: permit(u, permission)
        return u

    def session_cookie(response, token):
        response.set_cookie('nexus_session', token, httponly=True, secure=settings.mode != 'local',
                            samesite='lax', max_age=settings.session_seconds, path='/')

    @app.get('/health/live')
    def live(): return {'status': 'ok', 'version': __version__}

    @app.get('/health/ready')
    def ready():
        try:
            with factory() as db:
                version = db.scalar(select(func.max(SchemaVersion.version)))
                if version != CURRENT_SCHEMA: fail(503, 'SCHEMA_UPGRADE_REQUIRED', 'Run the schema upgrade before serving this release.')
        except __import__('sqlalchemy').exc.SQLAlchemyError:
            fail(503, 'DATABASE_UNAVAILABLE', 'The database is unavailable or requires initialization.')
        if settings.policy_mode == 'opa':
            try:
                r = httpx.get(settings.opa_url.split('/v1/')[0] + '/health', timeout=2); r.raise_for_status()
            except httpx.HTTPError: fail(503, 'CONTROL_UNAVAILABLE', 'Policy service unavailable.')
        return {'status': 'ready', 'mode': settings.mode, 'policy_engine': settings.policy_mode, 'schema_version': CURRENT_SCHEMA}

    @app.get('/auth/config')
    def auth_config():
        return {'local_login': settings.mode == 'local', 'oidc': bool(settings.oidc_issuer), 'mode': settings.mode}

    @app.post('/auth/local/login')
    def login(body: Login, request: Request, response: Response):
        if settings.mode != 'local': fail(404, 'NOT_FOUND', 'Local sign-in is disabled.')
        origin = request.headers.get('origin')
        if origin and origin not in (settings.origin, 'http://localhost:5173', 'http://127.0.0.1:5173'):
            fail(403, 'INVALID_ORIGIN', 'Sign-in origin not allowed.')
        # Local-only bounded in-process limiter. Distributed rate limiting remains pilot work.
        key = (request.client.host if request.client else 'unknown', body.email.lower())
        cutoff = now() - 300
        for old in list(login_attempts):
            login_attempts[old] = [v for v in login_attempts[old] if v > cutoff]
            if not login_attempts[old]: del login_attempts[old]
        if len(login_attempts) >= 4096: fail(429, 'RATE_LIMITED', 'Try again later.')
        if len(login_attempts.get(key, [])) >= 8: fail(429, 'RATE_LIMITED', 'Too many attempts. Try again in five minutes.')
        login_attempts.setdefault(key, []).append(now())
        with factory.begin() as db:
            user = db.scalar(select(User).where(User.email == body.email.lower(), User.active == 1))
            # Equal password work for an unknown user reduces account-enumeration timing.
            stored = user.password_hash if user else '0' * 32 + ':' + '0' * 64
            if not password_valid(body.password, stored) or not user: fail(401, 'INVALID_CREDENTIALS', 'Email or password is incorrect.')
            token, csrf = issue_session(db, user, settings)
            audit(db, user.org_id, user.id, 'session.created',env=CURRENT_ENVIRONMENT)
        session_cookie(response, token)
        return {'user': public(user), 'csrf': csrf}

    @app.post('/auth/logout')
    def logout(request: Request, response: Response):
        with factory.begin() as db:
            user = human(request, db, True)
            row = db.get(SessionRecord, digest(request.cookies['nexus_session'])); db.delete(row)
            audit(db, user.org_id, user.id, 'session.ended')
        request.state.context_logout=True
        response.delete_cookie('nexus_session', path='/'); return {'status': 'signed_out'}

    @app.get('/v1/me')
    def me(request: Request):
        with factory() as db:
            user = human(request, db)
            session = db.get(SessionRecord, digest(request.cookies['nexus_session']))
            return {'user': public(user), 'csrf': session.csrf, 'permissions': sorted(PERMISSIONS[user.role]),
                    'workspace': 'Northstar Operations' if user.org_id == 'northstar' else user.org_id,
                    'environment': runtime_environment(db,user.org_id), 'runtime_context':public_session_context(get_session_context(db,session,user,allow_non_staging=switching_enabled(settings)),switching_enabled(settings)), 'synthetic': settings.business_connector=='synthetic', 'mode': settings.mode, 'business_connector': connector_profile(settings)}

    @app.get('/v1/overview')
    def overview(request: Request):
        with factory() as db:
            u = human(request, db)
            agents = db.scalars(select(Agent).where(Agent.org_id == u.org_id)).all()
            actions = db.scalars(select(Action).where(Action.org_id == u.org_id)).all()
            approvals = db.scalars(select(Approval).where(Approval.org_id == u.org_id)).all()
            counts = Counter(a.status for a in actions)
            daily = []
            for day in range(6, -1, -1):
                start = int(now() // 86400 - day) * 86400
                subset = [a for a in actions if start <= a.created < start + 86400]
                daily.append({'day': time.strftime('%a', time.gmtime(start)), 'allowed': sum(a.decision == 'allow' for a in subset),
                              'denied': sum(a.decision == 'deny' for a in subset), 'approval': sum(a.decision == 'require_approval' for a in subset)})
            pending = sum(a.status == 'pending' and a.expires > now() for a in approvals)
            return {'agents': len(agents), 'active_agents': sum(a.status == 'active' for a in agents),
                    'actions': len(actions), 'denied': counts['denied'], 'pending': pending,
                    'verified': counts['verified'], 'unknown': counts['outcome_unknown'],
                    'verification_rate': round(100 * counts['verified'] / max(1, sum(a.attempts > 0 for a in actions)), 1),
                    'trend': daily, 'updated': now(), 'policy_engine': settings.policy_mode,
                    'recent': [public(a) for a in sorted(actions, key=lambda a: a.created, reverse=True)[:6]],
                    'cost': None, 'cost_note': 'Provider usage is not connected. No billed cost is claimed.'}

    @app.get('/v1/agents')
    def agents(request: Request):
        with factory() as db:
            u = human(request, db)
            return [public(a) for a in db.scalars(select(Agent).where(Agent.org_id == u.org_id).order_by(Agent.created))]

    @app.post('/v1/agents', status_code=201)
    def create_agent(body: AgentInput, request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'manage')
            a = Agent(org_id=u.org_id, owner_id=u.id, **body.model_dump()); db.add(a); db.flush()
            audit(db, u.org_id, u.id, 'agent.registered', detail={'agent_id': a.id}); return public(a)

    @app.get('/v1/agents/{id}')
    def agent_detail(id: str, request: Request):
        with factory() as db:
            u = human(request, db); a = scoped(db, Agent, id, u.org_id)
            return {**public(a), 'grants': [public(g) for g in db.scalars(select(Grant).where(Grant.agent_id == id, Grant.org_id == u.org_id))]}

    @app.post('/v1/agents/{id}/lifecycle/{operation}')
    def lifecycle(id: str, operation: str, body: Reason, request: Request):
        if operation not in ('activate', 'suspend', 'rotate'): fail(404, 'NOT_FOUND', 'Operation not found.')
        with factory.begin() as db:
            u = human(request, db, True, 'contain' if operation == 'suspend' else 'manage')
            a = scoped(db, Agent, id, u.org_id)
            if operation == 'activate':
                grants = db.scalar(select(Grant).where(Grant.agent_id == id, Grant.org_id == u.org_id))
                if not grants: fail(409, 'GRANT_REQUIRED', 'Add a tool grant before activation.')
                a.status = 'active'
            if operation == 'suspend': a.status = 'suspended'
            a.generation += 1
            raw = None
            if operation == 'rotate':
                raw = secrets.token_urlsafe(40); a.credential_hash = digest(raw)
            audit(db, u.org_id, u.id, 'agent.' + operation, detail={'agent_id': id, 'reason': body.reason})
            return {**public(a), **({'credential': raw, 'warning': 'Shown once. Store securely outside prompts.'} if raw else {})}

    @app.post('/v1/agents/{id}/tool-grants', status_code=201)
    def grant(id: str, body: GrantInput, request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'manage'); a = scoped(db, Agent, id, u.org_id); t = scoped(db, Tool, body.tool_id, u.org_id)
            expected = 'supplier:read' if t.kind == 'supplier' else 'purchase:create'
            if body.scope != expected: fail(422, 'INVALID_SCOPE', 'Scope does not match tool schema.')
            g = Grant(org_id=u.org_id, agent_id=a.id, tool_id=t.id, scope=body.scope); db.add(g); db.flush()
            audit(db, u.org_id, u.id, 'grant.created', detail={'agent_id': id, 'tool_id': t.id}); return public(g)

    @app.delete('/v1/agents/{id}/tool-grants/{grant_id}')
    def revoke(id: str, grant_id: str, request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'manage'); a = scoped(db, Agent, id, u.org_id); g = scoped(db, Grant, grant_id, u.org_id)
            if g.agent_id != a.id: fail(404, 'NOT_FOUND', 'Grant not found.')
            db.delete(g); a.generation += 1
            audit(db, u.org_id, u.id, 'grant.revoked', detail={'grant_id': grant_id}); return {'status': 'revoked'}

    @app.post('/v1/workload/token/{id}')
    def agent_token(id: str, authorization: str = Header(default='')):
        with factory() as db:
            a = db.get(Agent, id)
            key = authorization.removeprefix('Bearer ')
            if not a or not a.credential_hash or not secrets.compare_digest(digest(key), a.credential_hash) or a.status != 'active':
                fail(401, 'INVALID_CREDENTIAL', 'Workload credential invalid.')
            return {'access_token': workload_token(a, settings), 'token_type': 'Bearer', 'expires_in': 300}

    @app.get('/v1/tools')
    def tools(request: Request):
        with factory() as db:
            u = human(request, db)
            return [{**public(t),'schema_json':(SupplierArguments if t.kind=='supplier' else PurchaseArguments).model_json_schema(),'schema_origin':'current fixed server contract'} for t in db.scalars(select(Tool).where(Tool.org_id == u.org_id))]

    @app.post('/v1/console/actions', status_code=202)
    def console_action(body: ConsoleAction, request: Request, idempotency_key: str = Header()):
        if settings.mode != 'local': fail(404, 'NOT_FOUND', 'Synthetic console runner is local-only; use workload gateway.')
        with factory.begin() as db:
            u = human(request, db, True, 'operate'); a = scoped(db, Agent, body.agent_id, u.org_id); t = scoped(db, Tool, body.tool_id, u.org_id)
            action = submit_action(db, settings, a, t, body.request, idempotency_key, 'human:' + u.id, u.id)
            return public(action)

    @app.post('/v1/gateway/tools/{id}:execute', status_code=202)
    def gateway(id: str, body: ActionInput, request: Request, authorization: str = Header(default=''), idempotency_key: str = Header()):
        with factory.begin() as db:
            a = authenticate_agent(authorization.removeprefix('Bearer '), db, settings, request,write=True)
            t = scoped(db, Tool, id, a.org_id)
            action = submit_action(db, settings, a, t, body, idempotency_key, 'agent:' + a.id, a.owner_id)
            result = public(action)
        if result['status'] == 'denied':
            return JSONResponse({'error': {'code': result['reason'], 'message': 'Action denied by policy or grant.', 'action_id': result['id']}}, 403)
        return result

    @app.get('/v1/gateway/actions/{id}')
    def workload_action_status(id: str, request: Request, authorization: str = Header(default='')):
        with factory() as db:
            agent = authenticate_agent(authorization.removeprefix('Bearer '), db, settings, request)
            action = scoped(db, Action, id, agent.org_id)
            if action.agent_id != agent.id: fail(404, 'NOT_FOUND', 'Action not found for this workload.')
            return {'id': action.id, 'status': action.status, 'reason': action.reason,
                    'external_ref': action.external_ref, 'trace_id': action.trace_id, 'updated': action.updated}

    @app.get('/v1/actions')
    def actions(request: Request, limit: int = 100):
        with factory() as db:
            u = human(request, db)
            return [public(a) for a in db.scalars(select(Action).where(Action.org_id == u.org_id).order_by(Action.created.desc()).limit(min(max(limit, 1), 500)))]

    @app.get('/v1/actions/{id}')
    def action(id: str, request: Request):
        with factory() as db:
            u = human(request, db); a = scoped(db, Action, id, u.org_id)
            return {**public(a), 'events': [public(e) for e in db.scalars(select(Audit).where(Audit.org_id == u.org_id, Audit.action_id == id).order_by(Audit.created))]}

    @app.get('/v1/approvals')
    def approvals(request: Request):
        with factory.begin() as db:
            u = human(request, db)
            rows = db.scalars(select(Approval).where(Approval.org_id == u.org_id).order_by(Approval.created.desc())).all()
            result = []
            for a in rows:
                if a.status == 'pending' and a.expires <= now():
                    a.status = 'expired'; a.version += 1
                    action = scoped(db, Action, a.action_id, u.org_id); action.status = 'expired'
                    audit(db, u.org_id, 'system', 'approval.expired', action)
                result.append({**public(a), 'action': public(scoped(db, Action, a.action_id, u.org_id)), 'self_review': a.requester_id == u.id})
            return result

    @app.post('/v1/approvals/{id}/decision')
    def approval_decision(id: str, body: ApprovalDecision, request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'approve'); a = scoped(db, Approval, id, u.org_id)
            return public(decide(db, u, a, body))

    @app.post('/v1/actions/{id}/reconcile')
    def reconcile(id: str, request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'operate'); a = scoped(db, Action, id, u.org_id)
            if a.status != 'outcome_unknown': fail(409, 'NOT_UNKNOWN', 'Only unknown outcomes can be reconciled.')
            if a.envelope.get('destination')!=connector_identity(settings):fail(409,'DESTINATION_CHANGED','Restore the reviewed adapter binding before reconciling this operation.')
            try:result = app.state.connector.lookup(a.id,a.envelope)
            except UncertainOutcome:fail(503,'RECONCILIATION_UNAVAILABLE','Authoritative business lookup is unavailable. The outcome remains unknown.')
            except ValueError:fail(409,'DESTINATION_CHANGED','The reviewed connector configuration is unavailable.')
            if result and verify(a.envelope, result):
                a.status = 'verified'; a.external_ref = result['external_ref']; a.verification = {'matched': True, 'result': result, 'reconciled': True}
            else: a.verification = {'matched': False, 'note': 'No matching authoritative result. Manual investigation required.'}
            a.updated = now(); audit(db, u.org_id, u.id, 'execution.reconciled', a, {'status': a.status})
            return public(a)

    @app.get('/v1/policies')
    def policies(request: Request):
        with factory() as db:
            u = human(request, db)
            return [public(p) for p in db.scalars(select(Policy).where(Policy.org_id == u.org_id).order_by(Policy.version.desc()))]

    @app.post('/v1/policies/activate')
    def activate_policy(body: PolicyInput, request: Request):
        if Decimal(body.threshold) < 0 or Decimal(body.maximum) <= Decimal(body.threshold):
            fail(422, 'INVALID_LIMITS', 'Maximum must exceed the nonnegative approval threshold.')
        with factory.begin() as db:
            u = human(request, db, True, 'policy')
            current = db.scalar(select(Policy).where(Policy.org_id == u.org_id, Policy.env == runtime_environment(db,u.org_id),
                                Policy.version == body.expected_version).with_for_update())
            if not current or not current.active:
                fail(409, 'STALE_VERSION', 'Policy changed. Refresh and review.')
            candidate = Policy(org_id=u.org_id, version=current.version + 1, threshold=body.threshold, maximum=body.maximum)
            checks = [('supplier:read', '0', 'allow'), ('purchase:create', body.threshold, 'allow'),
                      ('purchase:create', str(Decimal(body.threshold) + Decimal('.01')), 'require_approval'),
                      ('purchase:create', str(Decimal(body.maximum) + Decimal('.01')), 'deny')]
            for scope, amount, expected in checks:
                if evaluate(settings, scope, {'amount': amount}, candidate)['decision'] != expected:
                    fail(409, 'POLICY_TEST_FAILED', 'Boundary tests failed. The current policy remains active.')
            changed = db.execute(update(Policy).where(Policy.id == current.id, Policy.active == 1, Policy.version == body.expected_version).values(active=0))
            if changed.rowcount != 1: fail(409, 'STALE_VERSION', 'Policy changed. Refresh and review.')
            p = Policy(org_id=u.org_id, version=current.version + 1, threshold=body.threshold, maximum=body.maximum)
            db.add(p); db.flush(); audit(db, u.org_id, u.id, 'policy.activated', detail={'version': p.version, 'reason': body.reason})
            return public(p)

    @app.get('/v1/audit-events')
    def events(request: Request, q: str = '', limit: int = 200):
        with factory() as db:
            u = human(request, db)
            rows = db.scalars(select(Audit).where(Audit.org_id == u.org_id).order_by(Audit.created.desc()).limit(min(max(limit, 1), 500))).all()
            return [public(e) for e in rows if q.lower() in json.dumps(public(e)).lower()]

    @app.get('/v1/audit-page')
    def paged_events(request: Request, q: str = Query('', max_length=120),
                     limit: int = Query(50, ge=1, le=200), cursor: str = Query('', max_length=2048)):
        from .operations import audit_page
        with factory() as db:
            u = human(request, db)
            return audit_page(db, settings, u.org_id, q, limit, cursor)

    @app.post('/v1/audit-exports', status_code=201)
    def export(request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'export')
            rows = [public(e) for e in db.scalars(select(Audit).where(Audit.org_id == u.org_id).order_by(Audit.created).limit(10000))]
            job = Export(org_id=u.org_id, owner_id=u.id, expires=now() + 604800, records=rows); db.add(job); db.flush()
            audit(db, u.org_id, u.id, 'audit.export_created', detail={'export_id': job.id, 'count': len(rows)})
            return {'id': job.id, 'status': 'ready', 'records': len(rows), 'expires': job.expires, 'url': '/v1/audit-exports/' + job.id + '/download'}

    @app.get('/v1/audit-exports/{id}/download')
    def download(id: str, request: Request):
        with factory.begin() as db:
            u = human(request, db, permission='export'); job = scoped(db, Export, id, u.org_id)
            if job.owner_id != u.id or job.expires < now(): fail(404, 'NOT_FOUND', 'Export unavailable or expired.')
            if not isinstance(job.records,list) or any(not isinstance(row,dict) or row.get('org_id')!=job.org_id or row.get('env')!=job.env for row in job.records):
                fail(409,'EXPORT_SCOPE_CHANGED','This saved export contains records outside the current context. Create a new export.')
            audit(db, u.org_id, u.id, 'audit.export_downloaded', detail={'export_id': id})
            return Response(json.dumps({'synthetic': True, 'records': job.records}, indent=2), media_type='application/json',
                            headers={'Content-Disposition': 'attachment; filename="nexus-audit.json"'})

    @app.get('/v1/evaluations')
    def evaluations(request: Request):
        with factory() as db:
            u = human(request, db)
            return [public(e) for e in db.scalars(select(Evaluation).where(Evaluation.org_id == u.org_id).order_by(Evaluation.created.desc()))]

    @app.post('/v1/evaluations', status_code=201)
    def run_evaluation(request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'operate'); p = active_policy(db, u.org_id)
            cases = [('scoped-read', 'supplier:read', '0', 'allow'),
                     ('at-threshold', 'purchase:create', p.threshold, 'allow'),
                     ('above-threshold', 'purchase:create', str(Decimal(p.threshold) + Decimal('.01')), 'require_approval'),
                     ('at-maximum', 'purchase:create', p.maximum, 'require_approval'),
                     ('above-maximum', 'purchase:create', str(Decimal(p.maximum) + Decimal('.01')), 'deny')]
            results = []
            for name, action, amount, expected in cases:
                actual = evaluate(settings, action, {'amount': amount}, p)['decision']
                results.append({'name': name, 'expected': expected, 'actual': actual, 'passed': actual == expected})
            run = Evaluation(org_id=u.org_id, suite='policy-boundaries-v1', cases=results, passed=sum(r['passed'] for r in results), total=len(results))
            db.add(run); db.flush(); audit(db, u.org_id, u.id, 'evaluation.completed', detail={'run_id': run.id, 'policy_version': p.version})
            return public(run)

    @app.get('/v1/incidents')
    def incidents(request: Request):
        with factory() as db:
            u = human(request, db)
            return [public(i) for i in db.scalars(select(Incident).where(Incident.org_id == u.org_id).order_by(Incident.created.desc()))]

    @app.post('/v1/agents/{id}/contain', status_code=201)
    def contain(id: str, body: Reason, request: Request):
        with factory.begin() as db:
            u = human(request, db, True, 'contain'); a = scoped(db, Agent, id, u.org_id)
            a.status = 'suspended'; a.generation += 1; a.credential_hash = ''
            grants = db.scalars(select(Grant).where(Grant.agent_id == a.id, Grant.org_id == u.org_id)).all()
            for g in grants: db.delete(g)
            incident = Incident(org_id=u.org_id, agent_id=a.id, title='Agent containment: ' + a.name, reason=body.reason)
            db.add(incident); db.flush(); audit(db, u.org_id, u.id, 'incident.contained', detail={'agent_id': id, 'incident_id': incident.id, 'reason': body.reason})
            return public(incident)

    @app.post('/v1/members/{id}/revoke')
    def revoke_member(id: str, body: Reason, request: Request):
        from sqlalchemy import delete
        with factory.begin() as db:
            u = human(request, db, True, 'members')
            member = db.scalar(select(User).where(User.id == id, User.org_id == u.org_id).with_for_update())
            if not member: fail(404, 'NOT_FOUND', 'Member not found.')
            if member.id == u.id: fail(409, 'SELF_REVOCATION', 'Ask another owner to change your access.')
            if member.role == 'owner': fail(409, 'OWNER_PROTECTED', 'Owner access requires a reviewed ownership transfer.')
            member.active = 0
            db.execute(delete(SessionRecord).where(SessionRecord.user_id == id))
            audit(db, u.org_id, u.id, 'member.revoked', detail={'member_id': id, 'reason': body.reason})
            return {'id': id, 'active': False, 'sessions_revoked': True}

    @app.get('/v1/operations')
    def operations(request: Request):
        with factory() as db:
            u = human(request, db)
            expired = db.scalar(select(func.count()).select_from(Export).where(Export.org_id == u.org_id, Export.expires <= now()))
            sessions = db.scalar(select(func.count()).select_from(SessionRecord).join(User, User.id == SessionRecord.user_id)
                .where(User.org_id == u.org_id, SessionRecord.expires <= now()))
            return {'expired_exports': expired, 'expired_sessions': sessions,
                'maintenance': 'python -m nexus.cli maintenance',
                'audit_retention': 'Preserved; no automatic audit deletion',
                'checks': [
                    {'name': 'Policy enforcement', 'state': 'configured' if settings.policy_mode == 'opa' else 'local', 'detail': settings.policy_mode.upper() + ' policy engine'},
                    {'name': 'Organization sign-in', 'state': 'configured' if settings.oidc_issuer else 'pending', 'detail': 'Issuer configured' if settings.oidc_issuer else 'Connect your organization identity provider'},
                    {'name': 'Business connector', 'state': 'local' if settings.business_connector=='synthetic' else 'configured', 'detail': 'Synthetic mock system; no customer API connected' if settings.business_connector=='synthetic' else 'HTTPS contract adapter configured; customer sandbox acceptance required'},
                    {'name': 'Expired-record cleanup', 'state': 'available', 'detail': 'Dry-run and apply commands supplied; scheduling is operator-managed'},
                    {'name': 'Provider billing', 'state': 'pending', 'detail': 'Requires provider usage and invoice access'},
                    {'name': 'Cloud deployment', 'state': 'pending', 'detail': 'Choose account, region, private networking and secrets service'}]}

    @app.get('/v1/settings')
    def workspace_settings(request: Request):
        with factory() as db:
            u = human(request, db)
            return {'users': [{'id': v.id, 'name': v.name, 'email': v.email, 'role': v.role, 'active': v.active} for v in db.scalars(select(User).where(User.org_id == u.org_id))],
                    'mode': settings.mode, 'environment': runtime_environment(db,u.org_id), 'policy_engine': settings.policy_mode,
                    'database': 'SQLite local' if settings.database_url.startswith('sqlite') else 'PostgreSQL',
                    'limitations': ['Synthetic connector selected' if settings.business_connector=='synthetic' else 'HTTP adapter configured; customer acceptance not recorded', 'Cloud pilot not deployed', 'Provider billing not connected',
                                    'Schedule the supplied cleanup job; distributed rate limiting remains pilot work'],
                    'identity': {'sso_configured': bool(settings.oidc_issuer),
                                 'pkce': 'S256 / encrypted server-side verifier / single-use state',
                                 'required_acr': settings.oidc_required_acr or 'IdP flow policy (no ACR constraint)',
                                 'trust': 'Configured CA bundle' if settings.oidc_ca_bundle else 'System certificate trust',
                                 'schema_version': CURRENT_SCHEMA},
                    'retention': {'audit': 'Not automated yet', 'exports': 'Download expires after 7 days'}}

    # OIDC credentials and PKCE verifier remain server-side. Transactions are single-use.
    from . import oidc

    @app.get('/auth/oidc/start')
    def oidc_start():
        location, binding = oidc.begin(factory, settings)
        response = RedirectResponse(location)
        response.set_cookie('nexus_oidc', binding, httponly=True, secure=settings.mode != 'local',
                            samesite='lax', max_age=300, path='/auth')
        return response

    @app.get('/auth/oidc/callback')
    def oidc_callback(request: Request, state: str = '', code: str = ''):
        token = oidc.finish(factory, settings, state, request.cookies.get('nexus_oidc', ''), code)
        response = RedirectResponse('/')
        session_cookie(response, token)
        response.delete_cookie('nexus_oidc', path='/auth')
        return response

    from .workbench import register_workbench
    register_workbench(app, factory, settings, human)
    from .inference import register_inference
    register_inference(app, factory, settings, human)
    from .readiness import register_readiness
    register_readiness(app, factory, settings, human)
    from .durable import register_durable
    register_durable(app,factory,settings,human)
    from .documents import register_documents
    register_documents(app,factory,settings,human)
    from .retrieval_checks import register_retrieval_checks
    register_retrieval_checks(app,factory,settings,human)
    from .runtime_operations import register_runtime_operations
    register_runtime_operations(app,factory,settings,human)
    from .ingestion import register_ingestion
    register_ingestion(app,factory,settings,human)
    from .membership import register_membership
    register_membership(app,factory,settings,human)
    from .hybrid import register_hybrid
    register_hybrid(app,factory,settings,human)
    from .neural_index_runtime import register_neural_indexes
    register_neural_indexes(app,factory,settings,human)
    from .indexed_search_reviews import register_indexed_search_reviews
    register_indexed_search_reviews(app,factory,human)
    from .environments import register_environments
    from .session_context import register_session_context, response_context_valid
    register_session_context(app,factory,settings,human)
    register_environments(app,factory,settings,human)
    from .environment_runtime import register_environment_runtime
    register_environment_runtime(app,factory,settings,human)
    from .environment_asset_copy import register_environment_asset_copy
    register_environment_asset_copy(app,factory,settings,human)
    from .connector_checks import register_connector_checks
    register_connector_checks(app,factory,settings,human)
    @app.get('/v1/runtime-context')
    def runtime_context(request:Request):
        with factory() as db:
            user=human(request,db)
            return {'workspace_id':user.org_id,'environment':runtime_environment(db,user.org_id),'access_checked':True,'switching_enabled':switching_enabled(settings)}
    from .interfaces import register_interfaces
    register_interfaces(app, factory, settings, human)

    frontend = Path(settings.frontend_dir).resolve()
    if (frontend / 'assets').is_dir(): app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')

    @app.get('/{path:path}')
    def frontend_page(path: str):
        if path.startswith(('v1/', 'auth/', 'health/', 'api/')): fail(404, 'NOT_FOUND', 'Endpoint not found.')
        # Vite public assets live at the root, not only under /assets.
        # Serve only the explicitly public illustrations; never arbitrary backend files.
        if path in ('nexus-agent-neon.png', 'nexus-governance.svg'):
            asset = frontend / path
            if not asset.is_file(): fail(404, 'ASSET_NOT_FOUND', 'Rebuild the frontend to restore this illustration.')
            return FileResponse(asset)
        if Path(path).suffix or any(part.startswith('.') for part in Path(path).parts):
            fail(404, 'NOT_FOUND', 'Static asset not found.')
        if not (frontend / 'index.html').is_file():
            return JSONResponse({'message': 'Build the frontend: cd frontend && npm ci && npm run build', 'api_docs': '/api/docs'})
        return FileResponse(frontend / 'index.html')
    return app
