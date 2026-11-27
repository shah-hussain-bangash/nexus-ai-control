"""Owner-reviewed workspace-wide identity changes; never activates an account."""
import re
from typing import Literal
from fastapi import Request,Header
from pydantic import Field,field_validator,model_validator
from sqlalchemy import select,update,delete
from sqlalchemy.exc import IntegrityError
from .db import User,Organization,WorkbenchRun,SessionRecord
from .schemas import Strict
from .security import fail,digest
from .service import canonical,audit
from .membership import revision,identity_issuer
from .runtime_context import runtime_environment

KIND='member_identity_binding'
BOUNDARY='Workspace-wide owner-reviewed identity binding only. The target is deactivated and its sessions revoked; activation is a separate reviewed operation. No identity-provider lookup, MFA verification, invitation or provider-side offboarding is performed. Owner and self identity changes remain protected.'


class BindingInput(Strict):
    expected_revision:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_issuer:str=Field(max_length=500)
    command:Literal['bind','clear']
    subject:str=Field(default='',max_length=200)
    note:str=Field(min_length=10,max_length=500)
    reviewed:bool=Field(strict=True)
    @field_validator('subject','note')
    @classmethod
    def visible(cls,value):
        if value!=value.strip() or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Use exact visible text without surrounding whitespace or control characters.')
        return value
    @model_validator(mode='after')
    def explicit(self):
        if not self.reviewed or len(self.note.strip())<10:raise ValueError('Explicitly review this identity change and provide a visible reason.')
        if self.command=='bind' and not self.subject or self.command=='clear' and self.subject:raise ValueError('Binding requires a subject; clearing requires an empty subject.')
        return self


class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


def receipts(db,user):
    # Identities and their administrative receipts span environments. Only this
    # fixed operation kind is read through Core; explicit organization/actor
    # predicates preserve the workspace-wide owner boundary.
    table=WorkbenchRun.__table__
    return select(table).where(table.c.org_id==user.org_id,table.c.kind==KIND,table.c.author_id==user.id)


def find(db,user,key):
    return next((row for row in db.execute(receipts(db,user)) if row.result.get('key')==digest(key)),None)


def receipt(row):
    return {'id':row.id,'status':'identity_updated','created':row.created,
        **{key:row.result[key] for key in ('member_id','command','sessions_revoked','active_after_change','oidc_bound_after_change','binding_fingerprint')},'boundary':BOUNDARY}


def register_identity_bindings(app,factory,settings,human):
    @app.post('/v1/member-identity/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            actor=human(request,db,True,'members');old=find(db,actor,body.key)
            if not old:fail(404,'IDENTITY_RECEIPT_NOT_FOUND','No identity change matches this account and workspace.')
            return receipt(old)

    @app.post('/v1/member-identity/{id}',status_code=201)
    def change(id:str,body:BindingInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        fingerprint=digest(canonical({'member_id':id,**body.model_dump()}))
        try:
            with factory.begin() as db:
                actor=human(request,db,True,'members');db.execute(update(Organization).where(Organization.id==actor.org_id).values(name=Organization.name))
                old=find(db,actor,idempotency_key)
                if old:
                    if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different identity change.')
                    return receipt(old)
                target=db.scalar(select(User).where(User.id==id,User.org_id==actor.org_id).with_for_update())
                if not target:fail(404,'MEMBER_NOT_FOUND','Member is not in this workspace.')
                if target.id==actor.id or target.role=='owner':fail(409,'OWNER_PROTECTED','Self and owner identity changes require a separate ownership procedure.')
                if revision(db,target)!=body.expected_revision:fail(409,'STALE_VERSION','Member or session state changed. Reload and review again.')
                issuer=identity_issuer(settings)
                if body.expected_issuer!=issuer:fail(409,'IDENTITY_ISSUER_CHANGED','The configured issuer changed. Reload before reviewing this binding.')
                if body.command=='bind' and not issuer:fail(422,'OIDC_NOT_CONFIGURED','Configure a trusted issuer before binding an identity.')
                subject=issuer+'|'+body.subject if body.command=='bind' else None
                if subject and db.scalar(select(User.id).where(User.oidc_subject==subject,User.id!=target.id)):
                    fail(409,'IDENTITY_UNAVAILABLE','This identity cannot be assigned. Review it privately with the identity administrator.')
                if len(db.execute(receipts(db,actor)).all())>=1000:fail(429,'IDENTITY_RECEIPT_CAPACITY','This account reached its bounded identity-change history. Existing receipts were preserved.')
                target.oidc_subject=subject;target.active=0
                revoked=db.execute(delete(SessionRecord).where(SessionRecord.user_id==target.id)).rowcount
                result={'key':digest(idempotency_key),'fingerprint':fingerprint,'member_id':target.id,'command':body.command,
                    'sessions_revoked':revoked,'active_after_change':False,'oidc_bound_after_change':bool(subject),'binding_fingerprint':digest(subject) if subject else None}
                row=WorkbenchRun(org_id=actor.org_id,env=runtime_environment(db,actor.org_id),author_id=actor.id,kind=KIND,status='completed',duration_ms=0,result=result)
                db.add(row);db.flush()
                audit(db,actor.org_id,actor.id,'member.identity_changed',detail={'member_id':target.id,'command':body.command,'receipt_id':row.id,
                    'binding_fingerprint':result['binding_fingerprint'],'sessions_revoked':revoked,'active_after_change':False,'note':body.note})
                return receipt(row)
        except IntegrityError:fail(409,'IDENTITY_UNAVAILABLE','This identity cannot be assigned. Reload and review it privately with the administrator.')
