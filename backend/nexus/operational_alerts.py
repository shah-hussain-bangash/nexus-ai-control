"""Manual, environment-scoped alert evaluation. No notification or worker transport."""
import re
from typing import Literal
from fastapi import Request, Header, Query
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select, func, update
from .db import Action, DurableRun, IngestionJob, InferenceCall, WorkbenchRun, Organization, now
from .runtime_context import runtime_environment
from .schemas import Strict
from .security import fail, digest
from .service import canonical, audit

POLICY='operational_alert_policy'
SAMPLE='operational_alert_sample'
Metric=Literal['oldest_queued_action_age_seconds','unknown_action_count','unknown_inference_count','overdue_pending_inference_count','expired_ingestion_lease_count','expired_index_build_lease_count','expired_agent_run_lease_count']
BOUNDARY='Manual point-in-time database thresholds in the current environment. No continuous monitoring, external notification, automatic remediation, worker heartbeat or SLO acceptance. A clear sample is not a health or production-readiness guarantee.'


class Rule(Strict):
    metric:Metric
    enabled:bool=Field(default=True,strict=True)
    severity:Literal['warning','critical']='warning'
    threshold:int=Field(strict=True,ge=1,le=1000000)
    @model_validator(mode='after')
    def bounded_age(self):
        if self.metric=='oldest_queued_action_age_seconds' and self.threshold>604800:raise ValueError('Queue age threshold must be at most seven days, in seconds.')
        return self


class Note(Strict):
    note:str=Field(min_length=10,max_length=1000)
    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<10 or '\x00' in value:raise ValueError('Use a visible note of at least ten characters.')
        return value.strip()


class PolicyInput(Note):
    expected_version:int=Field(strict=True,ge=0)
    rules:list[Rule]=Field(max_length=7)
    @model_validator(mode='after')
    def unique(self):
        if len({rule.metric for rule in self.rules})!=len(self.rules):raise ValueError('Use at most one rule per fixed signal.')
        return self


class EvaluationInput(Note):expected_version:int=Field(strict=True,ge=0)
class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


def rows(db,user,kind):
    return select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==kind)


def current(db,user):
    found=db.scalars(rows(db,user,POLICY).where(WorkbenchRun.status=='active').limit(2)).all()
    if len(found)>1:fail(409,'ALERT_POLICY_INCONSISTENT','Multiple active alert policies require owner review.')
    return found[0] if found else None


def policy_view(row):
    return {'id':row.id,'status':row.status,'created':row.created,**{k:row.result[k] for k in ('version','rules','note')}} if row else {'id':None,'status':'not_configured','version':0,'rules':[],'note':'','created':None}


def signals(db,user):
    timestamp=now();org=user.org_id;env=runtime_environment(db,org)
    def count(model,*conditions):
        return select(func.count()).select_from(model).where(model.org_id==org,model.env==env,*conditions).scalar_subquery()
    oldest=select(func.min(Action.created)).where(Action.org_id==org,Action.env==env,Action.status=='queued').scalar_subquery()
    # One statement keeps all seven database readings in a single snapshot.
    values=db.execute(select(oldest,
        count(Action,Action.status=='outcome_unknown'),
        count(InferenceCall,InferenceCall.status=='unknown'),
        count(InferenceCall,InferenceCall.status=='pending',InferenceCall.created<=timestamp-300),
        count(IngestionJob,IngestionJob.status=='processing',IngestionJob.lease_until<=timestamp),
        count(WorkbenchRun,WorkbenchRun.kind=='neural_index_job',WorkbenchRun.status=='processing',func.coalesce(WorkbenchRun.result['lease_until'].as_float(),0)<=timestamp),
        count(DurableRun,DurableRun.status=='processing',DurableRun.lease_until<=timestamp))).one()
    names=('oldest_queued_action_age_seconds','unknown_action_count','unknown_inference_count','overdue_pending_inference_count','expired_ingestion_lease_count','expired_index_build_lease_count','expired_agent_run_lease_count')
    return {'sampled_at':timestamp,'values':dict(zip(names,[max(0,int(timestamp-values[0])) if values[0] is not None else 0,*values[1:]]))}


