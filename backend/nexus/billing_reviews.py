"""Owner-entered statement comparison; never changes inference charges or budgets."""
import re
from typing import Literal
from fastapi import Request,Header,Query
from pydantic import Field,field_validator,model_validator
from sqlalchemy import select,update,func
from .db import InferenceCall,WorkbenchRun,Organization
from .schemas import Strict
from .runtime_context import runtime_environment
from .security import fail,digest
from .service import canonical,audit

KIND='billing_statement_review'
MAX_MONEY=1000000000000
BOUNDARY='Owner-entered statement comparison of selected current-environment calls only. Not provider-verified billing, a complete invoice/account reconciliation or a ledger adjustment. Budgets and unresolved reservations are unchanged.'


class Line(Strict):
    line_ref:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')
    call_id:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    billed_micro_usd:int=Field(strict=True,ge=0,le=MAX_MONEY)
    input_tokens:int|None=Field(default=None,strict=True,ge=0,le=100000000)
    output_tokens:int|None=Field(default=None,strict=True,ge=0,le=100000000)
    provider_request_id:str|None=Field(default=None,pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$')


class Statement(Strict):
    statement_ref:str=Field(min_length=2,max_length=120)
    period:str=Field(pattern=r'^20\d{2}-(0[1-9]|1[0-2])$')
    currency:Literal['USD']='USD'
    note:str=Field(min_length=10,max_length=1000)
    lines:list[Line]=Field(min_length=1,max_length=50)
    @field_validator('statement_ref','note')
    @classmethod
    def visible(cls,value,info):
        if len(value.strip())<(10 if info.field_name=='note' else 2) or '\x00' in value:raise ValueError('Use a visible reference/note without null bytes.')
        return value.strip()
    @model_validator(mode='after')
    def unique(self):
        if len({line.line_ref for line in self.lines})!=len(self.lines) or len({line.call_id for line in self.lines})!=len(self.lines):
            raise ValueError('Use distinct statement line references and one row per local call.')
        return self


class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


def projection(row):
    settled=row.status in ('completed','reconciled')
    if settled and (type(row.charged) is not int or not 0<=row.charged<=MAX_MONEY):
        fail(409,'BILLING_AMOUNT_UNSUPPORTED','A recorded charge exceeds the supported comparison range.')
    reference=(row.result or {}).get('provider_request_id')
    if type(reference) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}',reference):reference=None
    return {'call_id':row.id,'period':row.period,'status':row.status,'settled':settled,
        'charged_micro_usd':row.charged if settled else None,'input_tokens':row.input_tokens if settled else None,
        'output_tokens':row.output_tokens if settled else None,'provider_request_id':reference,
        'model_asset_id':row.asset_id,'model_asset_version':row.asset_version}


def calls_for(db,user,ids):
    return {row.id:row for row in db.scalars(select(InferenceCall).where(InferenceCall.id.in_(ids),
        InferenceCall.org_id==user.org_id,InferenceCall.env==runtime_environment(db,user.org_id)).execution_options(populate_existing=True))}


def compare_line(line,local):
    if not local['settled']:
        return {'line':line,'local':local,'status':'unresolved','amount_delta_micro_usd':None,
            'input_token_delta':None,'output_token_delta':None,'provider_request_id_match':None,'checked_fields':[]}
    delta=line['billed_micro_usd']-local['charged_micro_usd'];checked=['amount']
    ins=line.get('input_tokens');outs=line.get('output_tokens');ref=line.get('provider_request_id')
    input_delta=ins-local['input_tokens'] if ins is not None else None
    output_delta=outs-local['output_tokens'] if outs is not None else None
    ref_match=ref==local['provider_request_id'] if ref is not None else None
    if ins is not None:checked.append('input_tokens')
    if outs is not None:checked.append('output_tokens')
    if ref is not None:checked.append('provider_request_id')
    matches=delta==0 and input_delta in (None,0) and output_delta in (None,0) and ref_match is not False
    return {'line':line,'local':local,'status':'matched' if matches else 'discrepancy','amount_delta_micro_usd':delta,
        'input_token_delta':input_delta,'output_token_delta':output_delta,'provider_request_id_match':ref_match,'checked_fields':checked}


def record_for(db,id,user):
    row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==id,WorkbenchRun.kind==KIND,
        WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id)))
    if not row:fail(404,'BILLING_REVIEW_NOT_FOUND','Billing review is unavailable in this environment.')
    return row


