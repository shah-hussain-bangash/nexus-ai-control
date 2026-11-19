"""Persistent UI specifications. These endpoints never activate a runtime service."""
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import json
import math
import re
from datetime import date, datetime
from fastapi import Request
from pydantic import Field, StrictBool, model_validator
from sqlalchemy import select
from .runtime_context import runtime_environment
from .schemas import Strict
from .db import WorkspaceAsset, AssetRevision, public
from .security import fail
from .service import audit


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name('interface_catalog.json').read_text())


def definition(module):
    return next((item for item in catalog()['modules'] if item['id']==module),None)


class OperationalRecord(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    title: str = Field(min_length=1,max_length=120)
    owner: str = Field(min_length=1,max_length=120)
    state: str = Field(min_length=1,max_length=40)
    attributes: dict[str,str] = Field(max_length=20)


class OperationalEvent(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    record_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    command: str = Field(min_length=1,max_length=60)
    from_state: str = Field(min_length=1,max_length=40)
    to_state: str = Field(min_length=1,max_length=40)
    at: str = Field(min_length=1,max_length=40)
    note: str = Field(min_length=1,max_length=500)
    scenario: Literal['happy_path','permission_denied','dependency_unavailable','timeout_unknown','stale_revision']


class OperationalPlan(Strict):
    records: list[OperationalRecord] = Field(default_factory=list,max_length=50)
    events: list[OperationalEvent] = Field(default_factory=list,max_length=100)


class FunctionPlan(Strict):
    feature_id: str = Field(min_length=1,max_length=160)
    owner: str = Field(min_length=1,max_length=120)
    phase: Literal['planned','ui_reviewed','backend_in_progress','staging_review'] = 'planned'
    values: dict[str,str] = Field(max_length=10)
    checks: dict[str,StrictBool] = Field(max_length=4)
    notes: str = Field(default='',max_length=2000)


class Blueprint(Strict):
    module: str = Field(min_length=1,max_length=80)
    values: dict = Field(max_length=30)
    phase: Literal['planned','ui_reviewed','backend_in_progress','staging_review'] = 'planned'
    ui_checks: dict[str,StrictBool] = Field(default_factory=dict,max_length=20)
    surface_rows: list[dict] = Field(default_factory=list,max_length=30)
    operational_state: OperationalPlan = Field(default_factory=OperationalPlan)
    function_plans: list[FunctionPlan] = Field(default_factory=list,max_length=12)

    @model_validator(mode='after')
    def validate_interface(self):
        spec=definition(self.module)
        if not spec:raise ValueError('Unknown interface module.')
        feature_ids=set()
        for plan in self.function_plans:
            feature=next((f for f in spec['features'] if f['id']==plan.feature_id),None)
            if not feature or plan.feature_id in feature_ids:raise ValueError('Use distinct function plans from this module.')
            feature_ids.add(plan.feature_id)
            if not plan.owner.strip() or set(plan.checks)!={'scope','access','feedback','handoff'}:raise ValueError('Supply an owner and exactly four UI review checks.')
            if plan.phase!='planned' and not all(plan.checks.values()):raise ValueError('Review all UI criteria before advancing the function planning phase.')
            if set(plan.values)!={f['id'] for f in feature['fields']}:raise ValueError('Use exactly the function screen fields.')
            for f in feature['fields']:
                value=plan.values[f['id']]
                if not value.strip() or len(value)>2000:raise ValueError('Function controls require 1–2,000 characters.')
                if f['type']=='select' and value not in f['options']:raise ValueError('Unknown function screen option.')
                if f['type']=='number':
                    try:n=float(value)
                    except ValueError:raise ValueError('Use numeric function values.')
                    if not math.isfinite(n) or not f.get('min',0)<=n<=f.get('max',1000000000):raise ValueError('Function numeric value is out of range.')
                if f['type']=='reference' and not re.fullmatch(r'(env:[A-Z][A-Z0-9_]{2,70}|secret://[A-Za-z0-9/_-]{3,180})',value):raise ValueError('Use secret references only in function plans.')
                if f['type']=='url':
                    parsed=urlsplit(value)
                    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):raise ValueError('Use a credential-free HTTPS function endpoint.')
                if f['type']=='json':
                    try:payload=json.loads(value)
                    except ValueError:raise ValueError('Use valid function JSON.')
                    if not isinstance(payload,dict):raise ValueError('Use a JSON object in function screens.')
                if f['type']=='date':
                    try:date.fromisoformat(value)
                    except ValueError:raise ValueError('Use an ISO calendar date in function screens.')
        operations=spec['operations']; ids=set(); state_by_id={}
        states={operations['initial_state']} | {x for c in operations['commands'] for x in c['from_states']} | {c['to_state'] for c in operations['commands']}
        for row in self.operational_state.records:
            if row.id in ids or not row.title.strip() or not row.owner.strip() or row.state not in states:raise ValueError('Invalid operational record identity or state.')
            ids.add(row.id);state_by_id[row.id]=operations['initial_state']
            if set(row.attributes)!={f['id'] for f in operations['fields']}:raise ValueError('Use exactly the operational form fields.')
            for f in operations['fields']:
                value=row.attributes[f['id']]
                if not value.strip() or len(value)>2000:raise ValueError('Operational fields require 1–2,000 characters.')
                if f['type']=='select' and value not in f['options']:raise ValueError('Unknown operational option.')
                if f['type']=='reference' and not re.fullmatch(r'(env:[A-Z][A-Z0-9_]{2,70}|secret://[A-Za-z0-9/_-]{3,180})',value):raise ValueError('Use secret references only.')
                if f['type']=='number':
                    try:n=float(value)
                    except ValueError:raise ValueError('Use numeric operational values.')
                    if not math.isfinite(n) or not f.get('min',0)<=n<=f.get('max',1000000000):raise ValueError('Operational numeric value is out of range.')
                if f['type']=='json':
                    try:payload=json.loads(value)
                    except ValueError:raise ValueError('Use a valid JSON object.')
                    if not isinstance(payload,dict):raise ValueError('Use a JSON object for tool schemas.')
                if f['type']=='url':
                    parsed=urlsplit(value)
                    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):raise ValueError('Use a credential-free HTTPS endpoint.')
                if f['type']=='email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise ValueError('Use a valid review email.')
                if f['type']=='date':
                    try:date.fromisoformat(value)
                    except ValueError:raise ValueError('Use an ISO calendar date.')
        event_ids=set()
        for event in self.operational_state.events:
            if event.id in event_ids or event.record_id not in ids or not event.note.strip():raise ValueError('Invalid operational event reference.')
            event_ids.add(event.id)
            try:timestamp=datetime.fromisoformat(event.at.replace('Z','+00:00'))
            except ValueError:raise ValueError('Use an ISO event timestamp.')
            if timestamp.tzinfo is None:raise ValueError('Event timestamp requires a timezone.')
            command=next((c for c in operations['commands'] if c['id']==event.command),None)
            current=state_by_id[event.record_id]
            if not command or current!=event.from_state or current not in command['from_states']:raise ValueError('Operational event is not a valid state transition.')
            target=command['to_state'] if event.scenario=='happy_path' else current
            if event.to_state!=target:raise ValueError('Failed UI scenarios must preserve the record state.')
            state_by_id[event.record_id]=target
        if any(state_by_id[row.id]!=row.state for row in self.operational_state.records):raise ValueError('Operational states must match their review event history.')
        expected={field['id'] for field in spec['fields']}
        if set(self.values)!=expected:raise ValueError('Use exactly the defined interface fields.')
        for field in spec['fields']:
            value=self.values[field['id']];kind=field['type']
            if kind=='toggle':
                if type(value) is not bool:raise ValueError('Use a boolean control value.')
            elif kind=='number':
                if type(value) not in (int,float) or not math.isfinite(value) or not field['min']<=value<=field['max']:raise ValueError('Numeric control is out of range.')
            elif kind=='list':
                if not isinstance(value,list) or not 1<=len(value)<=30 or any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in value):raise ValueError('List controls need 1–30 short values.')
                self.values[field['id']]=[x.strip() for x in value]
            else:
                if not isinstance(value,str) or not value.strip() or len(value)>1000:raise ValueError('Use a nonempty, bounded text value.')
                value=value.strip();self.values[field['id']]=value
                if kind=='select' and value not in field['options']:raise ValueError('Select a defined option.')
                if kind=='reference' and not re.fullmatch(r'(env:[A-Z][A-Z0-9_]{2,70}|secret://[A-Za-z0-9/_-]{3,180})',value):raise ValueError('Use a secret reference, never a secret value.')
                if kind=='url':
                    parsed=urlsplit(value)
                    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):raise ValueError('Use a credential-free HTTPS endpoint without query/fragment.')
        seen=set();column_ids={c['id'] for c in spec['record_columns']}
        for row in self.surface_rows:
            if set(row)!={'id','state','values'} or not isinstance(row['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',row['id']) or row['id'] in seen:raise ValueError('Use distinct preview-record identifiers.')
            seen.add(row['id'])
            if row['state'] not in spec['record_states'] or not isinstance(row['values'],dict) or set(row['values'])!=column_ids:raise ValueError('Preview record does not match the operational interface.')
            for col in spec['record_columns']:
                value=row['values'][col['id']]
                if not isinstance(value,str) or not value.strip() or len(value)>250:raise ValueError('Preview metadata must be nonempty and at most 250 characters.')
                if col['type']=='reference' and not re.fullmatch(r'(env:[A-Z][A-Z0-9_]{2,70}|secret://[A-Za-z0-9/_-]{3,180})',value):raise ValueError('Preview records accept secret references only.')
        criteria={c['id'] for c in spec['criteria']}
        if set(self.ui_checks)-criteria:raise ValueError('Unknown interface review criterion.')
        if self.phase!='planned' and not all(self.ui_checks.get(key,False) for key in criteria):raise ValueError('Review every interface criterion before advancing its planning phase.')
        return self


def preview(config,action='',scenario='happy_path'):
    obj=Blueprint.model_validate(config);spec=definition(obj.module)
    command=next((a for a in spec['actions'] if a['id']==action),None)
    if scenario not in ('happy_path','invalid_configuration','permission_denied','dependency_unavailable','timeout_unknown','stale_revision'):fail(422,'UNKNOWN_DESIGN_SCENARIO','Choose a defined interface review scenario.')
    if action and not command:fail(422,'UNKNOWN_DESIGN_ACTION','Choose an action defined in this interface module.')
    return {'module':obj.module,'title':spec['title'],'action':command['label'] if command else 'Full interface journey','scenario':scenario,'steps':[{'id':s['id'],'label':s['label'],'status':('design_checked' if scenario=='happy_path' or i<2 else 'simulated_stop' if i==2 else 'not_simulated'),'detail':s['description'] if scenario=='happy_path' or i<2 else 'Interface scenario: '+scenario.replace('_',' ')+'. No runtime operation was attempted.'} for i,s in enumerate(spec['stages'])],'configured_fields':len(obj.values),'reviewed_criteria':sum(obj.ui_checks.values()),'total_criteria':len(spec['criteria']),'planned_contract':command,'runtime_activated':False,'provider_calls':0,'business_effects':0,'boundary':'Interface design preview only. No runtime job, provider call, cloud deployment or business effect was performed.'}


def register_interfaces(app,factory,settings,human):
    @app.get('/v1/interface-catalog')
    def listing(request:Request):
        with factory() as db:
            human(request,db)
            return catalog()

    @app.post('/v1/interface-starter')
    def starter(request:Request):
        if settings.mode!='local':fail(403,'LOCAL_ONLY','Synthetic interface examples are local-only.')
        with factory.begin() as db:
            user=human(request,db,True,'policy');created=0
            environment=runtime_environment(db,user.org_id)
            for spec in catalog()['modules']:
                exists=db.scalar(select(WorkspaceAsset.id).where(WorkspaceAsset.org_id==user.org_id,WorkspaceAsset.env==environment,WorkspaceAsset.kind=='blueprint',WorkspaceAsset.name==spec['sample_name']))
                if exists:continue
                config=Blueprint(module=spec['id'],values={f['id']:f['default'] for f in spec['fields']}).model_dump()
                row=WorkspaceAsset(org_id=user.org_id,env=environment,kind='blueprint',name=spec['sample_name'],description=spec['description'],config=config,author_id=user.id)
                db.add(row);db.flush()
                db.add(AssetRevision(org_id=user.org_id,env=row.env,asset_id=row.id,version=row.version,snapshot=public(row),author_id=user.id));created+=1
            audit(db,user.org_id,user.id,'interface.examples_loaded',detail={'created':created,'runtime_activated':False})
            return {'created':created,'runtime_activated':False,'synthetic':True}
