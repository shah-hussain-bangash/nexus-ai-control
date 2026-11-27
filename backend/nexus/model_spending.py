"""Owner-managed environment/model admission ceilings over existing call accounting."""
import re
from datetime import datetime,timezone
from fastapi import Request,Header,Query
from pydantic import Field,field_validator,model_validator
from sqlalchemy import select,update,func,case
from .db import WorkbenchRun,InferenceCall,WorkspaceAsset,Organization
from .runtime_context import runtime_environment
from .schemas import Strict
from .security import fail,digest
from .service import canonical,audit

KIND='inference_spend_policy'
MAX_MONEY=1000000000000
BOUNDARY='Current-environment model-route ceilings for new inference admissions, using operator-priced spend plus unresolved reservations. Workspace/server limits remain separate. Not provider-account billing, hardware cost control or a guarantee against actual usage exceeding estimates.'


class Cap(Strict):
    model_id:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    expected_model_version:int=Field(strict=True,ge=1)
    monthly_limit_micro_usd:int=Field(strict=True,ge=0,le=MAX_MONEY)


class Policy(Strict):
    expected_version:int=Field(strict=True,ge=0)
    require_model_caps:bool=Field(default=False,strict=True)
    caps:list[Cap]=Field(default_factory=list,max_length=100)
    note:str=Field(min_length=10,max_length=1000)
    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<10 or '\x00' in value:raise ValueError('Use a visible policy change note.')
        return value.strip()
    @model_validator(mode='after')
    def unique(self):
        if len({cap.model_id for cap in self.caps})!=len(self.caps):raise ValueError('Assign at most one cap per model route.')
        return self


class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


def policy_rows(db,user):
    return select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND)


def current_policy(db,org,environment):
    rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==org,WorkbenchRun.env==runtime_environment(db,org,environment),WorkbenchRun.kind==KIND,WorkbenchRun.status=='active').limit(2)).all()
    if len(rows)>1:fail(409,'SPEND_POLICY_INCONSISTENT','Multiple active spending policies require owner review.')
    return rows[0] if rows else None


def usage(db,org,environment,period):
    environment=runtime_environment(db,org,environment)
    rows=db.execute(select(InferenceCall.asset_id,
        func.sum(case((InferenceCall.status.in_(('completed','reconciled')),InferenceCall.charged),else_=0)),
        func.sum(case((InferenceCall.status.in_(('pending','unknown')),InferenceCall.reserved),else_=0)),func.count())
        .where(InferenceCall.org_id==org,InferenceCall.env==environment,InferenceCall.period==period).group_by(InferenceCall.asset_id)).all()
    return {id:{'spent_micro_usd':int(spent or 0),'held_micro_usd':int(held or 0),'calls':count} for id,spent,held,count in rows}


def enforce(db,user,model_id,period):
    # Caller holds the organization and workspace-budget lock. Its newly flushed
    # pending row is included, so no reservation is counted twice.
    environment=runtime_environment(db,user.org_id);policy=current_policy(db,user.org_id,environment)
    if not policy:return None
    config=policy.result;cap=next((cap for cap in config['caps'] if cap['model_id']==model_id),None)
    if not cap:
        if config['require_model_caps']:fail(429,'MODEL_SPEND_CAP_REQUIRED','An owner must assign a cap to this model route before new inference.')
        return {'policy_id':policy.id,'policy_version':config['version'],'model_id':model_id,'capped':False,'require_model_caps':False}
    totals=usage(db,user.org_id,environment,period).get(model_id,{'spent_micro_usd':0,'held_micro_usd':0})
    if totals['spent_micro_usd']+totals['held_micro_usd']>cap['monthly_limit_micro_usd']:
        fail(429,'MODEL_SPEND_LIMIT','The model route has insufficient unreserved monthly capacity. No provider request was sent.')
    return {'policy_id':policy.id,'policy_version':config['version'],'model_id':model_id,'capped':True,
        'monthly_limit_micro_usd':cap['monthly_limit_micro_usd'],'period':period,'scope':'environment/model asset across versions'}


def snapshot(row):
    if not row:return {'id':None,'status':'not_configured','version':0,'require_model_caps':False,'caps':[],'note':'','created':None}
    return {'id':row.id,'status':row.status,'created':row.created,**{k:row.result[k] for k in ('version','require_model_caps','caps','note')}}


