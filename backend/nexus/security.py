import hashlib
import hmac
import secrets
import base64
import re
import jwt
from fastapi import HTTPException
from sqlalchemy import select,update
from .db import SessionRecord, SessionRuntimeContext, User, Agent, Organization, now
from .runtime_context import CURRENT_ENVIRONMENT, environment_user_allowed, bind_runtime_context, bound_runtime_context, switching_enabled


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


def require_request_context(request, org_id,environment=CURRENT_ENVIRONMENT):
    if request is None:
        return
    workspaces=request.headers.getlist('X-Nexus-Workspace')+request.query_params.getlist('workspace')+request.query_params.getlist('org_id')
    environments=request.headers.getlist('X-Nexus-Environment')+request.query_params.getlist('environment')+request.query_params.getlist('env')
    if len(set(workspaces))>1 or len(set(environments))>1:
        fail(400,'CONTEXT_CONFLICT','Conflicting workspace or environment selectors are not permitted.')
    if workspaces and workspaces[0]!=org_id:
        fail(403,'WORKSPACE_ACCESS_DENIED','The requested workspace is not available to this identity.')
    if environments and environments[0]!=environment:
        fail(409,'ENVIRONMENT_CONTEXT_CHANGED','The requested environment does not match the selected context. Refresh before continuing.')


def require_environment_access(db,user,environment=CURRENT_ENVIRONMENT,allow_non_staging=False):
    if not environment_user_allowed(db,user.id,user.org_id,environment,allow_non_staging=allow_non_staging):
        fail(403,'ENVIRONMENT_ACCESS_DENIED','Access to the current environment is unavailable. Contact your workspace owner.')


def require_identity_context(db,org_id,environment=CURRENT_ENVIRONMENT):
    # Authentication is not permission to retarget an existing operation. Use a
    # fresh session for a different workspace/environment, even with cached rows.
    context=bound_runtime_context(db)
    if context is not None and context!=(org_id,environment):
        fail(409,'IDENTITY_CONTEXT_CHANGED','The authenticated identity does not match this operation context. Start a fresh operation.')


def get_session_context(db,session,user,allow_non_staging=False):
    context=db.scalar(select(SessionRuntimeContext).where(SessionRuntimeContext.session_id==session.id).execution_options(populate_existing=True))
    if (not context or context.user_id!=user.id or context.org_id!=user.org_id
        or not re.fullmatch(r'[a-z][a-z0-9-]{1,31}',context.environment) or (context.environment!=CURRENT_ENVIRONMENT and not allow_non_staging) or type(context.revision) is not int or context.revision<1
        or not isinstance(context.binding_id,str) or not re.fullmatch(r'[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}',context.binding_id)):
        fail(401,'SESSION_CONTEXT_UNAVAILABLE','Your session context is unavailable. Sign in again.')
    return context


def public_session_context(context,enabled=False):
    return {'workspace_id':context.org_id,'user_id':context.user_id,'environment':context.environment,
            'revision':context.revision,'binding_id':context.binding_id,'switching_enabled':enabled}


def require_session_revision(request,context):
    ids=request.headers.getlist('X-Nexus-Context-ID');revisions=request.headers.getlist('X-Nexus-Context-Revision')
    if not ids and not revisions:
        if request.method=='GET' and request.url.path in ('/v1/me','/v1/session-context'):return
        if context.environment==CURRENT_ENVIRONMENT and context.revision==1:return
        fail(409,'STALE_SESSION_CONTEXT','Refresh your workspace before continuing.')
    if len(ids)!=1 or len(revisions)!=1 or not re.fullmatch(r'[1-9][0-9]{0,15}',revisions[0]):
        fail(400,'INVALID_SESSION_CONTEXT','Refresh your workspace context and try again.')
    if ids[0]!=context.binding_id or int(revisions[0])!=context.revision:
        fail(409,'STALE_SESSION_CONTEXT','Your workspace context changed. Refresh before continuing.')


