"""Reviewed binding changes in disposable accounts; no real IdP or credentials."""
import pytest
import httpx
from sqlalchemy import select,func,update
from conftest import auth
from test_membership import create,directory,change
from test_oidc_security import provider,begin,finish
from nexus.db import User,SessionRecord,WorkbenchRun,EnvironmentAssignment,Audit
from nexus.security import issue_session
from nexus.environments import assign_staging

ISSUER='https://identity.test.invalid/realm'
SUBJECT='synthetic-private-subject-7654'
NOTE='Reviewed synthetic account identity binding.'


def target(ctx):
    created=create(ctx).json()['member'];ctx['settings'].oidc_issuer=ISSUER;return created


def bind(ctx,member,command='bind',subject=SUBJECT,key='identity-binding-intent-0001',role='owner',**override):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    body={'expected_revision':member['revision'],'expected_issuer':ctx['settings'].oidc_issuer.rstrip('/'),'command':command,'subject':subject,'note':NOTE,'reviewed':True,**override}
    return ctx['client'].post('/v1/member-identity/'+member['id'],headers=headers,json=body)


def current(ctx,id):return next(row for row in directory(ctx) if row['id']==id)


def test_binding_deactivates_revokes_sessions_and_preserves_role_assignments(ctx):
    user=target(ctx)
    with ctx['db'].begin() as db:
        issue_session(db,db.get(User,user['id']),ctx['settings']);issue_session(db,db.get(User,user['id']),ctx['settings'])
        assignments=set(db.execute(select(EnvironmentAssignment.user_id,EnvironmentAssignment.environment_key)).all())
    user=current(ctx,user['id']);response=bind(ctx,user);assert response.status_code==201,response.text
    result=response.json();assert result['sessions_revoked']==2 and not result['active_after_change'] and result['oidc_bound_after_change']
    with ctx['db']() as db:
        saved=db.get(User,user['id']);assert saved.oidc_subject==ISSUER+'|'+SUBJECT and saved.active==0 and saved.role==user['role']
        assert db.scalar(select(func.count()).select_from(SessionRecord).where(SessionRecord.user_id==user['id']))==0
        assert assignments==set(db.execute(select(EnvironmentAssignment.user_id,EnvironmentAssignment.environment_key)).all())
        assert SUBJECT not in str([row.detail for row in db.scalars(select(Audit).where(Audit.event=='member.identity_changed'))])
    assert SUBJECT not in response.text and SUBJECT not in str(current(ctx,user['id']))
    assert result['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])
    activated=change(ctx,current(ctx,user['id']),'activate');assert activated.status_code==200 and activated.json()['member']['active']


def test_replay_and_recovery_do_not_deactivate_a_later_reactivated_account(ctx):
    user=target(ctx);first=bind(ctx,user).json()
    assert change(ctx,current(ctx,user['id']),'activate').status_code==200
    assert bind(ctx,user).json()['id']==first['id']
    headers,_=auth(ctx)
    recovered=ctx['client'].post('/v1/member-identity/recover',headers=headers,json={'key':'identity-binding-intent-0001'}).json()
    assert recovered==first and current(ctx,user['id'])['active']
    assert bind(ctx,user,subject='changed-subject').status_code==409


def test_workspace_receipt_survives_environment_context_without_reapplying(ctx):
    user=target(ctx);first=bind(ctx,user).json()
    with ctx['db'].begin() as db:
        db.execute(update(WorkbenchRun.__table__).where(WorkbenchRun.__table__.c.id==first['id']).values(env='development'))
    assert change(ctx,current(ctx,user['id']),'activate').status_code==200
    assert bind(ctx,user).json()['id']==first['id']
    assert current(ctx,user['id'])['active']


def test_clearing_binding_leaves_member_inactive_and_pilot_activation_requires_binding(ctx):
    user=target(ctx);bind(ctx,user)
    result=bind(ctx,current(ctx,user['id']),command='clear',subject='',key='identity-binding-clear-0001');assert result.status_code==201,result.text
    assert not result.json()['oidc_bound_after_change']
    ctx['settings'].mode='pilot'
    assert change(ctx,current(ctx,user['id']),'activate').status_code==422
    with ctx['db']() as db:assert db.get(User,user['id']).oidc_subject is None and db.get(User,user['id']).active==0


def test_owner_self_foreign_targets_and_other_receipt_owners_are_protected(ctx):
    user=target(ctx);first=bind(ctx,user).json()
    owner=next(row for row in directory(ctx) if row['role']=='owner')
    assert bind(ctx,owner,key='identity-owner-protected').status_code==409
    assert bind(ctx,{'id':'other-user','revision':'a'*64},key='identity-foreign-target').status_code==404
    assert bind(ctx,user,role='auditor',key='identity-forbidden-role').status_code==403
    headers,_=auth(ctx,org='other')
    assert ctx['client'].post('/v1/member-identity/recover',headers=headers,json={'key':'identity-binding-intent-0001'}).status_code==404
    assert ctx['client'].get('/v1/member-admin',headers={'X-Nexus-Workspace':'northstar'}).status_code==403


def test_duplicate_identity_returns_generic_error_without_changing_target(ctx):
    user=target(ctx)
    with ctx['db'].begin() as db:db.get(User,'other-user').oidc_subject=ISSUER+'|'+SUBJECT
    result=bind(ctx,user);assert result.status_code==409 and result.json()['error']['code']=='IDENTITY_UNAVAILABLE'
    assert 'other-user' not in result.text and SUBJECT not in result.text
    with ctx['db']() as db:assert db.get(User,user['id']).active==1 and db.get(User,user['id']).oidc_subject is None


def test_stale_sessions_and_issuer_changes_block_without_mutation(ctx):
    user=target(ctx)
    with ctx['db'].begin() as db:issue_session(db,db.get(User,user['id']),ctx['settings'])
    assert bind(ctx,user).status_code==409
    user=current(ctx,user['id'])
    result=bind(ctx,user,expected_issuer='https://previous.test.invalid');assert result.status_code==409 and result.json()['error']['code']=='IDENTITY_ISSUER_CHANGED'
    with ctx['db']() as db:assert db.get(User,user['id']).active==1 and db.get(User,user['id']).oidc_subject is None


@pytest.mark.parametrize('override',[{'subject':''},{'subject':' padded '},{'subject':'bad\x00subject'},{'subject':'a'*201},{'reviewed':False},{'reviewed':1},{'note':' '*10},{'command':'clear','subject':'unexpected'}])
def test_invalid_identity_review_is_rejected(ctx,override):
    user=target(ctx);assert bind(ctx,user,**override).status_code==422


def test_clear_allowed_without_issuer_but_binding_requires_configured_issuer(ctx):
    user=target(ctx);ctx['settings'].oidc_issuer=''
    assert bind(ctx,user).status_code==422
    assert bind(ctx,user,command='clear',subject='',key='identity-clear-without-issuer').status_code==201


def test_misconfigured_issuer_credentials_are_never_returned(ctx):
    user=target(ctx);ctx['settings'].oidc_issuer='https://private:DO-NOT-EXPOSE@identity.invalid'
    response=ctx['client'].get('/v1/member-admin');assert response.status_code==503 and 'DO-NOT-EXPOSE' not in response.text
    response=bind(ctx,user);assert response.status_code==503 and 'DO-NOT-EXPOSE' not in response.text


def test_writes_require_csrf_and_current_environment_access(ctx):
    user=target(ctx);headers,_=auth(ctx)
    body={'expected_revision':user['revision'],'expected_issuer':ISSUER,'command':'bind','subject':SUBJECT,'note':NOTE,'reviewed':True}
    assert ctx['client'].post('/v1/member-identity/'+user['id'],headers={'Idempotency-Key':'identity-no-csrf-0001'},json=body).status_code==403
    assert ctx['client'].post('/v1/member-identity/'+user['id'],headers=headers,json=body).status_code==422
    assert ctx['client'].post('/v1/member-identity/recover',json={'key':'identity-binding-intent-0001'}).status_code==403
    from test_runtime_context import revoke
    headers,owner_id=auth(ctx);headers['Idempotency-Key']='identity-revoked-environment';revoke(ctx,owner_id)
    assert ctx['client'].post('/v1/member-identity/'+user['id'],headers=headers,json=body).status_code==403


def test_pilot_oidc_denies_unbound_active_account_without_email_autolinking(ctx,provider):
    ctx['settings'].mode='pilot'
    ctx['client'].base_url=httpx.URL('https://testserver')
    query=begin(ctx,provider);response=finish(ctx,query)
    assert response.status_code==403
    with ctx['db']() as db:
        owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        assert owner.oidc_subject is None


def test_pilot_oidc_accepts_exact_prebound_identity(ctx,provider):
    ctx['settings'].mode='pilot'
    ctx['client'].base_url=httpx.URL('https://testserver')
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        owner.oidc_subject=ctx['settings'].oidc_issuer+'|owner-idp-subject'
    query=begin(ctx,provider);assert finish(ctx,query).status_code==307


def test_reviewed_member_binding_and_separate_activation_support_mock_pilot_signin(ctx,provider):
    user=create(ctx,oidc_subject='previous-trusted-subject').json()['member']
    assert bind(ctx,user).status_code==201
    assert change(ctx,current(ctx,user['id']),'activate').status_code==200
    ctx['settings'].mode='pilot';ctx['client'].base_url=httpx.URL('https://testserver')
    provider['claims']={'email':user['email'],'sub':SUBJECT}
    query=begin(ctx,provider);assert finish(ctx,query).status_code==307
    me=ctx['client'].get('/v1/me');assert me.status_code==200,me.text
    assert me.json()['user']['id']==user['id'] and me.json()['user']['role']=='engineer'
    assert ctx['client'].get('/v1/member-admin').status_code==403


def test_another_owner_cannot_recover_the_original_actors_intent(ctx):
    user=target(ctx);bind(ctx,user)
    with ctx['db'].begin() as db:
        owner=User(org_id='northstar',email='second-owner@synthetic.invalid',name='Second synthetic owner',role='owner',password_hash='!')
        db.add(owner);db.flush();assign_staging(db,owner);token,csrf=issue_session(db,owner,ctx['settings'])
    ctx['client'].cookies.set('nexus_session',token)
    response=ctx['client'].post('/v1/member-identity/recover',headers={'X-CSRF-Token':csrf},json={'key':'identity-binding-intent-0001'})
    assert response.status_code==404


def test_receipt_capacity_preserves_active_target_and_existing_history(ctx):
    user=target(ctx);_,actor=auth(ctx)
    with ctx['db'].begin() as db:
        for i in range(1000):db.add(WorkbenchRun(org_id='northstar',env='staging',author_id=actor,kind='member_identity_binding',status='completed',duration_ms=0,result={'key':'synthetic-'+str(i)}))
    assert bind(ctx,user).status_code==429
    with ctx['db']() as db:
        assert db.get(User,user['id']).active==1 and db.get(User,user['id']).oidc_subject is None
        assert db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind=='member_identity_binding'))==1000
