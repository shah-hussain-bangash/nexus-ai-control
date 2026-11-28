"""Explicit local design copying, with actor/source-scoped durable receipts."""
from typing import Literal
import re
from fastapi import Request,Header,Query
from pydantic import Field,field_validator
from sqlalchemy import select,func
from .db import WorkspaceAsset,AssetRevision,WorkbenchRun,WorkspaceEnvironment,EnvironmentAssignment,uid,now
from .schemas import Strict
from .security import fail,digest
from .runtime_context import runtime_environment,switching_enabled
from .service import audit,canonical
from .workbench import asset_for,validate_config

KIND='environment_asset_copy'
ALLOWED=('prompt','guardrail','workflow','model','connector')
RESET_FIELDS={'model':['credential_ref'],'connector':['credential_ref','scopes','read_only']}
REFERENCE_KINDS={'retrieve':'knowledge','prompt':'prompt','guardrail':'guardrail'}

class ReferenceMapping(Strict):
    node_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    target_asset_id:str=Field(min_length=1,max_length=64)
    expected_target_asset_version:int=Field(ge=1,strict=True)

class CopyInput(Strict):
    source_asset_id:str=Field(min_length=1,max_length=100)
    expected_source_version:int=Field(ge=1,strict=True)
    target_environment:str=Field(pattern=r'^[a-z][a-z0-9-]{1,31}$')
    expected_target_version:int=Field(ge=1,strict=True)
    name:str=Field(min_length=2,max_length=120)
    note:str=Field(min_length=5,max_length=500)
    reviewed:Literal[True]
    reference_mappings:list[ReferenceMapping]=Field(default_factory=list,max_length=12)

    @field_validator('name','note')
    @classmethod
    def visible(cls,value,info):
        if len(value.strip())<(2 if info.field_name=='name' else 5) or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Use visible text on one line.')
        return value.strip()

class ReceiptKey(Strict):
    key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')

def receipt_id(actor,environment,key):
    return digest(canonical([KIND,actor.org_id,actor.id,environment,key]))

def receipt(db,actor,environment,key):
    return db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==receipt_id(actor,environment,key),WorkbenchRun.org_id==actor.org_id,
        WorkbenchRun.env==environment,WorkbenchRun.author_id==actor.id,WorkbenchRun.kind==KIND))

def capacity(db,org):
    if db.scalar(select(func.count()).select_from(WorkbenchRun.__table__).where(WorkbenchRun.__table__.c.org_id==org,WorkbenchRun.__table__.c.kind==KIND))>=1000:
        fail(429,'COPY_CAPACITY','This workspace has reached its capacity of 1000 copy/cancellation receipts.')

def outcome(db,actor,row):
    result=row.result
    if result['status']=='copied' and not db.get(EnvironmentAssignment,(actor.id,actor.org_id,result['target_environment'])):
        fail(403,'ENVIRONMENT_ACCESS_DENIED','Target environment access is unavailable to your account.')
    return {'id':row.id,**{k:v for k,v in result.items() if k!='fingerprint'}}

def request_fingerprint(body):
    values=body.model_dump()
    # Keep pre-workflow receipts and browser retry bodies compatible. The new
    # optional empty field must not change their original request fingerprint.
    if not values['reference_mappings']:values.pop('reference_mappings')
    return digest(canonical(values))

