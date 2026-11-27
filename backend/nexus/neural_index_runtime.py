"""Scoped stored-index build/query API with durable, non-retrying receipts."""
import re,time
from fastapi import Request,Header,Query,HTTPException
from pydantic import Field,field_validator
from sqlalchemy import select,update,func
from .db import NeuralIndex,WorkbenchRun,KnowledgeDocument,DocumentChunk,Organization,now
from .documents import document_for,can_read
from .hybrid import Source,Recover,compute,visible_run,owned_run,KIND
from .neural_search import configuration,NORMALIZATION_VERSION
from .neural_index_store import create_index,load_index,rank_index,remove_index,metadata,vector_values,MAX_INDEXES
from .retrieval_admission import admit,BUILD_KIND
from .schemas import Strict
from .runtime_context import runtime_environment
from .security import fail,digest,PERMISSIONS
from .service import canonical,audit


class Build(Strict):
    name:str=Field(min_length=2,max_length=120)
    sources:list[Source]=Field(min_length=1,max_length=20)
    @field_validator('name')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<2 or '\x00' in value:raise ValueError('Use a visible index name.')
        return value.strip()
    @field_validator('sources')
    @classmethod
    def unique(cls,value):
        if len({s.id for s in value})!=len(value):raise ValueError('Use distinct source documents.')
        return value


class SearchIndex(Strict):
    index_id:str=Field(min_length=1,max_length=64)
    query:str=Field(min_length=1,max_length=500)
    top_k:int=Field(default=5,ge=1,le=10)
    min_score:float=Field(default=.15,ge=0,le=1,allow_inf_nan=False)
    one_per_document:bool=Field(default=False,strict=True)
    @field_validator('query')
    @classmethod
    def visible(cls,value):
        if not value.strip() or '\x00' in value:raise ValueError('Use a visible query.')
        return value.strip()


class Remove(Strict):
    expected_version:int=Field(strict=True,ge=1)
    note:str=Field(min_length=5,max_length=500)


def intent(key,body):
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
    return digest(key),digest(canonical(body))


def previous(db,user,kind,key,fingerprint):
    rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,
        WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==kind,WorkbenchRun.author_id==user.id)).all()
    row=next((r for r in rows if r.result.get('key')==key),None)
    if row and row.result.get('fingerprint')!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another retrieval request.')
    return row


def build_for(db,user,id):
    row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==id,WorkbenchRun.org_id==user.org_id,
        WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==BUILD_KIND))
    if not row or row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set()):fail(404,'INDEX_BUILD_NOT_FOUND','Build receipt is unavailable in your scope.')
    return row


def visible_build(db,user,row):
    result=row.result or {};index=None
    if result.get('index_id'):
        saved=db.scalar(select(NeuralIndex).where(NeuralIndex.id==result['index_id'],NeuralIndex.org_id==user.org_id,NeuralIndex.env==runtime_environment(db,user.org_id)))
        index=metadata(saved) if saved else None
    return {'id':row.id,'status':row.status,'created':row.created,'duration_ms':row.duration_ms,
        'index_id':result.get('index_id'),'index':index,'index_state':index['status'] if index else 'removed' if result.get('index_id') else None,
        'source_count':result.get('source_count',0),'corpus_passages':result.get('corpus_passages',0),
        'model':result.get('embedding_model'),'model_digest':result.get('embedding_digest'),'error_code':result.get('error_code',''),
        'provider_calls':4 if row.status=='completed' else None,
        'boundary':'Durable build receipt. Recovery never repeats model execution; deleting vectors does not delete this receipt.'}


def packet(value,count,config):
    fields={'vectors','dimensions','embedding_model','embedding_digest','embedding_requests','metadata_requests'}
    if type(value) is not dict or set(value)!=fields:raise ValueError('RANKING_FAILED')
    if any(value[key]!=config[key] for key in config):raise ValueError('RANKING_FAILED')
    if (type(value['dimensions']) is not int or not 1<=value['dimensions']<=4096 or
        type(value['vectors']) is not list or len(value['vectors'])!=count or
        type(value['embedding_requests']) is not int or value['embedding_requests']!=1 or
        type(value['metadata_requests']) is not int or value['metadata_requests']!=3):raise ValueError('RANKING_FAILED')
    return [vector_values(v,value['dimensions'],normalize=False) for v in value['vectors']]


def error_code(exc):
    allowed={'INDEX_SOURCE_CHANGED','INDEX_MODEL_CHANGED','INDEX_INVALIDATED','INDEX_NOT_FOUND','INDEX_CAPACITY','INDEX_INTEGRITY_FAILED'}
    code=exc.detail.get('code') if isinstance(exc,HTTPException) and isinstance(exc.detail,dict) else None
    return code if code in allowed else 'RANKING_FAILED'


