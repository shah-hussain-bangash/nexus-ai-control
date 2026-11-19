"""Tenant-scoped AI design assets and bounded, deterministic local workbenches.

No provider credentials are accepted, no external endpoint is contacted, and no
workflow dry run authorizes a business effect. Existing governed actions remain
the sole dispatch path for the synthetic business connector.
"""
import math
import hashlib
import re
import time
from collections import Counter
from typing import Literal
from urllib.parse import urlsplit
from fastapi import Request
from pydantic import Field, ValidationError, field_validator
from sqlalchemy import select, update, func
from .schemas import Strict
from .db import WorkspaceAsset, AssetRevision, WorkbenchRun, Action, CURRENT_SCHEMA, now, public
from .security import fail, permit
from .service import audit, active_policy
from .policy import evaluate
from .runtime_context import runtime_environment

Kind = Literal['workflow', 'prompt', 'model', 'knowledge', 'connector', 'guardrail', 'benchmark', 'budget', 'release', 'blueprint']


class Node(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    kind: Literal['input','retrieve','prompt','guardrail','policy','approval','tool','verify','output']
    label: str = Field(min_length=1,max_length=70)
    ref_id: str = Field(default='',max_length=64)
    ref_version: int | None = Field(default=None,ge=1)


class Workflow(Strict):
    nodes: list[Node] = Field(min_length=2,max_length=12)
    description: str = Field(default='',max_length=500)


class Prompt(Strict):
    template: str = Field(min_length=3,max_length=12000)
    required_terms: list[str] = Field(default_factory=list,max_length=20)
    forbidden_terms: list[str] = Field(default_factory=list,max_length=20)


class Model(Strict):
    provider: Literal['Azure OpenAI','OpenAI','Anthropic','Local endpoint']
    model: str = Field(min_length=1,max_length=100)
    endpoint: str = Field(default='',max_length=300)
    credential_ref: str = Field(default='',max_length=90)
    token_limit: int = Field(default=4096,ge=128,le=128000)
    timeout_ms: int = Field(default=30000,ge=1000,le=120000)
    temperature: float = Field(default=0.2,ge=0,le=2,allow_inf_nan=False)


class Knowledge(Strict):
    content: str = Field(min_length=10,max_length=24000)
    source: str = Field(default='Workspace document',max_length=300)
    language: Literal['English','Arabic','Bilingual'] = 'English'
    chunk_size: int = Field(default=700,ge=200,le=2000)


class Connector(Strict):
    protocol: Literal['REST','MCP','Webhook','Database'] = 'REST'
    endpoint: str = Field(default='',max_length=300)
    credential_ref: str = Field(default='',max_length=90)
    scopes: list[str] = Field(default_factory=list,max_length=20)
    read_only: bool = True


class Guardrail(Strict):
    blocked_terms: list[str] = Field(default_factory=list,max_length=30)
    detect_email: bool = True
    detect_override: bool = True
    mode: Literal['block','redact'] = 'block'


class BenchmarkCase(Strict):
    query: str = Field(min_length=2,max_length=500)
    expected_title: str = Field(min_length=2,max_length=120)


class Benchmark(Strict):
    cases: list[BenchmarkCase] = Field(min_length=1,max_length=30)
    top_k: int = Field(default=3,ge=1,le=5)


class Budget(Strict):
    monthly_limit: float = Field(default=500,ge=0,le=10000000,allow_inf_nan=False)
    input_per_million: float = Field(default=1,ge=0,le=10000,allow_inf_nan=False)
    output_per_million: float = Field(default=3,ge=0,le=10000,allow_inf_nan=False)
    currency: Literal['USD'] = 'USD'


class Release(Strict):
    target: Literal['Local','AWS','Azure','Kubernetes'] = 'Local'
    artifact: str = Field(default='nexus-control-plane',min_length=1,max_length=120)
    rollback: str = Field(min_length=5,max_length=2000)
    checks: list[str] = Field(default_factory=list,max_length=20)


from .interfaces import Blueprint

MODELS = dict(workflow=Workflow,prompt=Prompt,model=Model,knowledge=Knowledge,connector=Connector,
              guardrail=Guardrail,benchmark=Benchmark,budget=Budget,release=Release,blueprint=Blueprint)


class AssetInput(Strict):
    kind: Kind
    name: str = Field(min_length=2,max_length=120)
    description: str = Field(default='',max_length=500)
    config: dict

    @field_validator('name')
    @classmethod
    def clean_name(cls,value):
        value=value.strip()
        if len(value)<2:raise ValueError('Use a name with at least two visible characters.')
        return value


class AssetUpdate(AssetInput):
    expected_version: int = Field(ge=1)


class VersionInput(Strict):
    expected_version: int = Field(ge=1)


class RunInput(Strict):
    query: str = Field(default='',max_length=2000)
    amount: float = Field(default=12500,ge=0.01,le=99999999,allow_inf_nan=False)
    variables: dict[str,str] = Field(default_factory=dict,max_length=20)
    input_tokens: int = Field(default=100000,ge=0,le=1000000000)
    output_tokens: int = Field(default=20000,ge=0,le=1000000000)


def validate_config(kind, data):
    try:
        obj = MODELS[kind].model_validate(data)
        config = obj.model_dump()
    except (ValidationError, KeyError):
        fail(422,'INVALID_CONFIGURATION','Configuration does not match this asset type. Check field names, ranges and required values.')
    for key in ('blocked_terms','required_terms','forbidden_terms','scopes','checks'):
        if key in config and any(not x.strip() or len(x)>150 for x in config[key]):
            fail(422,'INVALID_CONFIGURATION','List values must be nonempty and at most 150 characters.')
    if kind in ('model','connector'):
        if config['credential_ref'] and not re.fullmatch(r'env:[A-Z][A-Z0-9_]{2,70}',config['credential_ref']):
            fail(422,'SECRET_REFERENCE_REQUIRED','Use an env:VARIABLE_NAME reference. Never enter a credential value.')
        if config['endpoint']:
            u=urlsplit(config['endpoint'])
            if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:
                fail(422,'INVALID_ENDPOINT','Use an HTTPS endpoint without credentials, query parameters or a fragment. It will not be contacted.')
    if kind=='workflow':
        nodes=config['nodes']; kinds=[n['kind'] for n in nodes]
        if len({n['id'] for n in nodes})!=len(nodes) or kinds[0]!='input' or kinds[-1]!='output' or kinds.count('input')!=1 or kinds.count('output')!=1:
            fail(422,'INVALID_WORKFLOW','Use unique step IDs, one Input first and one Output last.')
        for i,k in enumerate(kinds):
            if k=='tool':
                policies=[j for j in range(i) if kinds[j]=='policy']
                if not policies or not any(kinds[j]=='approval' for j in range(policies[-1]+1,i)) or 'verify' not in kinds[i+1:]:
                    fail(422,'UNGUARDED_TOOL','A tool step needs Policy then Approval before it, and Verify after it.')
    return config


def asset_context(db,user,row):
    environment=runtime_environment(db,user.org_id)
    if not user.active or row.org_id!=user.org_id or row.env!=environment:fail(404,'NOT_FOUND','Asset not found in this workspace.')
    return environment


def asset_for(db,user,id):
    row=db.scalar(select(WorkspaceAsset).where(WorkspaceAsset.id==id,WorkspaceAsset.org_id==user.org_id,WorkspaceAsset.env==runtime_environment(db,user.org_id)))
    if not row: fail(404,'NOT_FOUND','Asset not found in this workspace.')
    asset_context(db,user,row)
    return row


def validate_references(db,user,kind,config):
    if kind=='workflow':
        for node in config['nodes']:
            if node['ref_id']:
                ref=asset_for(db,user,node['ref_id'])
                expected={'retrieve':'knowledge','prompt':'prompt','guardrail':'guardrail'}.get(node['kind'])
                if not expected or ref.kind!=expected or ref.status=='archived':
                    fail(422,'INVALID_REFERENCE','A workflow step must reference an available asset of the matching type.')
                if node['ref_version'] is None:
                    fail(422,'REFERENCE_VERSION_REQUIRED','Pin the referenced asset version before saving this workflow.')
                if node['ref_version']!=ref.version:
                    fail(409,'REFERENCE_CHANGED','A referenced asset changed. Review and pin its current version in the workflow before running.')


def snapshot(db,row,user):
    db.add(AssetRevision(org_id=user.org_id,env=asset_context(db,user,row),asset_id=row.id,version=row.version,snapshot=public(row),author_id=user.id))


def chunks(db,org,environment=None):
    environment=runtime_environment(db,org,environment)
    docs=db.scalars(select(WorkspaceAsset).where(WorkspaceAsset.org_id==org,WorkspaceAsset.env==environment,WorkspaceAsset.kind=='knowledge',WorkspaceAsset.status!='archived').order_by(WorkspaceAsset.created.desc()).limit(100)).all()
    result=[]
    for doc in docs:
        text=doc.config['content'];size=doc.config['chunk_size']
        for i,start in enumerate(range(0,len(text),size-80)):
            excerpt=text[start:start+size]
            result.append({'asset_id':doc.id,'asset_version':doc.version,'title':doc.name,'source':doc.config['source'],'chunk':i+1,'text':excerpt,'sha256':hashlib.sha256(excerpt.encode()).hexdigest()})
            if len(result)>=2000:return result
    return result


def retrieve(db,org,query,top_k=5,only=None,environment=None):
    corpus=[x for x in chunks(db,org,environment) if not only or x['asset_id']==only]
    terms=list(dict.fromkeys(re.findall(r'\w+',query.casefold())))[:64]
    if not terms or not corpus:return []
    tokens=[Counter(re.findall(r'\w+',c['text'].casefold())) for c in corpus]
    avg=sum(sum(t.values()) for t in tokens)/len(tokens) or 1
    df={q:sum(q in t for t in tokens) for q in terms}
    ranked=[]
    for c,t in zip(corpus,tokens):
        score=0
        for q in terms:
            f=t[q]
            if f:score+=math.log(1+(len(tokens)-df[q]+.5)/(df[q]+.5))*f*2.2/(f+1.2*(.25+.75*sum(t.values())/avg))
        if score>0:ranked.append({**c,'score':round(score,4)})
    return sorted(ranked,key=lambda x:(-x['score'],x['asset_id'],x['chunk']))[:top_k]


def check_guardrail(text,config):
    hits=[];redacted=text
    for term in config['blocked_terms']:
        if term.casefold() in text.casefold():
            hits.append('blocked_term');redacted=re.sub(re.escape(term),'[REDACTED]',redacted,flags=re.I)
    if config['detect_email'] and re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}',text):
        hits.append('email');redacted=re.sub(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}','[EMAIL]',redacted)
    if config['detect_override'] and re.search(r'ignore\s+(all\s+)?(previous|prior|system)\s+instructions',text,re.I):
        hits.append('instruction_override');redacted=re.sub(r'ignore\s+(all\s+)?(previous|prior|system)\s+instructions','[OVERRIDE]',redacted,flags=re.I)
    return {'signals':sorted(set(hits)),'verdict':('blocked' if config['mode']=='block' else 'redacted') if hits else 'passed','output':redacted if config['mode']=='redact' else ('' if hits else text),'boundary':'Deterministic local checks; not a comprehensive safety classifier.'}


