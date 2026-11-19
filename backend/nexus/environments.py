"""Organization-scoped environment inventory; runtime switching remains disabled."""
from typing import Literal
from fastapi import Request
from pydantic import Field, field_validator
from sqlalchemy import select, update, delete, func
from .db import Organization, User, SessionRecord, WorkspaceEnvironment, EnvironmentAssignment, Base, now, public
from .schemas import Strict
from .security import fail
from .service import audit


def assign_staging(db, user):
    """Enroll a newly provisioned user without changing their organization or role."""
    if not db.get(WorkspaceEnvironment,(user.org_id,'staging')):
        db.add(WorkspaceEnvironment(org_id=user.org_id,key='staging',name='Staging',state='active'))
        db.flush()
    if not db.get(EnvironmentAssignment,(user.id,user.org_id,'staging')):
        db.add(EnvironmentAssignment(user_id=user.id,org_id=user.org_id,environment_key='staging'))


class EnvironmentInput(Strict):
    key: str = Field(pattern=r'^[a-z][a-z0-9-]{1,31}$')
    name: str = Field(min_length=2,max_length=80)
    note: str = Field(min_length=5,max_length=500)

    @field_validator('name','note')
    @classmethod
    def visible(cls,value,info):
        minimum=2 if info.field_name=='name' else 5
        if len(value.strip())<minimum or any(ord(c)<32 for c in value):raise ValueError('Use visible text without control characters.')
        return value.strip()


class ArchiveInput(Strict):
    expected_version: int = Field(ge=1)
    command: Literal['archive','restore']
    note: str = Field(min_length=5,max_length=500)

    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<5:raise ValueError('Include a visible review note.')
        return value.strip()


class AssignmentInput(Strict):
    user_id: str = Field(min_length=1,max_length=100)
    command: Literal['grant','revoke']
    expected_version: int = Field(ge=1,strict=True)
    expected_member_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    note: str = Field(min_length=5,max_length=500)
    reviewed: Literal[True]

    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<5 or any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError('Include a visible reason on one line.')
        return value.strip()


def serialize(row):
    return {**public(row),'human_runtime_enabled':row.key=='staging' and row.state=='active'}


