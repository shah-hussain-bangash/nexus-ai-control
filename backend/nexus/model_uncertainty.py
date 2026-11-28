"""Owner-reviewed admission pauses for recorded unknown outcomes; no retries."""
import re
from fastapi import Request,Header,Query
from pydantic import Field,field_validator,model_validator
from sqlalchemy import select,update,func
from .db import WorkbenchRun,WorkspaceAsset,InferenceCall,Organization
from .runtime_context import runtime_environment
from .schemas import Strict
from .security import fail,digest
from .service import canonical,audit

KIND='model_uncertainty_policy'
BOUNDARY='Admission limits over recorded unknown inference outcomes in this environment, across all months and route versions. No retries, fallback, provider health probe or cancellation of already admitted calls. Pending calls retain existing concurrency/reservation controls. This is not provider acceptance or a guarantee against overlapping failures.'

class Rule(Strict):
    model_id:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    expected_model_version:int=Field(strict=True,ge=1)
    unknown_limit:int=Field(strict=True,ge=1,le=100)

class Policy(Strict):
    expected_version:int=Field(strict=True,ge=0)
    rules:list[Rule]=Field(max_length=100)
    note:str=Field(min_length=10,max_length=1000)
    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<10 or any(ord(char)<32 or ord(char)==127 for char in value):raise ValueError('Use a visible policy reason.')
        return value.strip()
    @model_validator(mode='after')
    def unique(self):
        if len({rule.model_id for rule in self.rules})!=len(self.rules):raise ValueError('Use at most one limit per model route.')
        return self

class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')

def rows(db,user):
    return select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND)

def current(db,user):
    found=db.scalars(rows(db,user).where(WorkbenchRun.status=='active').limit(2)).all()
    if len(found)>1:fail(409,'UNCERTAINTY_POLICY_INCONSISTENT','Multiple active model-failure policies require owner review.')
    return found[0] if found else None

def snapshot(row):
    return {'id':row.id,'status':row.status,'created':row.created,**{key:row.result[key] for key in ('version','rules','note')}} if row else {'id':None,'status':'not_configured','created':None,'version':0,'rules':[],'note':''}

def unknown_counts(db,user):
    return dict(db.execute(select(InferenceCall.asset_id,func.count()).where(InferenceCall.org_id==user.org_id,InferenceCall.env==runtime_environment(db,user.org_id),InferenceCall.status=='unknown').group_by(InferenceCall.asset_id)).all())

def enforce(db,user,model_id):
    # Caller holds the workspace admission lock; its new pending row is not an
    # unknown outcome. Concurrent calls admitted earlier cannot be undone here.
    policy=current(db,user)
    if not policy:return None
    rule=next((item for item in policy.result['rules'] if item['model_id']==model_id),None)
    if not rule:return None
    count=unknown_counts(db,user).get(model_id,0)
    if count>=rule['unknown_limit']:fail(429,'MODEL_UNCERTAINTY_LIMIT','Recorded unknown outcomes reached this route limit. Ask an owner to reconcile the existing outcomes or review the policy. No new provider request was sent.')
    return {'policy_id':policy.id,'policy_version':policy.result['version'],'model_id':model_id,'unknown_limit':rule['unknown_limit'],'unknown_before_admission':count}

def register_model_uncertainty(app,factory,human):
    @app.get('/v1/model-uncertainty-controls')
    def inspect(request:Request):
        with factory() as db:
            user=human(request,db,False,'export');policy=snapshot(current(db,user));limits={item['model_id']:item for item in policy['rules']};counts=unknown_counts(db,user)
            models=db.scalars(select(WorkspaceAsset).where(WorkspaceAsset.org_id==user.org_id,WorkspaceAsset.env==runtime_environment(db,user.org_id),WorkspaceAsset.kind=='model').order_by(WorkspaceAsset.name,WorkspaceAsset.id).limit(501)).all()
            if len(models)>500:fail(409,'UNCERTAINTY_MODEL_CAPACITY','Review the bounded model inventory before loading controls.')
            return {**policy,'models':[{'id':model.id,'name':model.name,'version':model.version,'status':model.status,'unknown_calls':counts.get(model.id,0),'unknown_limit':limits.get(model.id,{}).get('unknown_limit'),'blocked':bool(model.id in limits and counts.get(model.id,0)>=limits[model.id]['unknown_limit'])} for model in models],
                'scope':{'workspace_id':user.org_id,'environment':runtime_environment(db,user.org_id)},'boundary':BOUNDARY}

    @app.get('/v1/model-uncertainty-controls/history')
    def history(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db,False,'export');found=db.scalars(rows(db,user).order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).offset(offset).limit(limit+1)).all()
            return {'items':[snapshot(row) for row in found[:limit]],'next_offset':offset+limit if len(found)>limit else None}

    @app.post('/v1/model-uncertainty-controls/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'export');old=next((row for row in db.scalars(rows(db,user).where(WorkbenchRun.author_id==user.id)) if row.result.get('key')==digest(body.key)),None)
            if not old:fail(404,'UNCERTAINTY_POLICY_NOT_FOUND','No model-failure policy receipt belongs to this account and environment.')
            return {**snapshot(old),'boundary':BOUNDARY}

    @app.put('/v1/model-uncertainty-controls',status_code=201)
    def save(body:Policy,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        fingerprint=digest(canonical(body.model_dump()))
        with factory.begin() as db:
            user=human(request,db,True,'members');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            old=next((row for row in db.scalars(rows(db,user).where(WorkbenchRun.author_id==user.id)) if row.result.get('key')==digest(idempotency_key)),None)
            if old:
                if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different model-failure policy.')
                return {**snapshot(old),'boundary':BOUNDARY}
            active=current(db,user);version=active.result['version'] if active else 0
            if body.expected_version!=version:fail(409,'STALE_VERSION','Reload the current model-failure policy before saving.')
            count=db.scalar(select(func.count()).select_from(rows(db,user).subquery()))
            if count>=200 or body.rules and count>=199:fail(429,'UNCERTAINTY_HISTORY_CAPACITY','Policy history reached its bound; the final slot is reserved for clearing all limits.')
            rules=[]
            for rule in body.rules:
                model=db.scalar(select(WorkspaceAsset).where(WorkspaceAsset.id==rule.model_id,WorkspaceAsset.org_id==user.org_id,WorkspaceAsset.env==runtime_environment(db,user.org_id),WorkspaceAsset.kind=='model'))
                if not model or model.status=='archived':fail(404,'UNCERTAINTY_MODEL_NOT_FOUND','A selected model route is unavailable.')
                if model.version!=rule.expected_model_version:fail(409,'UNCERTAINTY_MODEL_CHANGED','Reload the selected model route before setting its limit.')
                rules.append({'model_id':model.id,'reviewed_model_version':model.version,'unknown_limit':rule.unknown_limit})
            if active:active.status='superseded'
            row=WorkbenchRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,kind=KIND,status='active',duration_ms=0,result={'key':digest(idempotency_key),'fingerprint':fingerprint,'version':version+1,'rules':rules,'note':body.note})
            db.add(row);db.flush();audit(db,user.org_id,user.id,'inference.uncertainty_policy_changed',detail={'policy_id':row.id,'version':version+1,'routes':len(rules)})
            return {**snapshot(row),'boundary':BOUNDARY}
