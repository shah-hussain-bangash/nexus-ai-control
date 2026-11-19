"""Bound runtime isolation and mode-aware active-environment membership gates."""
import re
from sqlalchemy import select, and_, event, inspect
from sqlalchemy.orm import Session, with_loader_criteria
from .db import WorkspaceEnvironment, EnvironmentAssignment, User, Scoped

CURRENT_ENVIRONMENT = 'staging'


def validate_context(org_id,environment):
    if not isinstance(org_id,str) or not 1<=len(org_id)<=100 or not org_id.strip() or any(ord(c)<32 or ord(c)==127 for c in org_id):
        raise RuntimeError('Invalid runtime workspace context.')
    if not isinstance(environment,str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,31}',environment):
        raise RuntimeError('Invalid runtime environment context.')
    return org_id,environment


def bound_runtime_context(db):
    if 'nexus_runtime_context' not in db.info:return None
    context=db.info['nexus_runtime_context']
    if not isinstance(context,tuple) or len(context)!=2:raise RuntimeError('Invalid bound runtime context.')
    return validate_context(*context)


def bind_runtime_context(db,org_id,environment=CURRENT_ENVIRONMENT):
    # Internal propagation, not an authorization decision or switching endpoint.
    db.info['nexus_runtime_context']=validate_context(org_id,environment)


def runtime_environment(db,org_id,environment=None):
    context=bound_runtime_context(db)
    if context:
        if context[0]!=org_id or environment is not None and context[1]!=environment:
            raise RuntimeError('Runtime context does not match the requested workspace/environment.')
        return context[1]
    if environment is None:raise RuntimeError('Bind a runtime context or provide an explicit environment.')
    return validate_context(org_id,environment)[1]


@event.listens_for(Session,'do_orm_execute')
def constrain_runtime_queries(execute_state):
    context=bound_runtime_context(execute_state.session)
    if context and (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        org_id,environment=context
        execute_state.statement=execute_state.statement.options(with_loader_criteria(
            Scoped,lambda model:and_(model.org_id==org_id,model.env==environment),include_aliases=True))


@event.listens_for(Session,'before_flush')
def constrain_runtime_writes(db,flush_context,instances):
    context=bound_runtime_context(db)
    if not context:return
    org_id,environment=context
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row,Scoped):
            state=inspect(row)
            if row not in db.new and any(state.attrs[field].history.has_changes() for field in ('org_id','env')):
                raise RuntimeError('Persisted runtime scope cannot be changed in a bound session.')
            if row in db.new and row.env is None:row.env=environment
            if row.org_id!=org_id or row.env!=environment:
                raise RuntimeError('Cross-context writes are not permitted.')


def switching_enabled(settings):
    return settings is not None and settings.mode=='local'


def environment_user_allowed(db, user_id, org_id, environment=CURRENT_ENVIRONMENT,allow_non_staging=False):
    if environment != CURRENT_ENVIRONMENT and not allow_non_staging:
        return False
    query=(select(EnvironmentAssignment.user_id)
           .join(WorkspaceEnvironment,and_(WorkspaceEnvironment.org_id==EnvironmentAssignment.org_id,
                                         WorkspaceEnvironment.key==EnvironmentAssignment.environment_key))
           .join(User,and_(User.id==EnvironmentAssignment.user_id,User.org_id==EnvironmentAssignment.org_id))
           .where(EnvironmentAssignment.user_id==user_id,EnvironmentAssignment.org_id==org_id,
                  EnvironmentAssignment.environment_key==environment,WorkspaceEnvironment.state=='active',User.active==1))
    return db.scalar(query) is not None