def overview(db,user):
    environment=runtime_environment(db,user.org_id);period=datetime.now(timezone.utc).strftime('%Y-%m')
    current=current_policy(db,user.org_id,environment);value=snapshot(current);caps={cap['model_id']:cap for cap in value['caps']}
    models=db.scalars(select(WorkspaceAsset).where(WorkspaceAsset.org_id==user.org_id,WorkspaceAsset.env==environment,WorkspaceAsset.kind=='model').order_by(WorkspaceAsset.name,WorkspaceAsset.id).limit(501)).all()
    if len(models)>500:fail(409,'SPEND_MODEL_CAPACITY','Review the model inventory before loading spending controls.')
    totals=usage(db,user.org_id,environment,period);items=[]
    for model in models:
        used=totals.get(model.id,{'spent_micro_usd':0,'held_micro_usd':0,'calls':0});cap=caps.get(model.id)
        limit=cap['monthly_limit_micro_usd'] if cap else None
        items.append({'id':model.id,'name':model.name,'version':model.version,'status':model.status,**used,
            'spent_micro_usd':str(used['spent_micro_usd']),'held_micro_usd':str(used['held_micro_usd']),
            'monthly_limit_micro_usd':limit,'remaining_micro_usd':max(0,limit-used['spent_micro_usd']-used['held_micro_usd']) if limit is not None else None,
            'over_limit':bool(limit is not None and used['spent_micro_usd']+used['held_micro_usd']>limit)})
    return {**value,'models':items,'period':period,'currency':'USD','scope':{'workspace_id':user.org_id,'environment':environment},'provider_calls':0,'boundary':BOUNDARY}


def register_model_spending(app,factory,human):
    @app.get('/v1/inference-spend-controls')
    def inspect(request:Request):
        with factory() as db:
            user=human(request,db,False,'export');return overview(db,user)

    @app.get('/v1/inference-spend-controls/history')
    def history(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db,False,'export');rows=db.scalars(policy_rows(db,user).order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).offset(offset).limit(limit+1)).all()
            return {'items':[snapshot(row) for row in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}

    @app.post('/v1/inference-spend-controls/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'export');rows=db.scalars(policy_rows(db,user).where(WorkbenchRun.author_id==user.id))
            row=next((row for row in rows if row.result.get('key')==digest(body.key)),None)
            if not row:fail(404,'SPEND_POLICY_NOT_FOUND','No policy change matches this account and key.')
            return {**snapshot(row),'boundary':BOUNDARY}

    @app.put('/v1/inference-spend-controls',status_code=201)
    def save(body:Policy,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        key=digest(idempotency_key);fingerprint=digest(canonical(body.model_dump()))
        with factory.begin() as db:
            user=human(request,db,True,'members');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            rows=db.scalars(policy_rows(db,user).where(WorkbenchRun.author_id==user.id))
            old=next((row for row in rows if row.result.get('key')==key),None)
            if old:
                if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another spending-policy change.')
                return {**snapshot(old),'boundary':BOUNDARY}
            current=current_policy(db,user.org_id,runtime_environment(db,user.org_id));version=current.result['version'] if current else 0
            if body.expected_version!=version:fail(409,'STALE_VERSION','Refresh the current spending policy before saving.')
            if db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND))>=200:
                fail(429,'SPEND_POLICY_HISTORY_CAPACITY','Policy history reached its bounded capacity; no policy was changed.')
            caps=[]
            for cap in body.caps:
                model=db.scalar(select(WorkspaceAsset).where(WorkspaceAsset.id==cap.model_id,WorkspaceAsset.org_id==user.org_id,WorkspaceAsset.env==runtime_environment(db,user.org_id),WorkspaceAsset.kind=='model'))
                if not model or model.status=='archived':fail(404,'SPEND_MODEL_NOT_FOUND','A selected model route is unavailable.')
                if model.version!=cap.expected_model_version:fail(409,'SPEND_MODEL_CHANGED','Refresh the selected model route before assigning its cap.')
                caps.append({'model_id':model.id,'reviewed_model_version':model.version,'monthly_limit_micro_usd':cap.monthly_limit_micro_usd})
            if current:current.status='superseded'
            row=WorkbenchRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,kind=KIND,status='active',duration_ms=0,
                result={'key':key,'fingerprint':fingerprint,'version':version+1,'require_model_caps':body.require_model_caps,'caps':caps,'note':body.note})
            db.add(row);db.flush();audit(db,user.org_id,user.id,'inference.spend_policy_changed',detail={'policy_id':row.id,'version':version+1,'model_caps':len(caps),'require_model_caps':body.require_model_caps})
            return {**snapshot(row),'boundary':BOUNDARY}
