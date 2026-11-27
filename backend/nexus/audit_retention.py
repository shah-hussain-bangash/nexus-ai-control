"""Explicit, preview-bound removal of expired signed snapshot payloads only."""
import re
import math
from fastapi import Request,Header
from pydantic import Field,field_validator
from sqlalchemy import select,update,func
from .db import WorkbenchRun,Organization,now
from .schemas import Strict
from .runtime_context import runtime_environment
from .security import fail,digest
from .service import audit,canonical
from .signed_audit import KIND as SNAPSHOT,receipt

POLICY='audit_payload_retention_policy'
HOLD='audit_payload_retention_hold'
PLAN='audit_payload_retention_plan'
CONFIRM='PURGE EXPIRED SIGNED AUDIT PAYLOADS'
BOUNDARY='Explicit removal of expired signed-audit snapshot payloads only. Original audit events, signing keys, source records and downloaded copies are not changed. Holds protect snapshots from this tool only. Tombstones and operation receipts remain. No scheduled deletion, legal-compliance certification or immutable archive is provided.'


class Note(Strict):
    note:str=Field(min_length=10,max_length=500)
    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<10 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Use a visible 10–500 character reason.')
        return value.strip()


class PolicyInput(Note):
    expected_version:int=Field(strict=True,ge=0)
    enabled:bool=Field(strict=True)
    minimum_age_days:int=Field(strict=True,ge=7,le=3650)


class HoldInput(Note):
    expected_version:int=Field(strict=True,ge=0)
    held:bool=Field(strict=True)


class PlanInput(Note):expected_version:int=Field(strict=True,ge=0)
class ApplyInput(Note):
    expected_version:int=Field(strict=True,ge=1)
    confirmation:str=Field(max_length=80)
class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


def rows(db,user,kind):
    return select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==kind)


def lock(db,user):db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))


def policy(db,user):
    found=db.scalars(rows(db,user,POLICY).where(WorkbenchRun.status=='active').limit(2)).all()
    if len(found)>1:fail(409,'RETENTION_POLICY_INCONSISTENT','Multiple active policies require owner review.')
    row=found[0] if found else None
    return row,({'id':row.id,'status':row.status,**{key:row.result[key] for key in ('version','enabled','minimum_age_days','note')}} if row else {'id':None,'status':'not_configured','version':0,'enabled':False,'minimum_age_days':30,'note':''})


def holds(db,user):
    found=db.scalars(rows(db,user,HOLD)).all();result={}
    for row in found:
        target=row.result['snapshot_id']
        if target in result:fail(409,'RETENTION_HOLD_INCONSISTENT','Duplicate holds require owner review.')
        result[target]=row
    return result


def hold_view(row):
    return {'held':row.status=='active','version':row.result['version'],'note':row.result['note']} if row else {'held':False,'version':0,'note':''}


def eligible(row,config,hold,timestamp):
    if not config['enabled'] or row.status!='ready' or hold['held']:return False
    try:
        envelope=row.result['envelope'];payload=envelope['payload'];expires=row.result['expires'];created=payload['created_at_us']/1000000
        return (payload['id']==row.id and payload['workspace_id']==row.org_id and payload['environment']==row.env
            and type(expires) in (int,float) and math.isfinite(expires) and expires<=timestamp
            and math.isfinite(created) and 0<=created<=timestamp-config['minimum_age_days']*86400
            and 0<=row.created<=timestamp-config['minimum_age_days']*86400)
    except (KeyError,TypeError,ValueError,OverflowError):return False


def plan_view(row):
    return {'id':row.id,'status':row.status,'created':row.created,**{key:row.result[key] for key in ('policy_version','expires','targets','note')},
        'applied_at':row.result.get('applied_at'),'purged_count':row.result.get('purged_count',0),'boundary':BOUNDARY}


def own_intent(db,user,kind,key):
    return next((row for row in db.scalars(rows(db,user,kind).where(WorkbenchRun.author_id==user.id)) if row.result.get('key')==digest(key)),None)


