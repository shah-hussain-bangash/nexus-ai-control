"""Owner-reviewed supplier checks, admitted only through the governed outbox."""
import re
from typing import Literal
from fastapi import Request,Header
from pydantic import Field,field_validator
from sqlalchemy import select,func
from .schemas import Strict,ActionInput
from .db import Agent,Tool,Grant,Action,WorkbenchRun,Audit
from .check_evidence import evidence
from .security import fail,digest
from .runtime_context import runtime_environment
from .service import scoped,submit_action,audit,canonical
from .business_connector import connector_profile,validate_business

KIND='connector_check_intake'
TERMINAL=('verified','failed','denied','blocked','cancelled','rejected','changes_requested','expired')

class CheckInput(Strict):
    agent_id:str=Field(min_length=1,max_length=64)
    tool_id:str=Field(min_length=1,max_length=64)
    expected_grant_id:str=Field(min_length=1,max_length=64)
    expected_agent_generation:int=Field(ge=1,strict=True)
    expected_tool_version:Literal['1.0']
    expected_destination:str=Field(min_length=1,max_length=128)
    supplier_id:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')
    note:str=Field(min_length=5,max_length=500)
    reviewed:Literal[True]

    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<5 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Include a visible review reason on one line.')
        return value.strip()

class ReceiptKey(Strict):
    key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')

def principal(actor):return 'connector-check:'+actor.id
def receipt_id(actor,env,key):return digest(canonical([KIND,actor.org_id,actor.id,env,key]))
def receipt(db,actor,env,key):
    return db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==receipt_id(actor,env,key),WorkbenchRun.org_id==actor.org_id,
        WorkbenchRun.env==env,WorkbenchRun.author_id==actor.id,WorkbenchRun.kind==KIND))

def summary(row):
    if row.envelope.get('action')!='supplier:read':fail(409,'CHECK_SCOPE_INVALID','This record does not match a supplier check.')
    return {'id':row.id,'status':row.status,'reason':row.reason,'supplier_id':row.envelope['arguments']['supplier_id'],
            'destination':row.envelope['destination'],'connector_mode':'http' if row.envelope['destination'].startswith('http-business-v1:') else 'synthetic',
            'verified':row.status=='verified' and bool(row.verification.get('matched')),'external_ref':row.external_ref,'trace_id':row.trace_id,'created':row.created,'updated':row.updated}

def outcome(db,actor,record):
    if record.result['status']=='cancelled':return {'id':record.id,'status':'cancelled'}
    row=db.scalar(select(Action).where(Action.id==record.result['action_id'],Action.org_id==actor.org_id,Action.env==runtime_environment(db,actor.org_id),Action.principal==principal(actor)))
    if not row:fail(404,'CHECK_NOT_FOUND','The admitted check is unavailable; review the execution ledger before starting another intent.')
    return {'id':record.id,'status':'submitted','check':summary(row)}

def capacity(db,org):
    table=WorkbenchRun.__table__
    if db.scalar(select(func.count()).select_from(table).where(table.c.org_id==org,table.c.kind==KIND))>=1000:
        fail(429,'CHECK_CAPACITY','This workspace has reached its limit of 1000 check/cancellation receipts.')

def checks(db,actor):
    return select(Action).where(Action.org_id==actor.org_id,Action.env==runtime_environment(db,actor.org_id),Action.principal==principal(actor))