def register_environments(app,factory,settings,human):
    @app.get('/v1/workspace-environments')
    def listing(request:Request):
        with factory() as db:
            user=human(request,db,False,'members')
            organization=db.get(Organization,user.org_id)
            rows=db.scalars(select(WorkspaceEnvironment).where(WorkspaceEnvironment.org_id==user.org_id).order_by(WorkspaceEnvironment.created,WorkspaceEnvironment.key)).all()
            return {'workspace':{'id':user.org_id,'name':organization.name},'items':[serialize(row) for row in rows],
                    'current_environment':'staging','switching_enabled':False,
                    'boundary':'Environment inventory is available. New environments are preparing; runtime switching, promotion and non-staging data access are not enabled.'}

    @app.post('/v1/workspace-environments',status_code=201)
    def create(body:EnvironmentInput,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'members')
            db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            if db.get(WorkspaceEnvironment,(user.org_id,body.key)):fail(409,'ENVIRONMENT_EXISTS','This environment key already exists in your workspace.')
            if db.scalar(select(func.count()).select_from(WorkspaceEnvironment).where(WorkspaceEnvironment.org_id==user.org_id))>=20:
                fail(429,'ENVIRONMENT_CAPACITY','This workspace supports at most 20 environment records.')
            row=WorkspaceEnvironment(org_id=user.org_id,key=body.key,name=body.name,state='preparing')
            db.add(row);db.flush()
            audit(db,user.org_id,user.id,'environment.registered',detail={'environment_key':row.key,'note':body.note})
            return serialize(row)

    @app.post('/v1/workspace-environments/{key}/control')
    def control(key:str,body:ArchiveInput,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'members')
            db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            row=db.get(WorkspaceEnvironment,(user.org_id,key),with_for_update=True)
            if not row:fail(404,'ENVIRONMENT_NOT_FOUND','Environment not found in this workspace.')
            if key=='staging':fail(409,'CURRENT_ENVIRONMENT_PROTECTED','The current staging environment cannot be archived.')
            if row.version!=body.expected_version:fail(409,'STALE_VERSION','This environment changed. Refresh before confirming.')
            target='archived' if body.command=='archive' else 'preparing'
            required='preparing' if body.command=='archive' else 'archived'
            if row.state!=required:fail(409,'ENVIRONMENT_STATE','This command is not available for the current state.')
            if body.command=='archive':
                for table in Base.metadata.sorted_tables:
                    if 'org_id' in table.c and 'env' in table.c and db.scalar(select(func.count()).select_from(table).where(table.c.org_id==user.org_id,table.c.env==key)):
                        fail(409,'ENVIRONMENT_IN_USE','This environment contains existing records and cannot be archived through the inventory.')
            row.state=target;row.version+=1;row.updated=now()
            audit(db,user.org_id,user.id,'environment.'+body.command,detail={'environment_key':key,'version':row.version,'note':body.note})
            return serialize(row)

    @app.get('/v1/workspace-environments/{key}/assignments')
    def assignments(key:str,request:Request):
        from .membership import revision
        with factory() as db:
            user=human(request,db,False,'members')
            # Lock the same organization row as writers so version and membership
            # form one snapshot even at PostgreSQL READ COMMITTED isolation.
            db.scalar(select(Organization.id).where(Organization.id==user.org_id).with_for_update())
            environment=db.get(WorkspaceEnvironment,(user.org_id,key))
            if not environment:fail(404,'ENVIRONMENT_NOT_FOUND','Environment not found in this workspace.')
            users=db.scalars(select(User).where(User.org_id==user.org_id).order_by(User.name,User.id).limit(201)).all()
            if len(users)>200:fail(422,'MEMBER_CAPACITY','This bounded owner workspace supports up to 200 members.')
            rows=db.execute(select(User.id,User.name,User.role,User.active).join(EnvironmentAssignment,EnvironmentAssignment.user_id==User.id).where(
                EnvironmentAssignment.org_id==user.org_id,EnvironmentAssignment.environment_key==key,User.org_id==user.org_id).order_by(User.name,User.id)).all()
            assigned={r.id for r in rows}
            by_id={u.id:u for u in users}
            return {'items':[{'id':r.id,'name':r.name,'email':by_id[r.id].email,'role':r.role,'active':bool(r.active),'revision':revision(db,by_id[r.id])} for r in rows],
                    'candidates':[{'id':u.id,'name':u.name,'email':u.email,'role':u.role,'active':True,'revision':revision(db,u)} for u in users
                                  if u.id not in assigned and u.active and not (key=='staging' and u.role=='owner')],
                    'environment':serialize(environment),
                    'editing_enabled':environment.state in ('active','preparing'),'switching_enabled':False}

    @app.post('/v1/workspace-environments/{key}/assignments/control')
    def change_assignment(key:str,body:AssignmentInput,request:Request):
        from .membership import revision
        with factory.begin() as db:
            actor=human(request,db,True,'members')
            db.execute(update(Organization).where(Organization.id==actor.org_id).values(name=Organization.name))
            environment=db.get(WorkspaceEnvironment,(actor.org_id,key),with_for_update=True)
            if not environment:fail(404,'ENVIRONMENT_NOT_FOUND','Environment not found in this workspace.')
            if environment.version!=body.expected_version:fail(409,'STALE_VERSION','Environment or assignments changed. Refresh before confirming.')
            if environment.state not in ('active','preparing'):fail(409,'ENVIRONMENT_STATE','Restore this environment before changing assignments.')
            target=db.scalar(select(User).where(User.id==body.user_id,User.org_id==actor.org_id).with_for_update())
            if not target:fail(404,'MEMBER_NOT_FOUND','Member is not in this workspace.')
            if key=='staging' and target.role=='owner':fail(409,'OWNER_PROTECTED','Current owner access requires a separate reviewed ownership procedure.')
            if revision(db,target)!=body.expected_member_revision:fail(409,'STALE_VERSION','Member or session state changed. Refresh before confirming.')
            assignment=db.get(EnvironmentAssignment,(target.id,actor.org_id,key))
            if body.command=='grant':
                if not target.active:fail(409,'MEMBER_INACTIVE','Activate the member before assigning an environment.')
                if assignment:fail(409,'ASSIGNMENT_EXISTS','This member is already assigned. Refresh the list.')
                db.add(EnvironmentAssignment(user_id=target.id,org_id=actor.org_id,environment_key=key))
            else:
                if not assignment:fail(409,'ASSIGNMENT_MISSING','This member is no longer assigned. Refresh the list.')
                db.delete(assignment)
            revoked=db.execute(delete(SessionRecord).where(SessionRecord.user_id==target.id)).rowcount
            environment.version+=1;environment.updated=now()
            audit(db,actor.org_id,actor.id,'environment.assignment_'+body.command,detail={
                'environment_key':key,'member_id':target.id,'version':environment.version,
                'sessions_revoked':revoked,'note':body.note})
            return {'status':'assigned' if body.command=='grant' else 'removed','member_id':target.id,
                    'environment_key':key,'version':environment.version,'sessions_revoked':revoked,
                    'switching_enabled':False}