def evaluate(policy,reading):
    results=[{**rule,'value':reading['values'][rule['metric']],
        'status':'disabled' if not rule['enabled'] else 'firing' if reading['values'][rule['metric']]>=rule['threshold'] else 'clear'} for rule in policy['rules']]
    status='firing' if any(rule['status']=='firing' for rule in results) else 'clear' if any(rule['enabled'] for rule in results) else 'disabled'
    return {**reading,'status':status,'rules':results,'policy_id':policy['id'],'policy_version':policy['version']}


def sample_view(row,version):
    return {'id':row.id,'status':row.status,'created':row.created,**{k:row.result[k] for k in ('sampled_at','values','rules','policy_id','policy_version','note')},'stale_policy':row.result['policy_version']!=version}


def owned_receipt(db,user,kind,key):
    return next((row for row in db.scalars(rows(db,user,kind).where(WorkbenchRun.author_id==user.id)) if row.result.get('key')==digest(key)),None)


def register_operational_alerts(app,factory,human):
    @app.get('/v1/operational-alerts')
    def overview(request:Request):
        with factory() as db:
            user=human(request,db);policy=policy_view(current(db,user))
            return {'policy':policy,'live':evaluate(policy,signals(db,user)),'boundary':BOUNDARY}

    @app.get('/v1/operational-alerts/history')
    def history(request:Request,kind:Literal['policy','sample']='sample',offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db);version=policy_view(current(db,user))['version']
            found=db.scalars(rows(db,user,POLICY if kind=='policy' else SAMPLE).order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).offset(offset).limit(limit+1)).all()
            return {'items':[policy_view(row) if kind=='policy' else sample_view(row,version) for row in found[:limit]],'next_offset':offset+limit if len(found)>limit else None}

    @app.post('/v1/operational-alerts/{kind}/recover')
    def recover(kind:Literal['policy','sample'],body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True);row=owned_receipt(db,user,POLICY if kind=='policy' else SAMPLE,body.key)
            if not row:fail(404,'ALERT_RECEIPT_NOT_FOUND','No matching receipt belongs to this account and environment.')
            return {**(policy_view(row) if kind=='policy' else sample_view(row,policy_view(current(db,user))['version'])),'boundary':BOUNDARY}

    def save(body,request,key,kind):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        fingerprint=digest(canonical(body.model_dump()))
        with factory.begin() as db:
            user=human(request,db,True,'members' if kind==POLICY else 'operate')
            db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            policy=current(db,user);view=policy_view(policy);previous=owned_receipt(db,user,kind,key)
            if previous:
                if previous.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different alert request.')
                return {**(policy_view(previous) if kind==POLICY else sample_view(previous,view['version'])),'boundary':BOUNDARY}
            if body.expected_version!=view['version']:fail(409,'STALE_VERSION','Reload the current alert policy before submitting.')
            capacity=200 if kind==POLICY else 500
            if db.scalar(select(func.count()).select_from(rows(db,user,kind).subquery()))>=capacity:fail(429,'ALERT_HISTORY_CAPACITY','This environment has reached its bounded alert-history capacity. No existing history was removed.')
            if kind==POLICY:
                if policy:policy.status='superseded'
                payload={'version':view['version']+1,'rules':[rule.model_dump() for rule in body.rules],'note':body.note}
                status='active'
            else:
                payload={**evaluate(view,signals(db,user)),'note':body.note};status=payload.pop('status')
            row=WorkbenchRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,kind=kind,status=status,duration_ms=0,
                result={**payload,'key':digest(key),'fingerprint':fingerprint})
            db.add(row);db.flush()
            audit(db,user.org_id,user.id,'operations.alert_policy_changed' if kind==POLICY else 'operations.alert_sample_recorded',detail={'receipt_id':row.id,'policy_version':payload.get('version',payload.get('policy_version')),'status':status})
            return {**(policy_view(row) if kind==POLICY else sample_view(row,view['version'])),'boundary':BOUNDARY}

    @app.put('/v1/operational-alerts/policy',status_code=201)
    def change(body:PolicyInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        return save(body,request,idempotency_key,POLICY)

    @app.post('/v1/operational-alerts/sample',status_code=201)
    def record(body:EvaluationInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        return save(body,request,idempotency_key,SAMPLE)
