"""Opt-in authenticated metadata snapshots. No automatic key provisioning."""
import base64
import re
from fastapi import Request, Header, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import select, update, func
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .audit_signature import FORMAT,DOMAIN,MAX_BYTES,BOUNDARY,canonical,key_id,read_file,verify
from .db import WorkbenchRun,Audit,Organization,now,uid
from .schemas import Strict
from .runtime_context import runtime_environment
from .security import digest,fail
from .service import audit

KIND='signed_audit_metadata'


class SnapshotInput(Strict):
    limit:int=Field(default=200,strict=True,ge=1,le=1000)
    expected_key_id:str=Field(pattern=r'^[0-9a-f]{64}$')
    note:str=Field(min_length=10,max_length=500)
    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<10 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Use a visible 10–500 character note.')
        return value.strip()


class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


def signing_key(settings):
    if not settings.audit_signing_key_file:fail(409,'AUDIT_SIGNING_DISABLED','An operator must configure a dedicated audit signing key first.')
    try:
        key=serialization.load_pem_private_key(read_file(settings.audit_signing_key_file,4096),password=None)
        if not isinstance(key,Ed25519PrivateKey):raise ValueError()
        return key
    except (OSError,ValueError,TypeError,UnsupportedAlgorithm):fail(503,'AUDIT_SIGNING_UNAVAILABLE','The configured audit signing key is unavailable or unsupported.')


def scoped_rows(db,user):
    return select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.author_id==user.id,WorkbenchRun.kind==KIND)


def receipt(row):
    if row.status=='purged':
        return {'id':row.id,'status':'purged','created':row.created,'expires':row.result['expires'],**row.result['metadata'],
            'purged_at':row.result['purged_at'],'retention_plan_id':row.result['retention_plan_id'],'boundary':'Snapshot payload was removed by explicit owner retention. Original intent receipt is preserved; retrying never creates replacement evidence.'}
    envelope=row.result['envelope'];payload=envelope['payload']
    return {'id':row.id,'status':row.status,'created':row.created,'expires':row.result['expires'],'key_id':envelope['key_id'],
        'records':len(payload['records']),'truncated':payload['truncated'],'boundary':BOUNDARY}


def register_signed_audit(app,factory,settings,human):
    @app.get('/v1/signed-audit-evidence')
    def overview(request:Request):
        with factory() as db:
            user=human(request,db,False,'export')
            info={'enabled':bool(settings.audit_signing_key_file),'available':False,'key_id':None,'public_key_pem':None}
            if info['enabled']:
                try:
                    key=signing_key(settings).public_key();info.update(available=True,key_id=key_id(key),public_key_pem=key.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii'))
                except HTTPException:pass
            history=db.scalars(scoped_rows(db,user).order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).limit(20)).all()
            return {**info,'items':[receipt(row) for row in history],'boundary':BOUNDARY}

    @app.post('/v1/signed-audit-evidence/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'export');row=next((row for row in db.scalars(scoped_rows(db,user)) if row.result.get('key')==digest(body.key)),None)
            if not row:fail(404,'AUDIT_SNAPSHOT_NOT_FOUND','No snapshot matches this account, environment and intent.')
            return receipt(row)

    @app.get('/v1/signed-audit-evidence/{id}')
    def download(id:str,request:Request):
        with factory() as db:
            user=human(request,db,False,'export');row=db.scalar(scoped_rows(db,user).where(WorkbenchRun.id==id))
            if row and row.status=='purged':fail(410,'AUDIT_SNAPSHOT_PURGED','This signed snapshot payload was removed by an explicit owner retention operation.')
            if not row or row.result['expires']<=now():fail(404,'AUDIT_SNAPSHOT_NOT_FOUND','The snapshot is unavailable or expired.')
            envelope=row.result['envelope'];payload=envelope.get('payload',{})
            if payload.get('workspace_id')!=user.org_id or payload.get('environment')!=runtime_environment(db,user.org_id) or payload.get('id')!=row.id:
                fail(409,'EXPORT_SCOPE_CHANGED','Saved snapshot scope does not match the current environment.')
            return envelope

    @app.post('/v1/signed-audit-evidence',status_code=201)
    def create(body:SnapshotInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        fingerprint=digest(canonical(body.model_dump()).decode('ascii'))
        with factory.begin() as db:
            user=human(request,db,True,'export');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            previous=next((row for row in db.scalars(scoped_rows(db,user)) if row.result.get('key')==digest(idempotency_key)),None)
            if previous:
                if previous.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This intent belongs to a different audit snapshot.')
                return receipt(previous)
            key=signing_key(settings);public=key.public_key();identity=key_id(public)
            if identity!=body.expected_key_id:fail(409,'AUDIT_SIGNING_KEY_CHANGED','Reload the configured signing identity before creating evidence.')
            env=runtime_environment(db,user.org_id)
            inventory=select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==env,WorkbenchRun.kind==KIND)
            if db.scalar(inventory.where(WorkbenchRun.status!='purged'))>=100:
                fail(429,'AUDIT_SNAPSHOT_CAPACITY','Snapshot storage reached its bounded capacity. Existing evidence was preserved.')
            if db.scalar(inventory)>=5000:fail(429,'AUDIT_SNAPSHOT_RECEIPT_CAPACITY','Lifetime snapshot receipt capacity reached. Existing tombstones and evidence were preserved.')
            timestamp=now();found=db.scalars(select(Audit).where(Audit.org_id==user.org_id,Audit.env==env,Audit.created<=timestamp).order_by(Audit.created.desc(),Audit.id.desc()).limit(body.limit+1)).all()
            records=[{**{name:getattr(row,name) for name in ('id','event','actor','action_id','trace_id')},'created_at_us':int(row.created*1000000)} for row in reversed(found[:body.limit])]
            records.sort(key=lambda row:(row['created_at_us'],row['id']))
            identifier=uid();payload={'id':identifier,'workspace_id':user.org_id,'environment':env,'created_at_us':int(timestamp*1000000),
                'selection':'latest_audit_metadata','limit':body.limit,'truncated':len(found)>body.limit,'records':records,'note':body.note}
            envelope={'format':FORMAT,'algorithm':'Ed25519','key_id':identity,'payload':payload,'signature':base64.b64encode(key.sign(DOMAIN+canonical(payload))).decode('ascii')}
            try:verify(canonical(envelope),public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo),user.org_id,env)
            except (ValueError,TypeError,OverflowError):fail(409,'AUDIT_SNAPSHOT_UNSUPPORTED','Selected audit metadata exceeds the supported format or size. Choose a smaller limit.')
            row=WorkbenchRun(id=identifier,org_id=user.org_id,env=env,author_id=user.id,kind=KIND,status='ready',duration_ms=0,
                result={'key':digest(idempotency_key),'fingerprint':fingerprint,'expires':timestamp+604800,'envelope':envelope})
            db.add(row);db.flush();audit(db,user.org_id,user.id,'audit.signed_metadata_created',detail={'snapshot_id':row.id,'count':len(records),'key_id':identity})
            return receipt(row)
