"""Rerank a completed indexed search, preserving its passages and original scores."""
import hmac,time,re
from fastapi import Request,Header,HTTPException
from pydantic import Field,field_validator
from sqlalchemy import update
from .db import WorkbenchRun,Organization
from .schemas import Strict
from .security import fail,digest
from .service import canonical,audit
from .runtime_context import runtime_environment
from .hybrid import owned_run,visible_run,KIND,compute
from .neural_index_runtime import intent,previous
from .neural_index_store import load_index
from .indexed_review_comparison import query_identity
from .retrieval_admission import admit
from .local_reranking import configuration,checked_packet,PROTOCOL


class Rerank(Strict):
    search_id:str=Field(min_length=1,max_length=64)
    query:str=Field(min_length=1,max_length=500)
    @field_validator('query')
    @classmethod
    def visible(cls,value):
        if not value.strip() or '\x00' in value:raise ValueError('Repeat the original visible query.')
        return value.strip()


def parent_snapshot(db,user,id):
    base=owned_run(db,id,user);value=visible_run(db,base,user);params=value['parameters']
    if base.author_id!=user.id:fail(404,'SEARCH_NOT_FOUND','Choose your own saved search.')
    if base.status!='completed' or params.get('retrieval_mode')!='local_indexed' or params.get('reranking'):
        fail(409,'RERANK_SEARCH_UNSUPPORTED','Choose an original completed indexed search.')
    if value['withheld_stale_or_inaccessible'] or not value['normalization_current']:fail(409,'RERANK_SEARCH_STALE','Refresh the source search before reranking.')
    if not 2<=len(value['items'])<=10:fail(422,'RERANK_CANDIDATES_REQUIRED','Reranking requires 2–10 current passages.')
    pins={}
    for index_id,version in (params.get('index_versions') or {params['index_id']:params['index_version']}).items():
        index,_,_,_=load_index(db,user,index_id,model=params['embedding_model'],model_digest=params['embedding_digest'])
        if index.version!=version:fail(409,'RERANK_SEARCH_STALE','A selected index changed.')
        pins[index_id]=(index.version,index.content_hash)
    return base,value,pins


def register_reranking(app,factory,settings,human):
    @app.get('/v1/neural-reranking/capabilities')
    def capabilities(request:Request):
        with factory() as db:human(request,db)
        config=configuration(settings)
        return {'enabled':bool(config),'model':config['rerank_model'] if config else None,'digest':config['rerank_digest'] if config else None,
            'max_candidates':10,'timeout_seconds':22,'protocol':PROTOCOL,'boundary':'Optional local model ordering; original cosine scores retained. No quality acceptance.'}

    @app.post('/v1/neural-indexes/rerank',status_code=201)
    def execute(body:Rerank,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        key,fingerprint=intent(idempotency_key,{'stage':'local_reranking',**body.model_dump()})
        with factory.begin() as db:
            user=human(request,db,True);db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            old=previous(db,user,KIND,key,fingerprint)
            if old:return visible_run(db,old,user)
            config=configuration(settings)
            if not config:fail(503,'RERANK_DISABLED','The operator must enable a pinned local reranking model first.')
            base,value,pins=parent_snapshot(db,user,body.search_id)
            identity=base.result.get('query_identity')
            if type(identity) is not str or not re.fullmatch(r'[a-f0-9]{64}',identity):fail(409,'RERANK_QUERY_UNAVAILABLE','Run a new indexed search before reranking this older receipt.')
            author=user.id;org=user.org_id;environment=runtime_environment(db,org)
            if not hmac.compare_digest(identity,query_identity(settings.secret,org,environment,author,body.query)):
                fail(409,'RERANK_QUERY_DIFFERENT','Repeat the original query under the same query-identity key.')
            admit(db,user);parent_hash=digest(canonical(base.result));hits=[h.copy() for h in base.result['hits']]
            parameters={**value['parameters'],'parent_search_id':base.id,'reranking':{**config,'protocol':PROTOCOL}}
            row=WorkbenchRun(org_id=org,env=environment,author_id=author,kind=KIND,status='processing',duration_ms=0,
                result={'key':key,'fingerprint':fingerprint,'query_identity':identity,'parameters':parameters,
                    **{k:base.result.get(k,0) for k in ('source_count','corpus_chunks','index_count','embedding_dimensions')},
                    'normalization_version':base.result['normalization_version'],'parent_provider_calls':value['provider_calls']})
            db.add(row);db.flush();id=row.id
            payload={'retrieval_mode':'local_neural','task':'rerank','query':body.query,'texts':[hit['excerpt'] for hit in value['items']],**config}
            audit(db,org,author,'retrieval.rerank.started',detail={'run_id':id,'parent_search_id':base.id})
        started=time.perf_counter()
        try:packet=compute(payload)
        except Exception:packet={}
        with factory.begin() as db:
            user=human(request,db,True);db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            if user.id!=author or user.org_id!=org or runtime_environment(db,org)!=environment:fail(403,'SEARCH_SCOPE_CHANGED','Session scope changed while reranking.')
            row=owned_run(db,id,user)
            if row.status!='processing':return visible_run(db,row,user)
            error='';ordered=[];usage={}
            try:
                if configuration(settings)!=config:raise ValueError('RERANK_CONFIGURATION_CHANGED')
                current,_,current_pins=parent_snapshot(db,user,body.search_id)
                if digest(canonical(current.result))!=parent_hash or current_pins!=pins:raise ValueError('RERANK_SOURCE_CHANGED')
                order=checked_packet(packet,len(hits),config)
                ordered=[{**hits[position],'rerank_position':i+1} for i,position in enumerate(order)]
                usage={'rerank_requests':1,'metadata_requests':3,'embedding_requests':0,'input_tokens':packet['input_tokens'],'output_tokens':packet['output_tokens']}
            except (HTTPException,ValueError,TypeError,KeyError):error='RERANK_FAILED'
            row.status='failed' if error else 'completed';row.duration_ms=round((time.perf_counter()-started)*1000,3)
            row.result={**row.result,**usage,'hits':ordered if not error else [],'error_code':error,'rank':0,'vocabulary':0}
            audit(db,org,author,'retrieval.rerank.'+row.status,detail={'run_id':id,'error_code':error})
            return visible_run(db,row,user)