def register_audit_retention(app,factory,human):
    @app.get('/v1/audit-retention')
    def overview(request:Request):
        with factory() as db:
            user=human(request,db,False,'members');_,config=policy(db,user);protected=holds(db,user);timestamp=now()
            found=db.scalars(rows(db,user,SNAPSHOT).where(WorkbenchRun.status!='purged').order_by(WorkbenchRun.created,WorkbenchRun.id).limit(101)).all()
            if len(found)>100:fail(409,'RETENTION_INVENTORY_CAPACITY','Snapshot inventory exceeds its supported bound.')
            inventory=[]
            for row in found:
                hold=hold_view(protected.get(row.id))
                inventory.append({'id':row.id,'created':row.created,'expires':row.result.get('expires'),'hold':hold,'eligible':eligible(row,config,hold,timestamp)})
            history=db.scalars(rows(db,user,PLAN).order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).limit(20)).all()
            revisions=db.scalars(rows(db,user,POLICY).order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).limit(20)).all()
            return {'policy':config,'sampled_at':timestamp,'items':inventory,'plans':[plan_view(row) for row in history],
                'policies':[{'id':row.id,'status':row.status,'created':row.created,**{key:row.result[key] for key in ('version','enabled','minimum_age_days','note')}} for row in revisions],'boundary':BOUNDARY}

    @app.post('/v1/audit-retention/{kind}/recover')
    def recover(kind:str,body:Recover,request:Request):
        if kind not in ('policy','plan'):fail(404,'NOT_FOUND','Unknown retention operation.')
        with factory.begin() as db:
            user=human(request,db,True,'members');row=own_intent(db,user,POLICY if kind=='policy' else PLAN,body.key)
            if not row:fail(404,'RETENTION_RECEIPT_NOT_FOUND','No matching operation belongs to this account and environment.')
            return plan_view(row) if kind=='plan' else {'id':row.id,'status':row.status,**{key:row.result[key] for key in ('version','enabled','minimum_age_days','note')}}

    @app.put('/v1/audit-retention/holds/{id}')
    def change_hold(id:str,body:HoldInput,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'members');lock(db,user)
            target=db.scalar(rows(db,user,SNAPSHOT).where(WorkbenchRun.id==id))
            if not target or target.status!='ready':fail(404,'RETENTION_SNAPSHOT_UNAVAILABLE','Only retained signed snapshot payloads can be held or released.')
            old=holds(db,user).get(id);version=hold_view(old)['version']
            if body.expected_version!=version:fail(409,'STALE_VERSION','Reload the current hold before changing it.')
            if old:
                old.status='active' if body.held else 'released';old.result={'snapshot_id':id,'version':version+1,'note':body.note}
            else:
                old=WorkbenchRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,kind=HOLD,status='active' if body.held else 'released',duration_ms=0,result={'snapshot_id':id,'version':1,'note':body.note});db.add(old)
            db.flush();audit(db,user.org_id,user.id,'audit.snapshot_hold_changed',detail={'snapshot_id':id,'held':body.held,'version':version+1,'reason':body.note})
            return {'id':old.id,'status':old.status,**hold_view(old)}

    def create(body,request,key,kind):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        fingerprint=digest(canonical(body.model_dump()))
        with factory.begin() as db:
            user=human(request,db,True,'members');lock(db,user);old=own_intent(db,user,kind,key)
            if old:
                if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another retention request.')
                return plan_view(old) if kind==PLAN else {'id':old.id,'status':old.status,**{key:old.result[key] for key in ('version','enabled','minimum_age_days','note')}}
            current,config=policy(db,user)
            if body.expected_version!=config['version']:fail(409,'STALE_VERSION','Reload the current retention policy.')
            count=db.scalar(select(func.count()).select_from(rows(db,user,kind).subquery()))
            if count>=200 or kind==POLICY and body.enabled and count>=199:fail(429,'RETENTION_HISTORY_CAPACITY','Retention history reached its bound; the final policy slot is reserved for disabling. Existing receipts were preserved.')
            if kind==POLICY:
                if current:current.status='superseded'
                status='active';result={'version':config['version']+1,'enabled':body.enabled,'minimum_age_days':body.minimum_age_days,'note':body.note}
            else:
                if not config['enabled']:fail(409,'RETENTION_DISABLED','Enable and review a retention policy before creating a plan.')
                protected=holds(db,user);timestamp=now();targets=[]
                found=db.scalars(rows(db,user,SNAPSHOT).where(WorkbenchRun.status!='purged').order_by(WorkbenchRun.created,WorkbenchRun.id).limit(101)).all()
                if len(found)>100:fail(409,'RETENTION_INVENTORY_CAPACITY','Snapshot inventory exceeds its supported bound.')
                for row in found:
                    hold=hold_view(protected.get(row.id))
                    if eligible(row,config,hold,timestamp):targets.append({'id':row.id,'payload_sha256':digest(canonical(row.result)),'hold_version':hold['version']})
                status='previewed';result={'policy_version':config['version'],'expires':timestamp+900,'targets':targets,'note':body.note}
            row=WorkbenchRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,kind=kind,status=status,duration_ms=0,result={**result,'key':digest(key),'fingerprint':fingerprint})
            db.add(row);db.flush();audit(db,user.org_id,user.id,'audit.retention_policy_changed' if kind==POLICY else 'audit.retention_previewed',detail={'receipt_id':row.id,'policy_version':config['version']+1 if kind==POLICY else config['version'],'targets':len(result.get('targets',[])),'reason':body.note})
            return plan_view(row) if kind==PLAN else {'id':row.id,'status':row.status,**result}

    @app.put('/v1/audit-retention/policy',status_code=201)
    def save_policy(body:PolicyInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        return create(body,request,idempotency_key,POLICY)

    @app.post('/v1/audit-retention/plans',status_code=201)
    def preview(body:PlanInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        return create(body,request,idempotency_key,PLAN)

    @app.post('/v1/audit-retention/plans/{id}/apply')
    def apply(id:str,body:ApplyInput,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'members');lock(db,user);plan=db.scalar(rows(db,user,PLAN).where(WorkbenchRun.id==id))
            if not plan:fail(404,'RETENTION_PLAN_NOT_FOUND','No plan exists in this environment.')
            fingerprint=digest(canonical(body.model_dump()))
            if plan.status=='applied':
                if plan.result['apply_fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This plan already applied with a different confirmation.')
                return plan_view(plan)
            timestamp=now();_,config=policy(db,user)
            if body.confirmation!=CONFIRM:fail(422,'RETENTION_CONFIRMATION_REQUIRED','Type the exact displayed confirmation before applying.')
            if plan.status!='previewed' or plan.result['expires']<=timestamp:fail(409,'RETENTION_PLAN_EXPIRED','Create a fresh preview before applying retention.')
            if not config['enabled'] or body.expected_version!=config['version'] or plan.result['policy_version']!=config['version']:fail(409,'STALE_VERSION','The retention policy changed. Create a fresh preview.')
            protected=holds(db,user);selected=[]
            for target in plan.result['targets']:
                row=db.scalar(rows(db,user,SNAPSHOT).where(WorkbenchRun.id==target['id']));hold=hold_view(protected.get(target['id']))
                if not row or not eligible(row,config,hold,timestamp) or hold['version']!=target['hold_version'] or digest(canonical(row.result))!=target['payload_sha256']:
                    fail(409,'RETENTION_PLAN_STALE','A snapshot or hold changed. No payloads were removed; create a fresh preview.')
                selected.append(row)
            for row in selected:
                metadata=receipt(row);original=row.result
                row.result={key:original[key] for key in ('key','fingerprint','expires')}
                row.result={**row.result,'metadata':{key:metadata[key] for key in ('key_id','records','truncated')},'purged_at':timestamp,'retention_plan_id':plan.id,'payload_sha256':digest(canonical(original['envelope']))}
                row.status='purged'
            plan.status='applied';plan.result={**plan.result,'apply_fingerprint':fingerprint,'applied_at':timestamp,'purged_count':len(selected),'apply_note':body.note}
            audit(db,user.org_id,user.id,'audit.snapshot_payloads_purged',detail={'plan_id':plan.id,'count':len(selected),'policy_version':config['version'],'reason':body.note})
            return plan_view(plan)
