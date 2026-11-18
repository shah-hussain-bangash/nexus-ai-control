"""Current staging access gate; does not enable runtime environment switching."""
from sqlalchemy import select, and_, event
from sqlalchemy.orm import Session, with_loader_criteria
from .db import WorkspaceEnvironment, EnvironmentAssignment, User, Scoped

CURRENT_ENVIRONMENT = 'staging'


def bind_runtime_context(db,org_id):
    db.info['nexus_runtime_context']=(org_id,CURRENT_ENVIRONMENT)


@event.listens_for(Session,'do_orm_execute')
def constrain_runtime_queries(execute_state):
    context=execute_state.session.info.get('nexus_runtime_context')
    if context and (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        org_id,environment=context
        execute_state.statement=execute_state.statement.options(with_loader_criteria(
            Scoped,lambda model:and_(model.org_id==org_id,model.env==environment),include_aliases=True))


@event.listens_for(Session,'before_flush')
def constrain_runtime_writes(db,flush_context,instances):
    context=db.info.get('nexus_runtime_context')
    if not context:return
    org_id,environment=context
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row,Scoped):
            if row.org_id!=org_id or row.env not in (None,environment):
                raise RuntimeError('Cross-context writes are not permitted.')
            if row in db.new and row.env is None:row.env=environment


def environment_user_allowed(db, user_id, org_id, environment=CURRENT_ENVIRONMENT):
    if environment != CURRENT_ENVIRONMENT:
        return False
    query=(select(EnvironmentAssignment.user_id)
           .join(WorkspaceEnvironment,and_(WorkspaceEnvironment.org_id==EnvironmentAssignment.org_id,
                                         WorkspaceEnvironment.key==EnvironmentAssignment.environment_key))
           .join(User,and_(User.id==EnvironmentAssignment.user_id,User.org_id==EnvironmentAssignment.org_id))
           .where(EnvironmentAssignment.user_id==user_id,EnvironmentAssignment.org_id==org_id,
                  EnvironmentAssignment.environment_key==environment,WorkspaceEnvironment.state=='active',User.active==1))
    return db.scalar(query) is not None