def session_user(request, db, write=False,serialize=True):
    raw=request.cookies.get('nexus_session','');identity=digest(raw)
    def identity_rows():
        session=db.scalar(select(SessionRecord).where(SessionRecord.id==identity).execution_options(populate_existing=True))
        if not session or session.expires<=now():fail(401,'AUTH_REQUIRED','Your session expired. Sign in again.')
        user=db.scalar(select(User).where(User.id==session.user_id).execution_options(populate_existing=True))
        if not user or not user.active:fail(401,'AUTH_REQUIRED','Workspace access is unavailable.')
        return session,user
    session,user=identity_rows()
    if write and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),session.csrf):fail(403,'CSRF_FAILED','Refresh your session and try again.')
    if write and serialize:
        # One ordering for all human writes: organization, then fresh context.
        # Selection and revocation cannot cross another admitted write.
        db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
        session,user=identity_rows()
    app=request.scope.get('app');enabled=switching_enabled(getattr(getattr(app,'state',None),'settings',None))
    context=get_session_context(db,session,user,allow_non_staging=enabled)
    require_session_revision(request,context)
    require_request_context(request,user.org_id,context.environment)
    if write and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),session.csrf):fail(403,'CSRF_FAILED','Refresh your session and try again.')
    require_identity_context(db,user.org_id,context.environment)
    require_environment_access(db,user,context.environment,allow_non_staging=enabled)
    bind_runtime_context(db,user.org_id,context.environment)
    request.state.authenticated_context=(session.id,user.id,user.org_id,context.environment,context.revision,context.binding_id,user.role)
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
    require_identity_context(db,user.org_id)
    require_environment_access(db,user)
    token = secrets.token_urlsafe(40); csrf = secrets.token_urlsafe(32)
    record=SessionRecord(id=digest(token), user_id=user.id, csrf=csrf, expires=now() + settings.session_seconds)
    db.add(record);db.flush()
    db.add(SessionRuntimeContext(session_id=record.id,user_id=user.id,org_id=user.org_id,environment=CURRENT_ENVIRONMENT))
    return token, csrf


def workload_token(agent, settings):
    return jwt.encode({'iss': 'nexus-workload', 'aud': 'nexus-gateway', 'sub': agent.id,
                       'org': agent.org_id, 'env': agent.env, 'generation': agent.generation,
                       'iat': int(now()), 'exp': int(now()) + 300}, settings.agent_secret, algorithm='HS256')


def authenticate_agent(token, db, settings, request=None,write=False):
    try:
        claims = jwt.decode(token, settings.agent_secret, algorithms=['HS256'], audience='nexus-gateway',
                            issuer='nexus-workload', options={'require': ['sub', 'org', 'env', 'exp', 'iat', 'generation']})
    except jwt.PyJWTError: fail(401, 'INVALID_AGENT_TOKEN', 'Workload authentication failed.')
    require_identity_context(db,claims['org'],claims['env'])
    if write:
        # Match human admission ordering. A pause cannot pass an empty-work
        # review while a workload concurrently admits a new action.
        db.execute(update(Organization).where(Organization.id==claims['org']).values(name=Organization.name))
    agent = db.scalar(select(Agent).where(Agent.id==claims['sub']).execution_options(populate_existing=True))
    if not agent or agent.org_id != claims['org'] or agent.env != claims['env']:
        fail(401, 'INVALID_AGENT_TOKEN', 'Workload authentication failed.')
    if agent.status != 'active' or agent.generation != claims['generation']:
        fail(403, 'AGENT_INACTIVE', 'Agent is suspended, revoked or inactive.')
    require_request_context(request,agent.org_id,agent.env)
    require_identity_context(db,agent.org_id,agent.env)
    if not environment_user_allowed(db,agent.owner_id,agent.org_id,agent.env,allow_non_staging=switching_enabled(settings)):
        fail(403,'ENVIRONMENT_ACCESS_DENIED','The workload environment or owner authorization is unavailable.')
    bind_runtime_context(db,agent.org_id,agent.env)
    if request is not None:
        request.state.authenticated_workload_context=(agent.id,agent.org_id,agent.env,agent.generation,agent.owner_id)
    return agent
