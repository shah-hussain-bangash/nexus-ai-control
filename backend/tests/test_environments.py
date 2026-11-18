import pytest
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from conftest import auth
from nexus.db import (WorkspaceEnvironment, EnvironmentAssignment, User, Agent, Audit,
                      SchemaVersion, CURRENT_SCHEMA, migrate, user_organization_index)


def create(ctx,key='production',**changes):
    headers,_=auth(ctx)
    return ctx['client'].post('/v1/workspace-environments',headers=headers,json={
        'key':key,'name':'Production','note':'Prepared a separate synthetic environment.',**changes})


def control(ctx,row,command,**changes):
    headers,_=auth(ctx)
    return ctx['client'].post('/v1/workspace-environments/'+row['key']+'/control',headers=headers,json={
        'expected_version':row['version'],'command':command,'note':'Reviewed this environment inventory change.',**changes})


def test_default_environment_preserves_current_runtime_and_members(ctx):
    assert ctx['client'].get('/v1/workspace-environments').status_code==401
    auth(ctx)
    result=ctx['client'].get('/v1/workspace-environments').json()
    assert result['workspace']['id']=='northstar'
    assert result['current_environment']=='staging' and result['switching_enabled'] is False
    assert len(result['items'])==1 and result['items'][0]['human_runtime_enabled'] is True
    members=ctx['client'].get('/v1/workspace-environments/staging/assignments').json()
    assert len(members['items'])==3 and not members['editing_enabled']
    assert all(set(row)=={'id','name','role','active'} for row in members['items'])


def test_registered_environment_cannot_activate_or_switch_runtime(ctx):
    response=create(ctx)
    assert response.status_code==201,response.text
    row=response.json()
    assert row['state']=='preparing' and row['human_runtime_enabled'] is False
    assert create(ctx).status_code==409
    assert create(ctx,key='development',state='active').status_code==422
    assert create(ctx,key='development',org_id='other').status_code==422
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(Agent).where(Agent.env=='production'))==0
        assert db.scalar(select(func.count()).select_from(EnvironmentAssignment).where(EnvironmentAssignment.environment_key=='production'))==0


@pytest.mark.parametrize('role',['engineer','approver','auditor','security'])
def test_inventory_is_owner_only_and_writes_require_csrf(ctx,role):
    with ctx['db'].begin() as db:
        member=db.scalar(select(User).where(User.email=='reviewer@nexus.local'))
        member.role=role
    auth(ctx,role)
    assert ctx['client'].get('/v1/workspace-environments').status_code==403
    assert ctx['client'].post('/v1/workspace-environments',json={'key':'production','name':'Production','note':'Reviewed synthetic environment.'}).status_code==403


def test_owner_write_without_csrf_is_rejected(ctx):
    auth(ctx)
    assert ctx['client'].post('/v1/workspace-environments',json={'key':'production','name':'Production','note':'Reviewed synthetic environment.'}).status_code==403


def test_inventory_and_assignments_are_tenant_scoped(ctx):
    row=create(ctx).json()
    headers,_=auth(ctx,org='other')
    assert ctx['client'].get('/v1/workspace-environments').json()['workspace']['id']=='other'
    assert ctx['client'].get('/v1/workspace-environments/production/assignments').status_code==404
    assert ctx['client'].post('/v1/workspace-environments/production/control',headers=headers,json={
        'command':'archive','expected_version':row['version'],'note':'Cross tenant synthetic request.'}).status_code==404
    other=ctx['client'].post('/v1/workspace-environments',headers=headers,json={
        'key':'production','name':'Other production','note':'Independent environment with the same key.'})
    assert other.status_code==201
    assert ctx['client'].get('/v1/workspace-environments/staging/assignments').json()['items'][0]['id']=='other-user'
    auth(ctx)
    assert ctx['client'].get('/v1/workspace-environments').json()['items'][1]['name']=='Production'