def execute_preview(db,user,row,body,settings):
    asset_context(db,user,row)
    validate_references(db,user,row.kind,row.config)
    c=row.config
    if row.kind=='blueprint':
        from .interfaces import preview
        return 'completed',preview(c,body.variables.get('design_action',''),body.variables.get('design_scenario','happy_path'))
    if row.kind=='prompt':
        values={**body.variables,'query':body.query,'question':body.query}
        names=set(re.findall(r'{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}',c['template']))
        missing=sorted(names-set(values))
        if missing:fail(422,'MISSING_VARIABLES','Provide variables: '+', '.join(missing))
        rendered=re.sub(r'{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}',lambda m:values[m[1]],c['template'])
        checks=[{'name':'Contains: '+s,'passed':s.casefold() in rendered.casefold()} for s in c['required_terms']]
        checks += [{'name':'Excludes: '+s,'passed':s.casefold() not in rendered.casefold()} for s in c['forbidden_terms']]
        return 'completed',{'rendered':rendered,'checks':checks,'boundary':'Template rendering and deterministic assertions. No model was called.'}
    if row.kind=='knowledge':
        return 'completed',{'citations':retrieve(db,user.org_id,body.query,only=row.id),'retrieval':'BM25 lexical ranking','boundary':'Source excerpts only. No generated answer or embedding provider.'}
    if row.kind=='guardrail':return 'completed',check_guardrail(body.query,c)
    if row.kind=='benchmark':
        cases=[]
        for case in c['cases']:
            hits=retrieve(db,user.org_id,case['query'],c['top_k'])
            cases.append({**case,'passed':any(case['expected_title'].casefold()==hit['title'].casefold() for hit in hits),'retrieved_titles':list(dict.fromkeys(h['title'] for h in hits))})
        return 'completed',{'cases':cases,'passed':sum(x['passed'] for x in cases),'total':len(cases),'metric':f"Title recall at {c['top_k']}",'boundary':'Deterministic retrieval benchmark over available workspace documents.'}
    if row.kind=='budget':
        estimate=(body.input_tokens*c['input_per_million']+body.output_tokens*c['output_per_million'])/1000000
        return 'completed',{'estimated_cost':round(estimate,6),'currency':'USD','monthly_limit':c['monthly_limit'],'over_budget':estimate>c['monthly_limit'],'input_tokens':body.input_tokens,'output_tokens':body.output_tokens,'boundary':'Planning estimate using your rates. No provider usage fetched and no spend limit enforced.'}
    if row.kind=='workflow':
        events=[];blocked=False;decision='not_evaluated';query=body.query;context='';rendered='';citations=[];references=[]
        for node in c['nodes']:
            kind=node['kind'];detail='';status='previewed'
            if blocked:status='not_executed';detail='A preceding gate stopped this preview.'
            elif kind=='input':detail=f'Accepted {len(body.query)} input characters.'
            elif kind=='retrieve':
                hits=retrieve(db,user.org_id,query,3,only=node['ref_id'] or None);detail=f'{len(hits)} source chunks retrieved.'
                citations=hits;context='\n\n'.join(f"[{h['title']} / chunk {h['chunk']} / v{h['asset_version']}] {h['text']}" for h in hits)
            elif kind=='prompt':
                prompt=asset_for(db,user,node['ref_id']) if node['ref_id'] else None
                template=prompt.config['template'] if prompt else 'Question: {{question}}\nEvidence: {{context}}'
                values={'query':query,'question':query,'context':context}
                names=set(re.findall(r'{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}',template))
                if names-set(values):fail(422,'MISSING_VARIABLES','The linked prompt needs variables unavailable in this workflow preview.')
                rendered=re.sub(r'{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}',lambda m:values[m[1]],template)
                detail='Prompt rendered from retrieved evidence. No language model called.'
            elif kind=='guardrail':
                rules=[asset_for(db,user,node['ref_id'])] if node['ref_id'] else db.scalars(select(WorkspaceAsset).where(WorkspaceAsset.org_id==user.org_id,WorkspaceAsset.env==runtime_environment(db,user.org_id),WorkspaceAsset.kind=='guardrail',WorkspaceAsset.status!='archived')).all()
                signals=[]
                for rule in rules:
                    signal=check_guardrail(query,rule.config);signals.append(signal)
                    if signal['verdict']=='redacted':query=signal['output']
                blocked=any(r['verdict']=='blocked' for r in signals)
                status='blocked' if blocked else 'previewed';detail=f'{len(rules)} local rule sets evaluated.' if rules else 'No rule sets configured; no guardrail assurance.'
            elif kind=='policy':
                p=active_policy(db,user.org_id);d=evaluate(settings,'purchase:create',{'amount':f'{body.amount:.2f}','supplier_id':'SUP-DEMO-104','currency':'USD','purpose':'Workflow dry run'},p)
                decision=d['decision'];detail=f'Policy v{p.version}: {decision}.'
                if decision=='deny':status='denied';blocked=True
            elif kind=='approval':
                if decision=='require_approval':status='review_required';blocked=True;detail='Preview halted. Submit a governed action for real independent review.'
                else:detail='No independent approval required by this preview decision.'
            elif kind=='tool':status='simulated';detail='No connector called. Use Run governed action to dispatch a real synthetic business action.'
            elif kind=='verify':detail='Verification step designed; no external effect exists to verify in a dry run.'
            else:detail='Preview completed without external side effects.'
            events.append({**node,'status':status,'detail':detail})
            if node['ref_id']:
                references.append({'id':node['ref_id'],'version':node['ref_version'],'step':node['id']})
        return ('gated' if blocked else 'completed'),{'steps':events,'policy_decision':decision,'rendered':rendered,'citations':citations,'references':references,'boundary':'Workflow dry run. No LLM, customer endpoint or business connector was invoked; no approval was created.'}
    if row.kind in ('model','connector'):
        return 'completed',{'configuration_valid':True,'connection_verified':False,'credential_reference':c['credential_ref'] or 'Not configured','boundary':'Configuration validation only. Endpoint and secret reference were not contacted or resolved.'}
    return 'completed',{'checks':c.get('checks',[]),'target':c.get('target'),'deployment_performed':False,'boundary':'Release plan saved. No deployment or production approval performed.'}