def register_neural_indexes(app,factory,settings,human):
    @app.get('/v1/neural-indexes/builds')
    def builds(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db);query=select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,
                WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==BUILD_KIND)
            if 'policy' not in PERMISSIONS.get(user.role,set()):query=query.where(WorkbenchRun.author_id==user.id)
            rows=db.scalars(query.order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).offset(offset).limit(limit+1)).all()
            return {'items':[visible_build(db,user,r) for r in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}

    @app.post('/v1/neural-indexes/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True)
            rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),
                WorkbenchRun.author_id==user.id,WorkbenchRun.kind==BUILD_KIND)).all()
            row=next((r for r in rows if r.result.get('key')==digest(body.key)),None)
            if not row:fail(404,'INDEX_BUILD_NOT_FOUND','No build receipt matches this account and key.')
            return visible_build(db,user,row)

    @app.get('/v1/neural-indexes')
    def listing(request:Request):
        with factory() as db:
            user=human(request,db);query=select(NeuralIndex).where(NeuralIndex.org_id==user.org_id,NeuralIndex.env==runtime_environment(db,user.org_id))
            if 'policy' not in PERMISSIONS.get(user.role,set()):query=query.where(NeuralIndex.author_id==user.id)
            rows=db.scalars(query.order_by(NeuralIndex.created.desc(),NeuralIndex.id).limit(MAX_INDEXES)).all()
            return {'items':[metadata(r) for r in rows],'boundary':'Stored state only; use-time source access, model and integrity checks still apply.'}

    @app.delete('/v1/neural-indexes/{id}')
    def remove(id:str,body:Remove,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate')
            return remove_index(db,user,id,expected_version=body.expected_version,note=body.note)

    @app.post('/v1/neural-indexes',status_code=201)
    def build(body:Build,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        key,fingerprint=intent(idempotency_key,body.model_dump())
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            old=previous(db,user,BUILD_KIND,key,fingerprint)
            if old:return visible_build(db,user,old)
            config=configuration(settings)
            if not config:fail(503,'NEURAL_SEARCH_DISABLED','The operator must enable a pinned installed embedding model first.')
            if db.scalar(select(func.count()).select_from(NeuralIndex).where(NeuralIndex.org_id==user.org_id,NeuralIndex.env==runtime_environment(db,user.org_id)))>=MAX_INDEXES:
                fail(429,'INDEX_CAPACITY','Remove obsolete index metadata before building another snapshot.')
            docs=[document_for(db,s.id,user) for s in body.sources]
            if any(doc.version!=source.version for doc,source in zip(docs,body.sources)):fail(409,'SOURCE_CHANGED','Refresh the selected source versions.')
            chunks=db.scalars(select(DocumentChunk).where(DocumentChunk.org_id==user.org_id,DocumentChunk.env==runtime_environment(db,user.org_id),
                DocumentChunk.document_id.in_([d.id for d in docs])).order_by(DocumentChunk.document_id,DocumentChunk.position)).all()
            versions={d.id:d.version for d in docs};chunks=[c for c in chunks if c.document_version==versions[c.document_id]]
            if not 1<=len(chunks)<=32 or set(versions)!={c.document_id for c in chunks}:fail(422,'CORPUS_LIMIT','Build from 1–32 current passages; no sources are silently omitted.')
            from .local_embeddings import validate_texts,EmbeddingError
            try:validate_texts([c.text for c in chunks])
            except EmbeddingError:fail(422,'CORPUS_LIMIT','Selected text exceeds the neural input allowance.')
            admit(db,user);author=user.id;org=user.org_id;environment=runtime_environment(db,org)
            snapshots=[(d.id,d.version,d.content_hash) for d in docs]
            entries=[{'document_id':c.document_id,'document_version':c.document_version,'position':c.position,'sha256':c.content_hash} for c in chunks]
            payload={'retrieval_mode':'local_neural','task':'index_build','texts':[c.text for c in chunks],**config}
            row=WorkbenchRun(org_id=org,env=environment,author_id=author,kind=BUILD_KIND,status='processing',duration_ms=0,
                result={'key':key,'fingerprint':fingerprint,**config,'source_count':len(docs),'corpus_passages':len(chunks)})
            db.add(row);db.flush();id=row.id;audit(db,org,author,'retrieval.index.build_started',detail={'run_id':id})
        started=time.perf_counter()
        try:value=compute(payload)
        except Exception:value={'error_code':'RANKING_FAILED'}
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            if user.id!=author or user.org_id!=org or runtime_environment(db,org)!=environment:fail(403,'SEARCH_SCOPE_CHANGED','Session scope changed while building.')
            row=build_for(db,user,id)
            if row.status!='processing':return visible_build(db,user,row)
            error='';index=None
            try:
                if configuration(settings)!=config:raise ValueError('RANKING_FAILED')
                for doc_id,version,sha in snapshots:
                    doc=db.get(KnowledgeDocument,doc_id)
                    if not doc or not can_read(doc,user,environment) or doc.version!=version or doc.content_hash!=sha:
                        fail(409,'INDEX_SOURCE_CHANGED','A selected source changed while building.')
                vectors=packet(value,len(entries),config)
                index=create_index(db,user,name=body.name,model=config['embedding_model'],model_digest=config['embedding_digest'],
                    entries=[{**entry,'vector':vector} for entry,vector in zip(entries,vectors)],key='build-'+id)
            except (HTTPException,ValueError,TypeError,KeyError) as exc:error=error_code(exc)
            row.status='failed' if error else 'completed';row.duration_ms=round((time.perf_counter()-started)*1000,3)
            row.result={**row.result,'error_code':error,**({'index_id':index['id']} if index else {})}
            audit(db,org,author,'retrieval.index.build_'+row.status,detail={'run_id':id,'error_code':error})
            return visible_build(db,user,row)

    @app.post('/v1/neural-indexes/search',status_code=201)
    def search(body:SearchIndex,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        key,fingerprint=intent(idempotency_key,{'retrieval_mode':'local_indexed',**body.model_dump()})
        with factory.begin() as db:
            user=human(request,db,True);db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            old=previous(db,user,KIND,key,fingerprint)
            if old:return visible_run(db,old,user)
            config=configuration(settings)
            if not config:fail(503,'NEURAL_SEARCH_DISABLED','The operator must enable a pinned installed embedding model first.')
            index,_,_,_=load_index(db,user,body.index_id,model=config['embedding_model'],model_digest=config['embedding_digest'])
            version=index.version;sha=index.content_hash;admit(db,user)
            author=user.id;org=user.org_id;environment=runtime_environment(db,org)
            parameters={**body.model_dump(exclude={'query'}),'retrieval_mode':'local_indexed','index_version':version,**config}
            row=WorkbenchRun(org_id=org,env=environment,author_id=author,kind=KIND,status='processing',duration_ms=0,
                result={'key':key,'fingerprint':fingerprint,'parameters':parameters,'source_count':len(index.sources),'corpus_chunks':index.entry_count,'normalization_version':NORMALIZATION_VERSION})
            db.add(row);db.flush();id=row.id
            payload={'retrieval_mode':'local_neural','task':'index_query','query':body.query,**config}
            audit(db,org,author,'retrieval.index.query_started',detail={'run_id':id,'index_id':index.id})
        started=time.perf_counter()
        try:value=compute(payload)
        except Exception:value={'error_code':'RANKING_FAILED'}
        with factory.begin() as db:
            user=human(request,db,True);db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            if user.id!=author or user.org_id!=org or runtime_environment(db,org)!=environment:fail(403,'SEARCH_SCOPE_CHANGED','Session scope changed while searching.')
            row=owned_run(db,id,user)
            if row.status!='processing':return visible_run(db,row,user)
            error='';hits=[];details={}
            try:
                if configuration(settings)!=config:raise ValueError('RANKING_FAILED')
                vector=packet(value,1,config)[0]
                index,_,_,_=load_index(db,user,body.index_id,model=config['embedding_model'],model_digest=config['embedding_digest'])
                if index.version!=version or index.content_hash!=sha:fail(409,'INDEX_SOURCE_CHANGED','The snapshot changed during the query.')
                ranked=rank_index(db,user,body.index_id,vector,model=config['embedding_model'],model_digest=config['embedding_digest'],
                    top_k=body.top_k,min_score=body.min_score,one_per_document=body.one_per_document)
                hits=[{**{k:hit[k] for k in ('document_id','document_version','position','sha256','score')},'semantic_score':hit['score'],'lexical_score':0} for hit in ranked['items']]
                details={'embedding_dimensions':len(vector),'embedding_requests':1,'metadata_requests':3}
            except (HTTPException,ValueError,TypeError,KeyError) as exc:error=error_code(exc)
            row.status='failed' if error else 'completed';row.duration_ms=round((time.perf_counter()-started)*1000,3)
            row.result={**row.result,**details,'error_code':error,'hits':hits if not error else [],'rank':0,'vocabulary':0}
            audit(db,org,author,'retrieval.index.query_'+row.status,detail={'run_id':id,'error_code':error})
            return visible_run(db,row,user)
