"""Versioned local selection; pilot runtime remains staging-only."""
import secrets
from fastapi import Request
from pydantic import Field
from sqlalchemy import select
from .schemas import Strict
from .db import SessionRecord,SessionRuntimeContext,User,Agent,WorkspaceEnvironment,EnvironmentAssignment,now
from .security import digest,fail,get_session_context,public_session_context
from .runtime_context import CURRENT_ENVIRONMENT,switching_enabled,environment_user_allowed
from .service import audit

class Selection(Strict):
    workspace_id:str=Field(min_length=1,max_length=100)
    environment:str=Field(pattern=r'^[a-z][a-z0-9-]{1,31}$')
    expected_revision:int=Field(ge=1,le=9007199254740991,strict=True)
    expected_binding_id:str=Field(pattern=r'^[a-f0-9-]{36}$')
    expected_environment_version:int|None=Field(default=None,ge=1,strict=True)
    reviewed:bool=Field(default=False,strict=True)

def response_context_valid(request,factory,settings):
    workload=getattr(request.state,'authenticated_workload_context',None)
    if workload:
        agent_id,org,environment,generation,owner_id=workload
        with factory() as db:
            agent=db.get(Agent,agent_id)
            if not (agent and agent.status=='active' and (agent.org_id,agent.env,agent.generation,agent.owner_id)==(org,environment,generation,owner_id) and
                    environment_user_allowed(db,owner_id,org,environment,allow_non_staging=switching_enabled(settings))):return False
    snapshot=getattr(request.state,'authenticated_context',None)
    if not snapshot or getattr(request.state,'context_logout',False):return True
    session_id,user_id,org,environment,revision,binding,role=snapshot
    with factory() as db:
        session=db.get(SessionRecord,session_id);user=db.get(User,user_id);context=db.get(SessionRuntimeContext,session_id)
        return bool(session and session.user_id==user_id and session.expires>now() and user and user.active and user.org_id==org and user.role==role and context and
                    (context.user_id,context.org_id,context.environment,context.revision,context.binding_id)==(user_id,org,environment,revision,binding) and
                    environment_user_allowed(db,user_id,org,environment,allow_non_staging=switching_enabled(settings)))

def register_session_context(app,factory,settings,human):
    @app.get('/v1/session-context')
    def current(request:Request):
        with factory() as db:
            user=human(request,db);session=db.get(SessionRecord,digest(request.cookies['nexus_session']))
            return public_session_context(get_session_context(db,session,user,allow_non_staging=switching_enabled(settings)),switching_enabled(settings))

    @app.get('/v1/session-context/choices')
    def choices(request:Request):
        with factory() as db:
            user=human(request,db)
            rows=db.scalars(select(WorkspaceEnvironment).join(EnvironmentAssignment,(EnvironmentAssignment.org_id==WorkspaceEnvironment.org_id)&(EnvironmentAssignment.environment_key==WorkspaceEnvironment.key)).where(
                WorkspaceEnvironment.org_id==user.org_id,WorkspaceEnvironment.state=='active',EnvironmentAssignment.user_id==user.id).order_by(WorkspaceEnvironment.created,WorkspaceEnvironment.key)).all()
            return {'items':[{'key':r.key,'name':r.name,'version':r.version} for r in rows if r.key==CURRENT_ENVIRONMENT or switching_enabled(settings)],'switching_enabled':switching_enabled(settings)}

    @app.post('/v1/session-context/select')
    def select_context(body:Selection,request:Request):
        with factory.begin() as db:
            user=human(request,db,True);session=db.get(SessionRecord,digest(request.cookies['nexus_session']))
            context=get_session_context(db,session,user,allow_non_staging=switching_enabled(settings))
            if body.expected_binding_id!=context.binding_id or body.expected_revision!=context.revision:
                fail(409,'STALE_SESSION_CONTEXT','Your workspace context changed. Refresh before continuing.')
            if body.workspace_id!=user.org_id:fail(403,'WORKSPACE_ACCESS_DENIED','This workspace is unavailable to your identity.')
            if body.environment==context.environment:return public_session_context(context,switching_enabled(settings))
            if not switching_enabled(settings):fail(409,'ENVIRONMENT_SWITCHING_UNAVAILABLE','Environment selection is available only in local mode.')
            if not body.reviewed:fail(422,'REVIEW_REQUIRED','Review the workspace reset before switching.')
            target=db.get(WorkspaceEnvironment,(user.org_id,body.environment),with_for_update=True)
            if not target or not environment_user_allowed(db,user.id,user.org_id,body.environment,allow_non_staging=True):
                fail(403,'ENVIRONMENT_ACCESS_DENIED','This active environment is unavailable to your account.')
            if body.expected_environment_version!=target.version:fail(409,'STALE_VERSION','The target environment changed. Refresh before switching.')
            origin=context.environment
            audit(db,user.org_id,user.id,'session.environment_selected',detail={'from_environment':origin,'to_environment':target.key,'revision':context.revision+1,'environment_version':target.version})
            context.environment=target.key;context.revision+=1;session.csrf=secrets.token_urlsafe(32)
            request.state.authenticated_context=(session.id,user.id,user.org_id,context.environment,context.revision,context.binding_id,user.role)
            return public_session_context(context,True)