def register_workbench(app,factory,settings,human):
    @app.get('/v1/workbench')
    def listing(request:Request):
        with factory() as db:
            u=human(request,db)
            records=db.scalars(select(WorkspaceAsset).where(WorkspaceAsset.org_id==u.org_id,WorkspaceAsset.env==runtime_environment(db,u.org_id)).order_by(WorkspaceAsset.updated.desc()).limit(500)).all()
            runs=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==u.org_id,WorkbenchRun.env==runtime_environment(db,u.org_id),WorkbenchRun.kind.notin_(('hybrid_search','member_provision','environment_asset_copy'))).order_by(WorkbenchRun.created.desc()).limit(100)).all()
            return {'assets':[public(r) for r in records],'runs':[public(r) for r in runs],'mode':settings.mode,'schema_version':CURRENT_SCHEMA,'boundaries':{'provider_connected':False,'provider_execution_enabled':bool(settings.live_inference),'cloud_deployed':False,'retrieval':'Local BM25','workflow_execution':'Dry run only; governed action dispatcher remains separate'}}

    @app.post('/v1/workbench',status_code=201)
    def create(body:AssetInput,request:Request):
        config=validate_config(body.kind,body.config)
        with factory.begin() as db:
            u=human(request,db,True,'operate')
            if body.kind=='guardrail': permit(u,'policy')
            validate_references(db,u,body.kind,config)
            row=WorkspaceAsset(org_id=u.org_id,env=runtime_environment(db,u.org_id),kind=body.kind,name=body.name.strip(),description=body.description,config=config,author_id=u.id)
            db.add(row);db.flush();snapshot(db,row,u)
            audit(db,u.org_id,u.id,'workbench.created',detail={'asset_id':row.id,'kind':row.kind,'version':row.version})
            return public(row)

    @app.put('/v1/workbench/{id}')
    def edit(id:str,body:AssetUpdate,request:Request):
        config=validate_config(body.kind,body.config)
        with factory.begin() as db:
            u=human(request,db,True,'operate');row=asset_for(db,u,id)
            if row.kind=='guardrail': permit(u,'policy')
            if row.kind!=body.kind or row.status=='archived':fail(409,'ASSET_IMMUTABLE','Archived assets and asset types cannot be changed.')
            validate_references(db,u,body.kind,config)
            result=db.execute(update(WorkspaceAsset).where(WorkspaceAsset.id==id,WorkspaceAsset.org_id==u.org_id,WorkspaceAsset.env==runtime_environment(db,u.org_id),WorkspaceAsset.version==body.expected_version).values(name=body.name.strip(),description=body.description,config=config,version=WorkspaceAsset.version+1,status='draft',updated=now()))
            if result.rowcount!=1:fail(409,'STALE_VERSION','Another editor changed this asset. Refresh before editing.')
            db.refresh(row);snapshot(db,row,u);audit(db,u.org_id,u.id,'workbench.revised',detail={'asset_id':id,'version':row.version})
            return public(row)

    @app.post('/v1/workbench/{id}/validate')
    def validate(id:str,body:VersionInput,request:Request):
        with factory.begin() as db:
            u=human(request,db,True,'operate');row=asset_for(db,u,id)
            if row.kind=='guardrail': permit(u,'policy')
            if row.status=='archived':fail(409,'ASSET_ARCHIVED','Archived assets cannot be validated.')
            if row.kind=='model': permit(u,'manage')
            validate_config(row.kind,row.config);validate_references(db,u,row.kind,row.config)
            changed=db.execute(update(WorkspaceAsset).where(WorkspaceAsset.id==id,WorkspaceAsset.org_id==u.org_id,WorkspaceAsset.env==runtime_environment(db,u.org_id),WorkspaceAsset.version==body.expected_version,WorkspaceAsset.status!='archived').values(status='validated',version=WorkspaceAsset.version+1,updated=now()))
            if changed.rowcount!=1:fail(409,'STALE_VERSION','Refresh this asset before validating.')
            db.refresh(row);snapshot(db,row,u);audit(db,u.org_id,u.id,'workbench.validated',detail={'asset_id':id,'version':row.version,'connection_tested':False})
            return public(row)

    @app.post('/v1/workbench/{id}/archive')
    def archive(id:str,body:VersionInput,request:Request):
        with factory.begin() as db:
            u=human(request,db,True,'operate');row=asset_for(db,u,id)
            if row.kind=='guardrail': permit(u,'policy')
            changed=db.execute(update(WorkspaceAsset).where(WorkspaceAsset.id==id,WorkspaceAsset.org_id==u.org_id,WorkspaceAsset.env==runtime_environment(db,u.org_id),WorkspaceAsset.version==body.expected_version).values(status='archived',version=WorkspaceAsset.version+1,updated=now()))
            if changed.rowcount!=1:fail(409,'STALE_VERSION','Refresh before archiving.')
            db.refresh(row);snapshot(db,row,u);audit(db,u.org_id,u.id,'workbench.archived',detail={'asset_id':id,'version':row.version})
            return public(row)

    @app.get('/v1/workbench/{id}/history')
    def history(id:str,request:Request):
        with factory() as db:
            u=human(request,db);asset_for(db,u,id)
            return [public(r) for r in db.scalars(select(AssetRevision).where(AssetRevision.org_id==u.org_id,AssetRevision.env==runtime_environment(db,u.org_id),AssetRevision.asset_id==id).order_by(AssetRevision.version.desc())).all()]

    @app.post('/v1/workbench/{id}/run')
    def run(id:str,body:RunInput,request:Request):
        if any(len(v)>12000 for v in body.variables.values()):fail(422,'INPUT_TOO_LARGE','Variable values are limited to 12000 characters.')
        with factory.begin() as db:
            u=human(request,db,True,'operate');row=asset_for(db,u,id)
            if row.status=='archived':fail(409,'ASSET_ARCHIVED','Archived assets cannot be run.')
            validate_config(row.kind,row.config);validate_references(db,u,row.kind,row.config)
            started=time.perf_counter();status,result=execute_preview(db,u,row,body,settings)
            record=WorkbenchRun(org_id=u.org_id,env=runtime_environment(db,u.org_id),asset_id=id,kind=row.kind,status=status,asset_version=row.version,duration_ms=round((time.perf_counter()-started)*1000,3),result=result,author_id=u.id)
            db.add(record);db.flush();audit(db,u.org_id,u.id,'workbench.run',detail={'run_id':record.id,'asset_id':id,'version':row.version,'kind':row.kind,'status':status})
            return public(record)

    @app.post('/v1/workbench-starter')
    def starter(request:Request):
        if settings.mode!='local':fail(403,'LOCAL_ONLY','Synthetic starter content is local-only.')
        from .workbench_templates import templates
        with factory.begin() as db:
            u=human(request,db,True,'operate');permit(u,'policy');created=0
            for item in templates():
                if db.scalar(select(WorkspaceAsset.id).where(WorkspaceAsset.org_id==u.org_id,WorkspaceAsset.env==runtime_environment(db,u.org_id),WorkspaceAsset.kind==item['kind'],WorkspaceAsset.name==item['name'])):continue
                row=WorkspaceAsset(org_id=u.org_id,env=runtime_environment(db,u.org_id),author_id=u.id,**item);db.add(row);db.flush();snapshot(db,row,u);created+=1
            audit(db,u.org_id,u.id,'workbench.starter_loaded',detail={'created':created})
            return {'created':created,'synthetic':True,'provider_connections_created':False}
