from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, func
from conftest import auth, identifiers
from nexus.db import User, EnvironmentAssignment, WorkspaceEnvironment, SessionRecord, Audit, Action
from nexus.runtime_context import environment_user_allowed
from nexus.worker import run_once

PATH='/v1/workspace-environments/{}/assignments'


def snapshot(ctx,key='staging'):
    auth(ctx)
    response=ctx['client'].get(PATH.format(key))
    assert response.status_code==200,response.text
    return response.json()


def change(ctx,command='revoke',key='staging',role='approver',**changes):
    headers,_=auth(ctx)
    data=ctx['client'].get(PATH.format(key)).json()
    target=next(row for row in data['items']+data['candidates'] if row['role']==role)
    body={'user_id':target['id'],'command':command,'expected_version':data['environment']['version'],
          'expected_member_revision':target['revision'],'note':'Reviewed synthetic membership change.','reviewed':True,**changes}
    return ctx['client'].post(PATH.format(key)+'/control',headers=headers,json=body)


def test_revoke_and_grant_preserve_account_and_require_fresh_login(ctx):
    _,target_id=auth(ctx,'approver')
    token=ctx['client'].cookies.get('nexus_session')
    with ctx['db']() as db:
        user=db.get(User,target_id);before=(user.email,user.password_hash,user.role,user.active)
    revoked=change(ctx)
    assert revoked.status_code==200,revoked.text
    assert revoked.json()['status']=='removed' and revoked.json()['sessions_revoked']==1
    with ctx['db']() as db:
        user=db.get(User,target_id)
        assert (user.email,user.password_hash,user.role,user.active)==before
        assert not environment_user_allowed(db,target_id,'northstar')
    with TestClient(ctx['app']) as old:
        old.cookies.set('nexus_session',token)
        assert old.get('/v1/me').status_code==401
    assert ctx['client'].post('/auth/local/login',json={'email':before[0],'password':'Test-Only-Password-123!'}).status_code==403
    granted=change(ctx,'grant')
    assert granted.status_code==200 and granted.json()['status']=='assigned'
    with TestClient(ctx['app']) as old:
        old.cookies.set('nexus_session',token)
        assert old.get('/v1/me').status_code==401
    assert ctx['client'].post('/auth/local/login',json={'email':before[0],'password':'Test-Only-Password-123!'}).status_code==200
    with ctx['db']() as db:
        events=db.scalars(select(Audit).where(Audit.event.like('environment.assignment_%')).order_by(Audit.created,Audit.id)).all()
        assert [row.event for row in events]==['environment.assignment_revoke','environment.assignment_grant']
        assert all(row.detail['member_id']==target_id and row.detail['note']=='Reviewed synthetic membership change.' for row in events)


def test_preparing_membership_never_enables_runtime_and_archived_is_read_only(ctx):
    headers,_=auth(ctx)
    assert ctx['client'].post('/v1/workspace-environments',headers=headers,json={'key':'production','name':'Production','note':'Prepare synthetic environment.'}).status_code==201
    result=change(ctx,'grant','production')
    assert result.status_code==200 and result.json()['switching_enabled'] is False
    data=snapshot(ctx,'production')
    assert len(data['items'])==1 and data['environment']['state']=='preparing'
    with ctx['db']() as db:
        assert not environment_user_allowed(db,result.json()['member_id'],'northstar','production')
    headers,_=auth(ctx)
    archived=ctx['client'].post('/v1/workspace-environments/production/control',headers=headers,json={
        'command':'archive','expected_version':data['environment']['version'],'note':'Pause synthetic environment.'})
    assert archived.status_code==200
    assert snapshot(ctx,'production')['editing_enabled'] is False
    blocked=change(ctx,'revoke','production')
    assert blocked.status_code==409 and blocked.json()['error']['code']=='ENVIRONMENT_STATE'


@pytest.mark.parametrize('role',['engineer','approver','auditor','security'])
def test_only_owners_can_change_assignments(ctx,role):
    with ctx['db'].begin() as db:
        target=db.scalar(select(User).where(User.email=='reviewer@nexus.local'));target.role=role
    data=snapshot(ctx);target=next(r for r in data['items'] if r['role']==role)
    headers,_=auth(ctx,role)
    response=ctx['client'].post(PATH.format('staging')+'/control',headers=headers,json={
        'user_id':target['id'],'command':'revoke','expected_version':1,'expected_member_revision':target['revision'],
        'note':'Unauthorized synthetic request.','reviewed':True})
    assert response.status_code==403