def summary(row):
    result=row.result
    return {'id':row.id,'created':row.created,'status':row.status,'statement_ref':result['statement_ref'],
        'period':result['period'],'currency':'USD',**result['summary']}


def detail(db,row,user):
    ids=[item['line']['call_id'] for item in row.result['items']];calls=calls_for(db,user,ids)
    current=[projection(calls[id]) if id in calls else {'call_id':id,'unavailable':True} for id in ids]
    return {**summary(row),'note':row.result['note'],'items':row.result['items'],
        'stale':digest(canonical(current))!=row.result['local_fingerprint'],
        'scope':{'workspace_id':user.org_id,'environment':runtime_environment(db,user.org_id)},
        'provider_calls':0,'ledger_adjusted':False,'boundary':BOUNDARY}


def register_billing_reviews(app,factory,human):
    @app.get('/v1/billing-reviews')
    def listing(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db,False,'export')
            rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind==KIND,WorkbenchRun.org_id==user.org_id,
                WorkbenchRun.env==runtime_environment(db,user.org_id)).order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).offset(offset).limit(limit+1)).all()
            return {'items':[summary(row) for row in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None,'boundary':BOUNDARY}

    @app.get('/v1/billing-reviews/{id}')
    def inspect(id:str,request:Request):
        with factory() as db:
            user=human(request,db,False,'export');return detail(db,record_for(db,id,user),user)

    @app.post('/v1/billing-reviews/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'export')
            rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind==KIND,WorkbenchRun.author_id==user.id,
                WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id)))
            row=next((row for row in rows if row.result.get('key')==digest(body.key)),None)
            if not row:fail(404,'BILLING_REVIEW_NOT_FOUND','No billing review matches this account and key.')
            return detail(db,row,user)

    @app.post('/v1/billing-reviews',status_code=201)
    def create(body:Statement,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        key=digest(idempotency_key);fingerprint=digest(canonical(body.model_dump(exclude_none=True)))
        with factory.begin() as db:
            user=human(request,db,True,'members');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            existing=db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind==KIND,WorkbenchRun.author_id==user.id,
                WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id)))
            old=next((row for row in existing if row.result.get('key')==key),None)
            if old:
                if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another billing review.')
                return detail(db,old,user)
            calls=calls_for(db,user,[line.call_id for line in body.lines])
            if len(calls)!=len(body.lines) or any(row.period!=body.period for row in calls.values()):
                fail(404,'BILLING_CALL_NOT_FOUND','A selected call is unavailable in this environment and accounting month.')
            count=db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind==KIND,
                WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id)))
            if count>=200:fail(429,'BILLING_REVIEW_CAPACITY','This environment reached its bounded billing-review capacity.')
            snapshots=[projection(calls[line.call_id]) for line in body.lines]
            items=[compare_line(line.model_dump(exclude_none=True),local) for line,local in zip(body.lines,snapshots)]
            counts={status:sum(item['status']==status for item in items) for status in ('matched','discrepancy','unresolved')}
            totals={'line_count':len(items),'matched_lines':counts['matched'],'discrepancy_lines':counts['discrepancy'],'unresolved_lines':counts['unresolved'],
                'billed_total_micro_usd':sum(line.billed_micro_usd for line in body.lines),
                'recorded_settled_total_micro_usd':sum(local['charged_micro_usd'] for local in snapshots if local['settled']),
                'compared_billed_total_micro_usd':sum(item['line']['billed_micro_usd'] for item in items if item['local']['settled']),
                'settled_amount_delta_micro_usd':sum(item['amount_delta_micro_usd'] for item in items if item['amount_delta_micro_usd'] is not None)}
            row=WorkbenchRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,kind=KIND,
                status='matched' if counts['matched']==len(items) else 'review_required',duration_ms=0,
                result={'key':key,'fingerprint':fingerprint,'statement_ref':body.statement_ref,'period':body.period,'note':body.note,
                    'items':items,'summary':totals,'local_fingerprint':digest(canonical(snapshots))})
            db.add(row);db.flush();audit(db,user.org_id,user.id,'billing.statement_reviewed',detail={'review_id':row.id,'lines':len(items),'status':row.status})
            return detail(db,row,user)
