"""Session-owned context contract; non-staging selection remains disabled."""
from fastapi import Request
from pydantic import Field
from .schemas import Strict
from .db import SessionRecord
from .security import digest,fail,get_session_context,public_session_context
from .runtime_context import CURRENT_ENVIRONMENT


class Selection(Strict):
    workspace_id: str = Field(min_length=1,max_length=100)
    environment: str = Field(pattern=r'^[a-z][a-z0-9-]{1,31}$')
    expected_revision: int = Field(ge=1,le=9007199254740991)
    expected_binding_id: str = Field(pattern=r'^[a-f0-9-]{36}$')


def register_session_context(app,factory,human):
    @app.get('/v1/session-context')
    def current(request:Request):
        with factory() as db:
            user=human(request,db)
            session=db.get(SessionRecord,digest(request.cookies['nexus_session']))
            return public_session_context(get_session_context(db,session,user))

    @app.post('/v1/session-context/select')
    def select_context(body:Selection,request:Request):
        with factory.begin() as db:
            user=human(request,db,True)
            session=db.get(SessionRecord,digest(request.cookies['nexus_session']))
            context=get_session_context(db,session,user)
            if body.expected_binding_id!=context.binding_id or body.expected_revision!=context.revision:
                fail(409,'STALE_SESSION_CONTEXT','Your workspace context changed. Refresh before continuing.')
            if body.workspace_id!=user.org_id:fail(403,'WORKSPACE_ACCESS_DENIED','This workspace is unavailable to your identity.')
            if body.environment!=CURRENT_ENVIRONMENT:
                fail(409,'ENVIRONMENT_SWITCHING_UNAVAILABLE','Runtime environment switching is not enabled.')
            # Re-selecting the current context is a read-only acknowledgement.
            return public_session_context(context)
