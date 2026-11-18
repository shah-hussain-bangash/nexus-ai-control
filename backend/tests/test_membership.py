from sqlalchemy import select,func
from conftest import auth
from nexus.db import User,SessionRecord,WorkbenchRun
from nexus.security import issue_session,password_valid
from nexus.membership import reset_local

def create(ctx,email='new-user@test.invalid',**kw):
 h,_=auth(ctx);h['Idempotency-Key']='member-provision-key-001';return ctx['client'].post('/v1/member-admin',headers=h,json={'email':email,'name':'New review member','role':'engineer','note':'Reviewed this synthetic member provisioning.','reviewed':True,**kw})
def directory(ctx):auth(ctx);return ctx['client'].get('/v1/member-admin').json()['items']
def change(ctx,member,cmd,**kw):
 h,_=auth(ctx);return ctx['client'].post('/v1/member-admin/'+member['id']+'/change',headers=h,json={'expected_revision':member['revision'],'command':cmd,'note':'Reviewed this synthetic membership change.','reviewed':True,**kw})

def test_provisioning_is_idempotent_private_and_owner_scoped(ctx):
 response=create(ctx);assert response.status_code==201,response.text;data=response.json();assert not data['password_issued'] and not data['invitation_sent']
 assert create(ctx).json()['id']==data['id'];assert create(ctx,name='Changed intent').status_code==409
 h,_=auth(ctx);assert ctx['client'].post('/v1/member-admin/provision/recover',headers=h,json={'key':'member-provision-key-001'}).json()['id']==data['id']
 assert all(r['kind']!='member_provision' for r in ctx['client'].get('/v1/workbench').json()['runs'])
 assert 'password_hash' not in data['member'] and 'oidc_subject' not in data['member']
 auth(ctx,'auditor');assert ctx['client'].get('/v1/member-admin').status_code==403
 auth(ctx,org='other');assert ctx['client'].post('/v1/member-admin/provision/recover',headers=auth(ctx,org='other')[0],json={'key':'member-provision-key-001'}).status_code==404

def test_role_change_and_offboarding_revoke_existing_sessions(ctx):
 data=create(ctx).json()['member']
 with ctx['db'].begin() as db:
  user=db.get(User,data['id']);token,_=issue_session(db,user,ctx['settings'])
 current=next(m for m in directory(ctx) if m['id']==data['id']);response=change(ctx,current,'set_role',role='approver');assert response.status_code==200,response.text
 assert response.json()['sessions_revoked']==1
 ctx['client'].cookies.set('nexus_session',token);assert ctx['client'].get('/v1/me').status_code==401
 current=next(m for m in directory(ctx) if m['id']==data['id']);disabled=change(ctx,current,'deactivate');assert disabled.json()['member']['active'] is False
 assert change(ctx,current,'activate').status_code==409
 assert change(ctx,disabled.json()['member'],'activate').json()['member']['active'] is True

def test_owners_self_targets_and_other_tenants_are_protected(ctx):
 owner=next(m for m in directory(ctx) if m['role']=='owner');assert change(ctx,owner,'deactivate').status_code==409
 other={'id':'other-user','revision':'a'*64};assert change(ctx,other,'set_role',role='security').status_code==404
 assert create(ctx,role='owner').status_code==422

def test_revision_changes_when_sessions_change(ctx):
 user=create(ctx).json()['member'];old=user['revision']
 with ctx['db'].begin() as db:issue_session(db,db.get(User,user['id']),ctx['settings'])
 assert change(ctx,user,'revoke_sessions').status_code==409
 current=next(m for m in directory(ctx) if m['id']==user['id']);assert current['revision']!=old
 assert change(ctx,current,'revoke_sessions').json()['sessions_revoked']==1

def test_sso_provisioning_requires_trusted_prebinding(ctx):
 ctx['settings'].oidc_issuer='https://idp.test.invalid/realm'
 assert create(ctx).status_code==422
 created=create(ctx,oidc_subject='trusted-subject-123');assert created.status_code==201
 assert created.json()['member']['oidc_bound']
 with ctx['db']() as db:assert db.get(User,created.json()['id']).oidc_subject=='https://idp.test.invalid/realm|trusted-subject-123'

def test_local_password_is_terminal_only_and_clears_sessions(ctx):
 user=create(ctx).json()['member']
 reset_local(ctx['db'],ctx['settings'],user['email'],'Private-test-password-123')
 with ctx['db']() as db:assert password_valid('Private-test-password-123',db.get(User,user['id']).password_hash)
 ctx['settings'].mode='pilot'
 import pytest
 with pytest.raises(ValueError):reset_local(ctx['db'],ctx['settings'],user['email'],'Another-test-password-123')

def test_self_service_sessions_never_expose_tokens_and_preserve_current(ctx):
 h,uid=auth(ctx)
 with ctx['db'].begin() as db:issue_session(db,db.get(User,uid),ctx['settings'])
 sessions=ctx['client'].get('/v1/my-sessions').json()['items'];assert len(sessions)==2 and sum(x['current'] for x in sessions)==1
 assert all(set(x)=={'handle','current','expires'} for x in sessions)
 r=ctx['client'].post('/v1/my-sessions/revoke-others',headers=h,json={'note':'Closed my other synthetic test session.'});assert r.json()=={'sessions_revoked':1,'current_preserved':True}
 assert ctx['client'].get('/v1/me').status_code==200

def test_csrf_and_unavailable_accounts_are_rejected(ctx):
 assert create(ctx,email='not-an-email').status_code==422
 h,_=auth(ctx);assert ctx['client'].post('/v1/member-admin',json={'email':'valid@test.invalid','name':'Valid member','role':'engineer','note':'No csrf present.','reviewed':True},headers={'Idempotency-Key':'member-invalid-key-001'}).status_code==403
 assert create(ctx,email='other@test.invalid').status_code==409
