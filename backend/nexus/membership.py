"""Owner-controlled membership lifecycle and self-service session revocation."""
import hashlib,json,re,secrets
from urllib.parse import urlsplit
from typing import Literal
from fastapi import Request,Header
from pydantic import Field,field_validator
from sqlalchemy import select,update,delete,func
from sqlalchemy.exc import IntegrityError
from .schemas import Strict
from .db import User,SessionRecord,Organization,WorkbenchRun,now
from .security import fail,digest,password_hash
from .service import canonical,audit
from .environments import assign_staging
from .runtime_context import CURRENT_ENVIRONMENT
KIND='member_provision'
def identity_issuer(settings):
 issuer=settings.oidc_issuer.rstrip('/')
 if not issuer:return ''
 try:
  parsed=urlsplit(issuer);parsed.port
  if len(issuer)>500 or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(ord(c)<33 or ord(c)==127 for c in issuer):raise ValueError()
 except (ValueError,TypeError):fail(503,'IDENTITY_ISSUER_UNAVAILABLE','The configured identity issuer is unavailable or unsupported.')
 return issuer
class Note(Strict):
 note:str=Field(min_length=5,max_length=500)
 @field_validator('note')
 @classmethod
 def visible(cls,v):
  if len(v.strip())<5:raise ValueError('Include a visible reason.')
  return v.strip()
class Provision(Note):
 email:str=Field(min_length=5,max_length=254)
 name:str=Field(min_length=2,max_length=100)
 role:Literal['engineer','approver','auditor','security']='engineer'
 oidc_subject:str=Field(default='',max_length=200)
 reviewed:Literal[True]
 @field_validator('email')
 @classmethod
 def email_address(cls,v):
  v=v.strip().lower()
  if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',v):raise ValueError('Use a valid account email.')
  return v
 @field_validator('name')
 @classmethod
 def name_value(cls,v):
  if len(v.strip())<2:raise ValueError('Use a visible name.')
  return v.strip()
 @field_validator('oidc_subject')
 @classmethod
 def trusted_subject(cls,v):
  if v!=v.strip() or any(ord(c)<32 for c in v):raise ValueError('Use an exact trusted IdP subject.')
  return v
class Change(Note):
 expected_revision:str=Field(pattern=r'^[a-f0-9]{64}$')
 command:Literal['set_role','activate','deactivate','revoke_sessions']
 role:Literal['engineer','approver','auditor','security']='engineer'
 reviewed:Literal[True]
class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')

def revision(db,user):
 sessions=db.scalars(select(SessionRecord.id).where(SessionRecord.user_id==user.id).order_by(SessionRecord.id)).all()
 return digest(canonical({'id':user.id,'org':user.org_id,'email':user.email,'name':user.name,'role':user.role,'active':user.active,'subject':user.oidc_subject,'password_revision':digest(user.password_hash),'sessions':sessions}))
def member(db,user):return {'id':user.id,'name':user.name,'email':user.email,'role':user.role,'active':bool(user.active),'oidc_bound':bool(user.oidc_subject),'revision':revision(db,user),'active_sessions':db.scalar(select(func.count()).select_from(SessionRecord).where(SessionRecord.user_id==user.id,SessionRecord.expires>now()))}
def reset_local(factory,settings,email,password):
 if settings.mode!='local':raise ValueError('Password reset is restricted to local development.')
 if not 12<=len(password)<=128:raise ValueError('Use a password of 12–128 characters.')
 with factory.begin() as db:
  user=db.scalar(select(User).where(User.email==email.strip().lower()).with_for_update())
  if not user or not user.active:raise ValueError('Active local account not found.')
  user.password_hash=password_hash(password);db.execute(delete(SessionRecord).where(SessionRecord.user_id==user.id));audit(db,user.org_id,'local-console','member.password_reset',detail={'member_id':user.id},env=CURRENT_ENVIRONMENT)

