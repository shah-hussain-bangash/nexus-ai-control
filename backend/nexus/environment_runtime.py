"""Reviewed local runtime controls; retirement retains records and reserves the key."""
from fastapi import Request
from pydantic import Field,field_validator
from typing import Literal
from sqlalchemy import select,func,delete
from .db import Action,DurableRun,IngestionJob,InferenceCall,SessionRecord,SessionRuntimeContext,WorkspaceEnvironment,EnvironmentAssignment,now
from .schemas import Strict
from .security import fail
from .runtime_context import runtime_environment,switching_enabled
from .service import audit

# Unknown states also block. Future work types must join this review before
# admission is enabled; completed history is never deleted by these controls.
TERMINAL={Action:('verified','failed','denied','blocked','cancelled','rejected','changes_requested','expired'),
          DurableRun:('succeeded','failed','cancelled','rejected','expired'),
          IngestionJob:('published','failed','cancelled','archived','expired'),
          InferenceCall:('completed','reconciled')}

def runtime_review(db,org,key):
    # Core queries intentionally inspect the target from the initiating owner's
    # bound environment without retargeting a runtime session.
    counts={}
    for model,terminal in TERMINAL.items():
        table=model.__table__
        counts[table.name]=db.scalar(select(func.count()).select_from(table).where(table.c.org_id==org,table.c.env==key,table.c.status.not_in(terminal)))
    sessions=db.scalar(select(func.count()).select_from(SessionRecord).join(SessionRuntimeContext,SessionRuntimeContext.session_id==SessionRecord.id).where(
        SessionRuntimeContext.org_id==org,SessionRuntimeContext.environment==key,SessionRecord.expires>now()))
    return {'unfinished_work':counts,'selected_sessions':sessions}

class RuntimeControl(Strict):
    command:Literal['pause','resume','retire']
    expected_version:int=Field(ge=1,strict=True)
    expected_selected_sessions:int=Field(ge=0,strict=True)
    reviewed:Literal[True]
    note:str=Field(min_length=5,max_length=500)
    confirmation_key:str|None=Field(default=None,max_length=32,strict=True)

    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<5 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Include a visible review reason on one line.')
        return value.strip()

def register_environment_runtime(app,factory,settings,human):
    @app.post('/v1/workspace-environments/{key}/runtime-control')
    def control(key:str,body:RuntimeControl,request:Request):
        if not switching_enabled(settings):fail(403,'LOCAL_ONLY','Runtime lifecycle controls are available only in local mode.')
        with factory.begin() as db:
            actor=human(request,db,True,'members')  # Shared organization admission lock.
            row=db.get(WorkspaceEnvironment,(actor.org_id,key),with_for_update=True)
            if not row:fail(404,'ENVIRONMENT_NOT_FOUND','Environment not found in this workspace.')
            if key=='staging' or runtime_environment(db,actor.org_id)!='staging':
                fail(409,'CURRENT_ENVIRONMENT_PROTECTED','Switch to staging before managing another local runtime. Staging cannot be paused.')
            if row.version!=body.expected_version:fail(409,'STALE_VERSION','Environment changed. Refresh before reviewing again.')
            required='active' if body.command=='pause' else 'suspended'
            if row.state!=required:fail(409,'ENVIRONMENT_STATE','This command is unavailable for the current environment state.')
            if actor.role!='owner' or not db.get(EnvironmentAssignment,(actor.id,actor.org_id,key)):
                fail(403,'RUNTIME_OWNER_REQUIRED','An assigned active owner must review runtime controls.')
            if body.command=='retire' and body.confirmation_key!=key:
                fail(422,'RETIREMENT_CONFIRMATION_REQUIRED','Type the exact environment key to confirm permanent runtime retirement. Records are retained and this key cannot be reused.')
            review=runtime_review(db,actor.org_id,key)
            if any(review['unfinished_work'].values()):
                fail(409,'ENVIRONMENT_BUSY','Finish, cancel or reconcile unfinished work in this environment before changing runtime state.')
            if review['selected_sessions']!=body.expected_selected_sessions:
                fail(409,'STALE_RUNTIME_REVIEW','Selected sessions changed. Refresh and review the sign-out effect again.')
            sessions=select(SessionRuntimeContext.session_id).where(SessionRuntimeContext.org_id==actor.org_id,SessionRuntimeContext.environment==key)
            revoked=db.execute(delete(SessionRecord).where(SessionRecord.id.in_(sessions))).rowcount
            row.state={'pause':'suspended','resume':'active','retire':'retired'}[body.command];row.version+=1;row.updated=now()
            audit(db,actor.org_id,actor.id,'environment.runtime_'+body.command,detail={
                'environment_key':key,'version':row.version,'note':body.note,'sessions_revoked':revoked,'unfinished_work':review['unfinished_work'],'records_preserved':True})
            return {'key':key,'state':row.state,'version':row.version,'sessions_revoked':revoked,'records_preserved':True}
