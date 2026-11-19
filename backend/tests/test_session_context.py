import pytest
from sqlalchemy import select,func,delete
from conftest import auth
from nexus.db import SessionRecord,SessionRuntimeContext,SchemaVersion,User,EnvironmentAssignment,WorkspaceEnvironment,migrate
from nexus.security import digest


def context(ctx):return ctx['client'].get('/v1/session-context').json()
def headers(current):return {'X-Nexus-Context-ID':current['binding_id'],'X-Nexus-Context-Revision':str(current['revision'])}
def selection(current,**changes):
    return {'workspace_id':current['workspace_id'],'environment':current['environment'],'expected_revision':current['revision'],'expected_binding_id':current['binding_id'],**changes}


def test_current_context_is_session_owned_and_not_an_authentication_secret(ctx):
    csrf,owner=auth(ctx);current=context(ctx)
    assert current['user_id']==owner and current['workspace_id']=='northstar' and current['environment']=='staging'
    assert current['revision']==1 and not current['switching_enabled']
    assert current==ctx['client'].get('/v1/me').json()['runtime_context']
    assert 'session_id' not in current and 'csrf' not in current
    assert ctx['client'].get('/v1/agents',headers=headers(current)).status_code==200
    # Legacy clients without context headers still use their stored staging context.
    assert ctx['client'].get('/v1/agents').status_code==200
    with ctx['db']() as db:
        record=db.get(SessionRuntimeContext,digest(ctx['client'].cookies.get('nexus_session')))
        assert current['binding_id']!=record.session_id


def test_selection_is_csrf_protected_versioned_acknowledgement_only(ctx):
    csrf,_=auth(ctx);current=context(ctx);url='/v1/session-context/select'
    assert ctx['client'].post(url,json=selection(current)).status_code==403
    response=ctx['client'].post(url,headers=csrf,json=selection(current))
    assert response.status_code==200 and response.json()==current
    assert ctx['client'].post(url,headers=csrf,json=selection(current,expected_revision=2)).status_code==409
    assert ctx['client'].post(url,headers=csrf,json=selection(current,workspace_id='other')).status_code==403
    with ctx['db'].begin() as db:
        db.add(WorkspaceEnvironment(org_id='northstar',key='production',name='Production',state='preparing'))
        db.flush();db.add(EnvironmentAssignment(user_id=current['user_id'],org_id='northstar',environment_key='production'))
    assert ctx['client'].post(url,headers=csrf,json=selection(current,environment='production')).status_code==409
    assert context(ctx)==current


@pytest.mark.parametrize('extra',[
    {'X-Nexus-Context-Revision':'1'}, {'X-Nexus-Context-ID':'unknown'},
    {'X-Nexus-Context-ID':'unknown','X-Nexus-Context-Revision':'0'},
    {'X-Nexus-Context-ID':'unknown','X-Nexus-Context-Revision':'01'},
    {'X-Nexus-Context-ID':'unknown','X-Nexus-Context-Revision':'1.0'},
])
def test_incomplete_or_invalid_context_headers_are_rejected(ctx,extra):
    auth(ctx);assert ctx['client'].get('/v1/agents',headers=extra).status_code==400


def test_stale_revision_and_previous_session_binding_cannot_write(ctx):
    csrf,_=auth(ctx);old=context(ctx)
    with ctx['db'].begin() as db:
        db.get(SessionRuntimeContext,digest(ctx['client'].cookies.get('nexus_session'))).revision=2
    response=ctx['client'].post('/v1/workbench-starter',headers={**csrf,**headers(old)})
    assert response.status_code==409 and response.json()['error']['code']=='STALE_SESSION_CONTEXT'
    current=context(ctx);assert current['revision']==2
    auth(ctx)
    assert context(ctx)['binding_id']!=old['binding_id']
    assert ctx['client'].get('/v1/agents',headers=headers(current)).status_code==409


def test_duplicate_context_headers_are_rejected(ctx):
    auth(ctx);current=context(ctx)
    response=ctx['client'].get('/v1/agents',headers=[('X-Nexus-Context-ID',current['binding_id']),('X-Nexus-Context-ID',current['binding_id']),('X-Nexus-Context-Revision','1')])
    assert response.status_code==400


@pytest.mark.parametrize('change',['missing','revision','environment'])
def test_invalid_stored_selection_is_not_silently_replaced(ctx,change):
    auth(ctx);session_id=digest(ctx['client'].cookies.get('nexus_session'))
    with ctx['db'].begin() as db:
        row=db.get(SessionRuntimeContext,session_id)
        if change=='missing':db.delete(row)
        elif change=='revision':row.revision=0
        else:
            db.add(WorkspaceEnvironment(org_id='northstar',key='production',name='Production',state='preparing'));db.flush();row.environment='production'
    assert ctx['client'].get('/v1/me').status_code==401
    with ctx['db']() as db:
        row=db.get(SessionRuntimeContext,session_id)
        assert row is None if change=='missing' else row.revision==0 if change=='revision' else row.environment=='production'


def test_logout_and_member_revocation_remove_session_metadata(ctx):
    csrf,_=auth(ctx);session_id=digest(ctx['client'].cookies.get('nexus_session'))
    assert ctx['client'].post('/auth/logout',headers=csrf).status_code==200
    with ctx['db']() as db:assert db.get(SessionRuntimeContext,session_id) is None


def test_schema_nine_upgrade_preserves_credentials_sessions_and_revoked_access(ctx):
    _,owner=auth(ctx);session_id=digest(ctx['client'].cookies.get('nexus_session'))
    with ctx['db'].begin() as db:
        before_sessions=[(s.id,s.user_id,s.csrf,s.expires) for s in db.scalars(select(SessionRecord))]
        before_users=[(u.id,u.email,u.password_hash,u.active) for u in db.scalars(select(User).order_by(User.id))]
        db.execute(delete(EnvironmentAssignment).where(EnvironmentAssignment.user_id==owner))
    with ctx['app'].state.engine.begin() as connection:
        SessionRuntimeContext.__table__.drop(connection)
        connection.execute(delete(SchemaVersion).where(SchemaVersion.version==10))
    migrate(ctx['app'].state.engine,ctx['db']);migrate(ctx['app'].state.engine,ctx['db'])
    with ctx['db']() as db:
        assert before_sessions==[(s.id,s.user_id,s.csrf,s.expires) for s in db.scalars(select(SessionRecord))]
        assert before_users==[(u.id,u.email,u.password_hash,u.active) for u in db.scalars(select(User).order_by(User.id))]
        row=db.get(SessionRuntimeContext,session_id)
        assert row.environment=='staging' and row.revision==1
        assert not db.get(EnvironmentAssignment,(owner,'northstar','staging'))
        assert db.scalar(select(func.max(SchemaVersion.version)))==10
    assert ctx['client'].get('/v1/me').status_code==403