def register_membership(app,factory,settings,human):
 @app.get('/v1/member-admin')
 def listing(request:Request):
  with factory() as db:
   actor=human(request,db,False,'members');users=db.scalars(select(User).where(User.org_id==actor.org_id).order_by(User.name,User.id).limit(201)).all()
   if len(users)>200:fail(422,'MEMBER_CAPACITY','This bounded owner workspace supports up to 200 members.')
   return {'items':[member(db,u) for u in users],'mode':settings.mode,'oidc_configured':bool(settings.oidc_issuer),'oidc_issuer':identity_issuer(settings),'identity_scope':'workspace-wide','explicit_subject_required':settings.mode!='local','boundary':'Owner-controlled preprovisioning. No invitation email is sent. Owners/identity bindings are not changed by this endpoint.'}
 @app.post('/v1/member-admin/provision/recover')
 def recover(body:Recover,request:Request):
  with factory() as db:
   actor=human(request,db,True,'members');key=digest(body.key)
   rows=db.execute(select(WorkbenchRun.__table__).where(WorkbenchRun.__table__.c.org_id==actor.org_id,WorkbenchRun.__table__.c.kind==KIND,WorkbenchRun.__table__.c.author_id==actor.id)).all();old=next((r for r in rows if r.result.get('key')==key),None)
   if not old:fail(404,'PROVISION_NOT_FOUND','No provisioning receipt matches this account/key.')
   target=db.get(User,old.result['member_id'])
   if not target or target.org_id!=actor.org_id:fail(404,'PROVISION_NOT_FOUND','Provisioned account is unavailable.')
   return {'id':target.id,'status':'provisioned','member':member(db,target),'password_issued':False,'invitation_sent':False}
 @app.post('/v1/member-admin',status_code=201)
 def provision(body:Provision,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
  if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character provisioning key.')
  try:
   with factory.begin() as db:
    actor=human(request,db,True,'members');db.execute(update(Organization).where(Organization.id==actor.org_id).values(name=Organization.name))
    fingerprint=digest(canonical(body.model_dump()));key=digest(idempotency_key);receipts=db.execute(select(WorkbenchRun.__table__).where(WorkbenchRun.__table__.c.org_id==actor.org_id,WorkbenchRun.__table__.c.kind==KIND)).all();old=next((r for r in receipts if r.author_id==actor.id and r.result.get('key')==key),None)
    if old:
     if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different member request.')
     target=db.get(User,old.result['member_id']);return {'id':target.id,'status':'provisioned','member':member(db,target),'password_issued':False,'invitation_sent':False}
    if len(receipts)>=1000 or db.scalar(select(func.count()).select_from(User).where(User.org_id==actor.org_id))>=200:fail(429,'MEMBER_CAPACITY','Member or provisioning-receipt capacity was reached.')
    if db.scalar(select(User.id).where(User.email==body.email)):fail(409,'ACCOUNT_UNAVAILABLE','This account cannot be provisioned. Review the identifier with your administrator.')
    if settings.oidc_issuer and not body.oidc_subject:fail(422,'OIDC_SUBJECT_REQUIRED','Pre-bind the exact trusted IdP subject before provisioning an SSO member.')
    if body.oidc_subject and not settings.oidc_issuer:fail(422,'OIDC_NOT_CONFIGURED','Configure the trusted issuer before provisioning an IdP binding.')
    target=User(org_id=actor.org_id,email=body.email,name=body.name,role=body.role,password_hash=password_hash(secrets.token_urlsafe(48)),oidc_subject=settings.oidc_issuer.rstrip('/')+'|'+body.oidc_subject if body.oidc_subject else None)
    db.add(target);db.flush();assign_staging(db,target);db.add(WorkbenchRun(org_id=actor.org_id,kind=KIND,status='completed',duration_ms=0,author_id=actor.id,result={'key':key,'fingerprint':fingerprint,'member_id':target.id}))
    audit(db,actor.org_id,actor.id,'member.provisioned',detail={'member_id':target.id,'role':target.role,'oidc_bound':bool(target.oidc_subject),'note':body.note})
    return {'id':target.id,'status':'provisioned','member':member(db,target),'password_issued':False,'invitation_sent':False}
  except IntegrityError:fail(409,'ACCOUNT_UNAVAILABLE','This account cannot be provisioned. Refresh the member directory.')
 @app.post('/v1/member-admin/{id}/change')
 def change(id:str,body:Change,request:Request):
  with factory.begin() as db:
   actor=human(request,db,True,'members');db.execute(update(Organization).where(Organization.id==actor.org_id).values(name=Organization.name));target=db.scalar(select(User).where(User.id==id,User.org_id==actor.org_id).with_for_update())
   if not target:fail(404,'MEMBER_NOT_FOUND','Member is not in this workspace.')
   if target.id==actor.id or target.role=='owner':fail(409,'OWNER_PROTECTED','Self/owner access changes require a separate reviewed ownership procedure.')
   if revision(db,target)!=body.expected_revision:fail(409,'STALE_VERSION','Member or session state changed. Refresh before confirming.')
   if body.command=='set_role':target.role=body.role
   elif body.command=='activate':
    if settings.mode!='local' and not target.oidc_subject:fail(422,'OIDC_SUBJECT_REQUIRED','Bind the trusted IdP identity before activation.')
    target.active=1
   elif body.command=='deactivate':target.active=0
   result=db.execute(delete(SessionRecord).where(SessionRecord.user_id==target.id));db.flush()
   audit(db,actor.org_id,actor.id,'member.'+body.command,detail={'member_id':target.id,'role':target.role,'active':bool(target.active),'sessions_revoked':result.rowcount,'note':body.note})
   return {'member':member(db,target),'sessions_revoked':result.rowcount}
 @app.get('/v1/my-sessions')
 def sessions(request:Request):
  with factory() as db:
   user=human(request,db);current=digest(request.cookies.get('nexus_session',''));rows=db.scalars(select(SessionRecord).where(SessionRecord.user_id==user.id,SessionRecord.expires>now()).order_by(SessionRecord.expires.desc()).limit(50)).all()
   return {'items':[{'handle':digest('session-handle:'+r.id)[:32],'current':r.id==current,'expires':r.expires} for r in rows],'boundary':'Only active session handles and expiry are stored; device/IP/geolocation details are not available.'}
 @app.post('/v1/my-sessions/revoke-others')
 def revoke_others(body:Note,request:Request):
  with factory.begin() as db:
   user=human(request,db,True);current=digest(request.cookies.get('nexus_session',''));result=db.execute(delete(SessionRecord).where(SessionRecord.user_id==user.id,SessionRecord.id!=current));audit(db,user.org_id,user.id,'session.others_revoked',detail={'count':result.rowcount,'note':body.note});return {'sessions_revoked':result.rowcount,'current_preserved':True}