def mapped_config(db,actor,source,target,body):
    config=validate_config(source.kind,source.config)
    if source.kind!='workflow':
        if body.reference_mappings:fail(422,'UNEXPECTED_REFERENCE_MAPPING','Only workflow designs accept reference mappings.')
        if source.kind in RESET_FIELDS:
            config['credential_ref']=''
            if source.kind=='connector':config['scopes']=[];config['read_only']=True
            config=validate_config(source.kind,config)
        return config,[]
    nodes={node['id']:node for node in config['nodes'] if node['ref_id']}
    mappings={row.node_id:row for row in body.reference_mappings}
    if len(mappings)!=len(body.reference_mappings) or set(mappings)!=set(nodes):
        fail(422,'REFERENCE_MAPPING_REQUIRED','Map every referenced workflow step exactly once; do not include unrelated steps.')
    provenance=[];table=WorkspaceAsset.__table__
    for node_id,node in nodes.items():
        expected_kind=REFERENCE_KINDS.get(node['kind'])
        if not expected_kind:fail(422,'INVALID_REFERENCE','Only retrieval, prompt and guardrail steps may reference designs.')
        original=asset_for(db,actor,node['ref_id'])
        if original.kind!=expected_kind or original.status!='validated' or original.version!=node['ref_version']:
            fail(409,'SOURCE_CHANGED','A pinned source dependency changed or needs validation. Refresh and validate the workflow again.')
        mapping=mappings[node_id]
        linked=db.execute(select(table.c.id,table.c.kind,table.c.version,table.c.status).where(table.c.id==mapping.target_asset_id,table.c.org_id==actor.org_id,table.c.env==target.key)).mappings().first()
        if not linked or linked['kind']!=expected_kind or linked['status']!='validated':
            fail(422,'INVALID_TARGET_REFERENCE','Select a validated target design of the matching step type.')
        if linked['version']!=mapping.expected_target_asset_version:fail(409,'STALE_VERSION','A selected target dependency changed. Refresh and review the mappings again.')
        provenance.append({'node_id':node_id,'kind':expected_kind,'source_asset_id':original.id,'source_version':original.version,
                           'target_asset_id':linked['id'],'target_version':linked['version']})
        node['ref_id']=linked['id'];node['ref_version']=linked['version']
    return validate_config('workflow',config),provenance