def test_csrf_workspace_scope_and_owner_protection(ctx):
    data=snapshot(ctx);owner=next(r for r in data['items'] if r['role']=='owner')
    body={'user_id':owner['id'],'command':'revoke','expected_version':1,'expected_member_revision':owner['revision'],
          'note':'Protected synthetic request.','reviewed':True}
    assert ctx['client'].post(PATH.format('staging')+'/control',json=body).status_code==403
    response=change(ctx,role='owner')
    assert response.status_code==409 and response.json()['error']['code']=='OWNER_PROTECTED'
    headers,_=auth(ctx,org='other')
    assert ctx['client'].post(PATH.format('staging')+'/control',headers=headers,json=body).status_code==404
    assert ctx['client'].post(PATH.format('missing')+'/control',headers=headers,json=body).status_code==404
    assert ctx['client'].get(PATH.format('staging')).json()['candidates']==[]


@pytest.mark.parametrize('changes',[{'reviewed':False},{'reviewed':None},{'expected_version':True},{'expected_member_revision':'bad'},
    {'note':'    '},{'note':'review\nagain'},{'note':'x'*501},{'command':'activate'},{'org_id':'other'}])
def test_unreviewed_or_malformed_changes_are_rejected(ctx,changes):
    assert change(ctx,**changes).status_code==422
    assert snapshot(ctx)['environment']['version']==1


def test_assignment_version_and_member_revision_both_fence_stale_confirmations(ctx):
    headers,_=auth(ctx)
    data=ctx['client'].get(PATH.format('staging')).json()
    target=next(r for r in data['items'] if r['role']=='approver')
    body={'user_id':target['id'],'command':'revoke','expected_version':1,'expected_member_revision':target['revision'],
          'note':'Reviewed synthetic request.','reviewed':True}
    with ctx['db'].begin() as db:db.get(User,target['id']).role='engineer'
    response=ctx['client'].post(PATH.format('staging')+'/control',headers=headers,json=body)
    assert response.status_code==409 and response.json()['error']['code']=='STALE_VERSION'
    fresh=ctx['client'].get(PATH.format('staging')).json()
    body['expected_member_revision']=next(r for r in fresh['items'] if r['id']==target['id'])['revision']
    assert ctx['client'].post(PATH.format('staging')+'/control',headers=headers,json=body).status_code==200
    replay=ctx['client'].post(PATH.format('staging')+'/control',headers=headers,json=body)
    assert replay.status_code==409 and replay.json()['error']['code']=='STALE_VERSION'
    assert ctx['client'].get(PATH.format('staging')).json()['environment']['version']==2


def test_duplicate_grants_missing_revocations_and_inactive_members_are_rejected(ctx):
    assert change(ctx,'grant').json()['error']['code']=='ASSIGNMENT_EXISTS'
    removed=change(ctx)
    assert removed.status_code==200
    data=snapshot(ctx);target=next(r for r in data['candidates'] if r['role']=='approver')
    assert change(ctx).json()['error']['code']=='ASSIGNMENT_MISSING'
    with ctx['db'].begin() as db:db.get(User,target['id']).active=0
    assert all(r['id']!=target['id'] for r in snapshot(ctx)['candidates'])
    headers,_=auth(ctx)
    from nexus.membership import revision
    with ctx['db']() as db:rev=revision(db,db.get(User,target['id']))
    response=ctx['client'].post(PATH.format('staging')+'/control',headers=headers,json={
        'user_id':target['id'],'command':'grant','expected_version':2,'expected_member_revision':rev,
        'note':'Inactive synthetic request.','reviewed':True})
    assert response.status_code==409 and response.json()['error']['code']=='MEMBER_INACTIVE'


def test_revocation_blocks_queued_work_before_a_business_effect(ctx):
    with ctx['db'].begin() as db:
        member=db.scalar(select(User).where(User.email=='reviewer@nexus.local'));member.role='engineer'
    headers,target_id=auth(ctx,'engineer');headers['Idempotency-Key']='membership-worker-revocation'
    agent_id,tool_id=identifiers(ctx)
    response=ctx['client'].post('/v1/console/actions',headers=headers,json={'agent_id':agent_id,'tool_id':tool_id,'request':{
        'action':'purchase:create','resource':'purchase_requests','arguments':{'supplier_id':'SUP-DEMO-104',
        'amount':'3000.00','currency':'USD','purpose':'Synthetic revocation check'}}})
    assert response.status_code==202,response.text
    assert change(ctx,role='engineer').status_code==200
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    assert ctx['connector'].count()==0
    with ctx['db']() as db:
        row=db.get(Action,response.json()['id'])
        assert row.status=='blocked' and row.reason=='DISPATCH_ENVIRONMENT_ACCESS_CHANGED'


def test_duplicate_member_names_are_distinguished_by_account_email(ctx):
    with ctx['db'].begin() as db:
        users=db.scalars(select(User).where(User.org_id=='northstar',User.role!='owner')).all()
        for user in users:user.name='Same Name'
    rows=[row for row in snapshot(ctx)['items'] if row['name']=='Same Name']
    assert len(rows)==2 and len({row['email'] for row in rows})==2
    assert change(ctx).status_code==200
    candidates=snapshot(ctx)['candidates']
    assert len(candidates)==1 and candidates[0]['email']=='reviewer@nexus.local'