def register_connector_checks(app,factory,settings,human):
    def owner(request,db,write=False):
        if settings.mode!='local':fail(403,'LOCAL_ONLY','Owner connector checks are available only in local mode.')
        return human(request,db,write,'members')

    @app.get('/v1/connector-checks/config')
    def config(request:Request):
        with factory() as db:
            actor=owner(request,db);env=runtime_environment(db,actor.org_id)
            rows=db.execute(select(Grant,Agent,Tool).join(Agent,(Agent.id==Grant.agent_id)&(Agent.org_id==Grant.org_id)&(Agent.env==Grant.env)).join(
                Tool,(Tool.id==Grant.tool_id)&(Tool.org_id==Grant.org_id)&(Tool.env==Grant.env)).where(Grant.org_id==actor.org_id,Grant.env==env,
                Grant.scope=='supplier:read',Agent.status=='active',Tool.status=='validated',Tool.kind=='supplier').order_by(Agent.name,Tool.name,Grant.id).limit(201)).all()
            if len(rows)>200:fail(422,'CHECK_ROUTE_CAPACITY','This review supports up to 200 active granted supplier routes.')
            return {'connector':connector_profile(settings),'environment':env,'choices':[{'grant_id':g.id,'agent_id':a.id,'agent_name':a.name,
                'agent_generation':a.generation,'tool_id':t.id,'tool_name':t.name,'tool_version':t.version} for g,a,t in rows],
                'boundary':'Supplier-read evidence only. Submission uses policy and the existing worker. Synthetic checks do not contact a customer system or certify acceptance.'}

    @app.get('/v1/connector-checks')
    def history(request:Request):
        with factory() as db:
            actor=owner(request,db);query=checks(db,actor)
            rows=db.scalars(query.order_by(Action.created.desc(),Action.id.desc()).limit(20)).all()
            opened=db.scalar(query.where(Action.status.not_in(TERMINAL)).order_by(Action.created.desc(),Action.id.desc()).limit(1))
            return {'items':[summary(row) for row in rows],'open_check':summary(opened) if opened else None}

    @app.get('/v1/connector-checks/{check_id}/evidence')
    def export_evidence(check_id:str,request:Request):
        with factory() as db:
            actor=owner(request,db);env=runtime_environment(db,actor.org_id)
            # One SELECT captures action and audit events in the same database snapshot.
            rows=db.execute(select(Action,Audit).outerjoin(Audit,(Audit.action_id==Action.id)&
                (Audit.org_id==Action.org_id)&(Audit.env==Action.env)).where(Action.id==check_id,
                Action.org_id==actor.org_id,Action.env==env,Action.principal==principal(actor))
                .order_by(Audit.created,Audit.id).limit(201)).all()
            if not rows:fail(404,'CHECK_NOT_FOUND','No supplier check matches this account and environment.')
            if len(rows)>200:fail(422,'EVIDENCE_CAPACITY','This report supports up to 200 audit events; use the execution ledger.')
            return evidence(rows[0][0],[event for _,event in rows if event is not None],actor)

    @app.post('/v1/connector-checks/recover')
    def recover(body:ReceiptKey,request:Request):
        with factory.begin() as db:
            actor=owner(request,db,True);env=runtime_environment(db,actor.org_id);old=receipt(db,actor,env,body.key)
            if not old:fail(404,'CHECK_NOT_FOUND','No receipt matches this account, source environment and key. Recover again or cancel the pending intent.')
            return outcome(db,actor,old)

    @app.post('/v1/connector-checks/cancel-pending')
    def cancel(body:ReceiptKey,request:Request):
        with factory.begin() as db:
            actor=owner(request,db,True);env=runtime_environment(db,actor.org_id);old=receipt(db,actor,env,body.key)
            if old:return outcome(db,actor,old)
            capacity(db,actor.org_id)
            old=WorkbenchRun(id=receipt_id(actor,env,body.key),org_id=actor.org_id,env=env,kind=KIND,status='cancelled',duration_ms=0,author_id=actor.id,result={'status':'cancelled'})
            db.add(old);audit(db,actor.org_id,actor.id,'connector.check_intent_cancelled',detail={'receipt_id':old.id})
            return outcome(db,actor,old)

    @app.post('/v1/connector-checks',status_code=202)
    def submit(body:CheckInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Provide a unique 16–100 character check key and retain it after uncertainty.')
        with factory.begin() as db:
            actor=owner(request,db,True);env=runtime_environment(db,actor.org_id);fingerprint=digest(canonical(body.model_dump()))
            old=receipt(db,actor,env,idempotency_key)
            if old:
                if old.result['status']=='cancelled':fail(409,'CHECK_CANCELLED','This pending intent was cancelled and cannot admit a check.')
                if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different reviewed check.')
                return outcome(db,actor,old)
            if db.scalar(checks(db,actor).where(Action.status.not_in(TERMINAL)).limit(1)):
                fail(409,'CHECK_IN_PROGRESS','Finish or reconcile your existing check in this environment before starting another.')
            try:validate_business(settings);profile=connector_profile(settings)
            except RuntimeError:fail(503,'CONNECTOR_UNAVAILABLE','Ask the server operator to verify the configured business connector and credential.')
            if body.expected_destination!=profile['destination']:fail(409,'SOURCE_CHANGED','Connector destination changed. Refresh and review the configured destination again.')
            agent=scoped(db,Agent,body.agent_id,actor.org_id);tool=scoped(db,Tool,body.tool_id,actor.org_id)
            grant=db.scalar(select(Grant).where(Grant.id==body.expected_grant_id,Grant.org_id==actor.org_id,Grant.env==env,Grant.agent_id==agent.id,Grant.tool_id==tool.id,Grant.scope=='supplier:read'))
            if agent.status!='active' or agent.generation!=body.expected_agent_generation or tool.kind!='supplier' or tool.status!='validated' or tool.version!=body.expected_tool_version or not grant:
                fail(409,'SOURCE_CHANGED','The granted supplier route changed. Refresh and review it again.')
            capacity(db,actor.org_id)
            action=submit_action(db,settings,agent,tool,ActionInput(action='supplier:read',resource='suppliers',tool_version=body.expected_tool_version,
                arguments={'supplier_id':body.supplier_id},simulation='normal'),idempotency_key,principal(actor),actor.id)
            record=WorkbenchRun(id=receipt_id(actor,env,idempotency_key),org_id=actor.org_id,env=env,kind=KIND,status='completed',duration_ms=0,author_id=actor.id,
                result={'status':'submitted','action_id':action.id,'fingerprint':fingerprint})
            db.add(record);audit(db,actor.org_id,actor.id,'connector.check_submitted',action,{'receipt_id':record.id,'destination':profile['destination'],'note':body.note})
            return outcome(db,actor,record)