def register_environment_asset_copy(app,factory,settings,human):
    def owner(request,db,write=True):
        if not switching_enabled(settings):fail(403,'LOCAL_ONLY','Reviewed design copying is available only in local mode.')
        return human(request,db,write,'members')

    @app.get('/v1/environment-asset-copies/target/{key}/references')
    def references(key:str,request:Request,expected_version:int=Query(ge=1)):
        with factory() as db:
            actor=owner(request,db,False)
            if key==runtime_environment(db,actor.org_id):fail(422,'COPY_TARGET_REQUIRED','Select a different target environment.')
            target=db.get(WorkspaceEnvironment,(actor.org_id,key))
            if not target or target.state!='active' or not db.get(EnvironmentAssignment,(actor.id,actor.org_id,key)):
                fail(403,'ENVIRONMENT_ACCESS_DENIED','You must be assigned to an active target environment.')
            if target.version!=expected_version:fail(409,'STALE_VERSION','Target environment changed. Refresh before choosing references.')
            table=WorkspaceAsset.__table__
            rows=db.execute(select(table.c.id,table.c.kind,table.c.name,table.c.version).where(table.c.org_id==actor.org_id,table.c.env==key,
                table.c.kind.in_(tuple(REFERENCE_KINDS.values())),table.c.status=='validated').order_by(table.c.kind,table.c.name,table.c.id).limit(501)).mappings().all()
            if len(rows)>500:fail(422,'TARGET_REFERENCE_CAPACITY','This bounded review supports up to 500 target reference designs.')
            return {'items':[dict(row) for row in rows],'target_environment':key,'target_version':target.version,
                    'boundary':'Reference metadata only. No configuration, content, credentials or linked designs are copied by this lookup.'}

    @app.post('/v1/environment-asset-copies/recover')
    def recover(body:ReceiptKey,request:Request):
        with factory.begin() as db:
            actor=owner(request,db);environment=runtime_environment(db,actor.org_id)
            old=receipt(db,actor,environment,body.key)
            if not old:fail(404,'COPY_NOT_FOUND','No receipt matches this account, source environment and key. Recover again or cancel the pending intent before starting a new copy.')
            return outcome(db,actor,old)

    @app.post('/v1/environment-asset-copies/cancel')
    def cancel(body:ReceiptKey,request:Request):
        with factory.begin() as db:
            actor=owner(request,db);environment=runtime_environment(db,actor.org_id)
            old=receipt(db,actor,environment,body.key)
            if old:return outcome(db,actor,old)
            capacity(db,actor.org_id)
            old=WorkbenchRun(id=receipt_id(actor,environment,body.key),org_id=actor.org_id,env=environment,kind=KIND,status='cancelled',duration_ms=0,author_id=actor.id,result={'status':'cancelled','source_environment':environment})
            db.add(old)
            audit(db,actor.org_id,actor.id,'environment.asset_copy_cancelled',detail={'receipt_id':old.id})
            return outcome(db,actor,old)

    @app.post('/v1/environment-asset-copies',status_code=201)
    def copy(body:CopyInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a unique 16–100 character copy key; retain it after uncertainty.')
        key=idempotency_key
        with factory.begin() as db:
            actor=owner(request,db);source_environment=runtime_environment(db,actor.org_id)
            fingerprint=request_fingerprint(body)
            old=receipt(db,actor,source_environment,key)
            if old:
                if old.result['status']=='cancelled':fail(409,'COPY_CANCELLED','This copy intent was cancelled. It cannot create an asset.')
                if old.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different reviewed copy.')
                return outcome(db,actor,old)
            if body.target_environment==source_environment:fail(422,'COPY_TARGET_REQUIRED','Select a different active local environment.')
            target=db.get(WorkspaceEnvironment,(actor.org_id,body.target_environment),with_for_update=True)
            if not target or target.state!='active' or not db.get(EnvironmentAssignment,(actor.id,actor.org_id,body.target_environment)):
                fail(403,'ENVIRONMENT_ACCESS_DENIED','You must be assigned to an active target environment.')
            if target.version!=body.expected_target_version:fail(409,'STALE_VERSION','Target environment changed. Refresh and review again.')
            source=asset_for(db,actor,body.source_asset_id)
            if source.kind not in ALLOWED:fail(422,'COPY_KIND_UNAVAILABLE','Copy supports prompt, guardrail, remapped workflow and reset model/connector drafts only.')
            if source.version!=body.expected_source_version or source.status!='validated':fail(409,'SOURCE_CHANGED','Validate and refresh the exact source design before copying.')
            config,reference_provenance=mapped_config(db,actor,source,target,body)
            capacity(db,actor.org_id)
            assets=WorkspaceAsset.__table__
            if db.scalar(select(func.count()).select_from(assets).where(assets.c.org_id==actor.org_id,assets.c.env==target.key))>=500:
                fail(429,'COPY_TARGET_CAPACITY','The target environment has reached its limit of 500 design records for copying.')
            # Deliberate control-plane insert. Never retarget the bound runtime
            # session, reuse source IDs, overwrite target records or copy history.
            timestamp=now();asset_id=uid()
            values={'id':asset_id,'org_id':actor.org_id,'env':target.key,'kind':source.kind,'name':body.name,'description':source.description,
                    'status':'draft','version':1,'config':config,'created':timestamp,'updated':timestamp,'author_id':actor.id}
            db.execute(assets.insert().values(**values))
            origin={'environment':source_environment,'asset_id':source.id,'version':source.version}
            if reference_provenance:origin['references']=reference_provenance
            if source.kind in RESET_FIELDS:origin['reset_fields']=list(RESET_FIELDS[source.kind])
            db.execute(AssetRevision.__table__.insert().values(id=uid(),org_id=actor.org_id,env=target.key,asset_id=asset_id,version=1,
                snapshot={**values,'copied_from':origin},author_id=actor.id,created=timestamp))
            result={'status':'copied','source_environment':source_environment,'source_asset_id':source.id,'source_version':source.version,
                    'target_environment':target.key,'target_asset_id':asset_id,'target_created_version':1,'kind':source.kind,'name':body.name,'fingerprint':fingerprint}
            if reference_provenance:result['reference_mappings']=reference_provenance
            if source.kind in RESET_FIELDS:result['reset_fields']=list(RESET_FIELDS[source.kind])
            record=WorkbenchRun(id=receipt_id(actor,source_environment,key),org_id=actor.org_id,env=source_environment,kind=KIND,status='completed',duration_ms=0,author_id=actor.id,result=result)
            db.add(record)
            audit(db,actor.org_id,actor.id,'environment.asset_copied',detail={'receipt_id':record.id,'source':origin,'target_environment':target.key,
                'target_asset_id':asset_id,'target_version':1,'status':'draft','note':body.note,**({'reset_fields':list(RESET_FIELDS[source.kind])} if source.kind in RESET_FIELDS else {})})
            return outcome(db,actor,record)