def test_archive_restore_versions_default_protection_and_audit(ctx):
    row=create(ctx).json()
    archived=control(ctx,row,'archive')
    assert archived.status_code==200 and archived.json()['state']=='archived'
    assert control(ctx,row,'restore').status_code==409
    restored=control(ctx,archived.json(),'restore')
    assert restored.status_code==200 and restored.json()['state']=='preparing'
    assert control(ctx,{'key':'staging','version':1},'archive').status_code==409
    assert control(ctx,{'key':'missing','version':1},'archive').status_code==404
    with ctx['db']() as db:
        events=db.scalars(select(Audit.event).where(Audit.event.like('environment.%')).order_by(Audit.created,Audit.id)).all()
        assert events==['environment.registered','environment.archive','environment.restore']


def test_cannot_archive_an_environment_with_existing_business_data(ctx):
    row=create(ctx).json()
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
        db.add(Agent(org_id='northstar',env='production',name='Legacy agent',owner_id=owner.id,risk='low'))
    response=control(ctx,row,'archive')
    assert response.status_code==409 and response.json()['error']['code']=='ENVIRONMENT_IN_USE'


@pytest.mark.parametrize('changes',[{'key':'../production'},{'key':'Production'},{'name':' a '},{'note':'     '},{'name':'Bad\nName'}])
def test_invalid_environment_records_are_rejected(ctx,changes):
    assert create(ctx,**changes).status_code==422


def test_newly_provisioned_member_receives_only_staging_assignment(ctx):
    from test_membership import create as provision
    response=provision(ctx)
    assert response.status_code==201,response.text
    user_id=response.json()['member']['id']
    with ctx['db']() as db:
        assignments=db.scalars(select(EnvironmentAssignment).where(EnvironmentAssignment.user_id==user_id)).all()
        assert len(assignments)==1 and assignments[0].environment_key=='staging'


def test_database_rejects_cross_organization_assignment(ctx):
    with pytest.raises(IntegrityError):
        with ctx['db'].begin() as db:
            db.add(EnvironmentAssignment(user_id='other-user',org_id='northstar',environment_key='staging'))


def test_environment_capacity_is_bounded_per_workspace(ctx):
    with ctx['db'].begin() as db:
        for i in range(19):
            db.add(WorkspaceEnvironment(org_id='northstar',key='planned-'+str(i),name='Planned environment'))
    response=create(ctx)
    assert response.status_code==429 and response.json()['error']['code']=='ENVIRONMENT_CAPACITY'


def test_schema_eight_upgrade_preserves_accounts_sessions_and_existing_contexts(ctx):
    headers,owner_id=auth(ctx)
    with ctx['db'].begin() as db:
        before=[(u.id,u.email,u.password_hash,u.role,u.active) for u in db.scalars(select(User).order_by(User.id))]
        agent=Agent(org_id='northstar',env='production',name='Existing production record',owner_id=owner_id,risk='low')
        db.add(agent);db.flush();agent_id=agent.id
    with ctx['app'].state.engine.begin() as conn:
        EnvironmentAssignment.__table__.drop(conn)
        WorkspaceEnvironment.__table__.drop(conn)
        user_organization_index.drop(conn)
        conn.execute(delete(SchemaVersion).where(SchemaVersion.version>=9))
    migrate(ctx['app'].state.engine,ctx['db'])
    migrate(ctx['app'].state.engine,ctx['db'])
    with ctx['db']() as db:
        assert before==[(u.id,u.email,u.password_hash,u.role,u.active) for u in db.scalars(select(User).order_by(User.id))]
        assert db.get(Agent,agent_id).env=='production'
        assert db.get(WorkspaceEnvironment,('northstar','production')).state=='preparing'
        assert db.scalar(select(func.count()).select_from(EnvironmentAssignment))==len(before)
        assert not db.get(EnvironmentAssignment,(owner_id,'northstar','production'))
        assert db.scalar(select(func.max(SchemaVersion.version)))==CURRENT_SCHEMA
    assert ctx['client'].get('/v1/me').status_code==200
