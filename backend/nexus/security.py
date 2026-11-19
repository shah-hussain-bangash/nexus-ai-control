import hashlib
import hmac
import secrets
import base64
import jwt
from fastapi import HTTPException
from sqlalchemy import select
from .db import SessionRecord, User, Agent, now
from .runtime_context import CURRENT_ENVIRONMENT, environment_user_allowed, bind_runtime_context


def fail(status, code, message):
    raise HTTPException(status, {'code': code, 'message': message})


def digest(value: str): return hashlib.sha256(value.encode()).hexdigest()


def password_hash(value):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 310000).hex()


def password_valid(value, stored):
    if ':' not in stored: return False
    salt, expected = stored.split(':', 1)
    actual = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 310000).hex()
    return hmac.compare_digest(actual, expected)


def require_request_context(request, org_id):
    if request is None:
        return
    workspaces=request.headers.getlist('X-Nexus-Workspace')+request.query_params.getlist('workspace')+request.query_params.getlist('org_id')
    environments=request.headers.getlist('X-Nexus-Environment')+request.query_params.getlist('environment')+request.query_params.getlist('env')
    if len(set(workspaces))>1 or len(set(environments))>1:
        fail(400,'CONTEXT_CONFLICT','Conflicting workspace or environment selectors are not permitted.')
    if workspaces and workspaces[0]!=org_id:
        fail(403,'WORKSPACE_ACCESS_DENIED','The requested workspace is not available to this identity.')
    if environments and environments[0]!=CURRENT_ENVIRONMENT:
        fail(409,'ENVIRONMENT_SWITCHING_UNAVAILABLE','Runtime environment switching is not enabled. Use the current staging environment.')


def require_environment_access(db,user,environment=CURRENT_ENVIRONMENT):
    if not environment_user_allowed(db,user.id,user.org_id,environment):
        fail(403,'ENVIRONMENT_ACCESS_DENIED','Access to the current environment is unavailable. Contact your workspace owner.')


def session_user(request, db, write=False):
    raw = request.cookies.get('nexus_session', '')
    session = db.get(SessionRecord, digest(raw))
    if not session or session.expires <= now(): fail(401, 'AUTH_REQUIRED', 'Your session expired. Sign in again.')
    user = db.get(User, session.user_id)
    if not user or not user.active: fail(401, 'AUTH_REQUIRED', 'Workspace access is unavailable.')
    if write and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.csrf):
        fail(403, 'CSRF_FAILED', 'Refresh your session and try again.')
    require_request_context(request,user.org_id)
    require_environment_access(db,user)
    bind_runtime_context(db,user.org_id)
    return user


PERMISSIONS = {
    'owner': {'members', 'manage', 'operate', 'export', 'policy', 'contain'},
    'security': {'manage', 'operate', 'export', 'policy', 'contain'},
    'engineer': {'operate'},
    'approver': {'approve'},
    'auditor': {'export'},
}


def permit(user, permission):
    if permission not in PERMISSIONS.get(user.role, set()): fail(403, 'FORBIDDEN', 'Your role does not permit this operation.')


def issue_session(db, user, settings):
    require_environment_access(db,user)
    token = secrets.token_urlsafe(40); csrf = secrets.token_urlsafe(32)
    db.add(SessionRecord(id=digest(token), user_id=user.id, csrf=csrf, expires=now() + settings.session_seconds))
    return token, csrf


def workload_token(agent, settings):
    return jwt.encode({'iss': 'nexus-workload', 'aud': 'nexus-gateway', 'sub': agent.id,
                       'org': agent.org_id, 'env': agent.env, 'generation': agent.generation,
                       'iat': int(now()), 'exp': int(now()) + 300}, settings.agent_secret, algorithm='HS256')


def authenticate_agent(token, db, settings, request=None):
    try:
        claims = jwt.decode(token, settings.agent_secret, algorithms=['HS256'], audience='nexus-gateway',
                            issuer='nexus-workload', options={'require': ['sub', 'org', 'env', 'exp', 'iat', 'generation']})
    except jwt.PyJWTError: fail(401, 'INVALID_AGENT_TOKEN', 'Workload authentication failed.')
    agent = db.get(Agent, claims['sub'])
    if not agent or agent.org_id != claims['org'] or agent.env != claims['env']:
        fail(401, 'INVALID_AGENT_TOKEN', 'Workload authentication failed.')
    if agent.status != 'active' or agent.generation != claims['generation']:
        fail(403, 'AGENT_INACTIVE', 'Agent is suspended, revoked or inactive.')
    require_request_context(request,agent.org_id)
    if not environment_user_allowed(db,agent.owner_id,agent.org_id,agent.env):
        fail(403,'ENVIRONMENT_ACCESS_DENIED','The workload environment or owner authorization is unavailable.')
    bind_runtime_context(db,agent.org_id,agent.env)
    return agent
