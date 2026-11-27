"""Atomic admission of bounded background snapshot collections; no model dispatch here."""
from fastapi import Request,Header,Query
from pydantic import Field
from sqlalchemy import select,func,case
from .db import WorkbenchRun,NeuralIndex,KnowledgeDocument,DocumentChunk,now
from .schemas import Strict
from .runtime_context import runtime_environment
from .security import fail,PERMISSIONS,digest
from .service import canonical,audit
from .documents import document_for,can_read
from .neural_search import configuration
from .neural_index_runtime import Build,Recover,intent,previous
from .neural_index_jobs import (locked,job_for,view as job_view,create_queued_job,ACTIVE,interrupt,purge,revise)
from .neural_index_store import MAX_INDEXES
from .retrieval_admission import admit,COLLECTION_KIND,JOB_KIND


class Cancel(Strict):
    expected_token:str=Field(pattern=r'^[a-f0-9]{64}$')
    note:str=Field(min_length=5,max_length=500)


def collection_for(db,id,user):
    row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==id,WorkbenchRun.kind==COLLECTION_KIND,
        WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id)))
    if not row or row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set()):
        fail(404,'INDEX_COLLECTION_NOT_FOUND','Collection is unavailable in your scope.')
    return row


def members(db,row,user):
    jobs=[job_for(db,id,user) for id in row.result['job_ids']]
    if any(job.author_id!=row.author_id or job.result.get('collection_id')!=row.id for job in jobs):
        fail(409,'INDEX_COLLECTION_INVALID','Collection membership cannot be verified.')
    return jobs


def view(db,row,user):
    children=[job_view(db,job) for job in members(db,row,user)];value=row.result;environment=runtime_environment(db,user.org_id)
    current=True
    for id,snapshot in value['sources'].items():
        doc=db.get(KnowledgeDocument,id)
        if (not doc or not can_read(doc,user,environment) or doc.version!=snapshot['version'] or doc.content_hash!=snapshot['sha256'] or digest(doc.content)!=snapshot['sha256']):current=False;break
    ready=all(job['status']=='completed' and job['index'] and job['index']['status']=='ready' and
        job['index']['model']==value['config']['embedding_model'] and job['index']['model_digest']==value['config']['embedding_digest'] for job in children)
    ready=ready and len({job['index']['dimensions'] for job in children if job['index']})==1 and all(job['index'] and job['index']['dimensions']>0 for job in children)
    if ready and current:status='completed'
    elif not current or all(job['status']=='completed' for job in children) or any(job['status']=='completed' and (not job['index'] or job['index']['status']!='ready') for job in children):status='stale'
    elif any(job['status'] in ('failed','cancelled') for job in children):status='incomplete'
    elif any(job['status']=='processing' for job in children):status='processing'
    elif any(job['status']=='queued' for job in children):status='queued'
    elif any(job['status']=='interrupted' for job in children):status='interrupted'
    else:status='paused'
    return {'id':row.id,'name':value['name'],'status':status,'created':row.created,'children':children,
        'control_token':digest(canonical(children)),'searchable':bool(ready and current),
        'index_ids':[job['index_id'] for job in children] if ready and current else [],
        'snapshot_count':len(children),'total_passages':value['total_passages'],'completed_passages':sum(job['completed_passages'] for job in children),
        'confirmed_http_calls':sum(job['confirmed_http_calls'] for job in children),
        'provider_calls':None if any(job['provider_calls'] is None for job in children) else sum(job['provider_calls'] for job in children),
        'model':value['config']['embedding_model'],'model_digest':value['config']['embedding_digest'],
        'boundary':'Bounded collection metadata, not vector-integrity or quality acceptance. Full-set selection requires all snapshots ready and current source access; query-time checks still apply. Child snapshots publish independently.'}


def register_index_collections(app,factory,settings,human):
    @app.get('/v1/neural-index-collections')
    def listing(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db)
            active=[id for id in db.scalars(select(WorkbenchRun.result['collection_id'].as_string()).where(WorkbenchRun.kind==JOB_KIND,WorkbenchRun.status.in_(ACTIVE),WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id))) if id]
            query=select(WorkbenchRun).where(WorkbenchRun.kind==COLLECTION_KIND,WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id))
            if 'policy' not in PERMISSIONS.get(user.role,set()):query=query.where(WorkbenchRun.author_id==user.id)
            rows=db.scalars(query.order_by(case((WorkbenchRun.id.in_(active),0),else_=1),WorkbenchRun.created.desc(),WorkbenchRun.id).offset(offset).limit(limit+1)).all()
            return {'items':[view(db,row,user) for row in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}

    @app.get('/v1/neural-index-collections/{id}')
    def inspect(id:str,request:Request):
        with factory() as db:
            user=human(request,db);return view(db,collection_for(db,id,user),user)

    @app.post('/v1/neural-index-collections/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True)
            rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind==COLLECTION_KIND,WorkbenchRun.author_id==user.id,WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id)))
            row=next((row for row in rows if row.result.get('key')==digest(body.key)),None)
            if not row:fail(404,'INDEX_COLLECTION_NOT_FOUND','No collection matches this account and key.')
            return view(db,row,user)

    @app.post('/v1/neural-index-collections',status_code=202)
    def enqueue(body:Build,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        key,fingerprint=intent(idempotency_key,body.model_dump())
        with factory.begin() as db:
            user=human(request,db,True,'operate');environment=runtime_environment(db,user.org_id);locked(db,user.org_id,environment)
            old=previous(db,user,COLLECTION_KIND,key,fingerprint)
            if old:return view(db,old,user)
            config=configuration(settings)
            if not config:fail(503,'NEURAL_SEARCH_DISABLED','Enable a pinned installed local embedding model first.')
            docs=[document_for(db,source.id,user) for source in body.sources]
            if any(doc.version!=source.version for doc,source in zip(docs,body.sources)):fail(409,'SOURCE_CHANGED','Refresh selected source versions.')
            versions={doc.id:doc.version for doc in docs}
            chunks=db.scalars(select(DocumentChunk).where(DocumentChunk.document_id.in_(versions),DocumentChunk.org_id==user.org_id,DocumentChunk.env==environment).order_by(DocumentChunk.document_id,DocumentChunk.position)).all()
            chunks=[chunk for chunk in chunks if chunk.document_version==versions[chunk.document_id]]
            if not 1<=len(chunks)<=256 or set(versions)!={chunk.document_id for chunk in chunks}:fail(422,'CORPUS_LIMIT','Select 1–256 current passages; no selected source is silently omitted.')
            from .local_embeddings import validate_texts,EmbeddingError
            try:
                for start in range(0,len(chunks),8):validate_texts([chunk.text for chunk in chunks[start:start+8]])
            except EmbeddingError:fail(422,'CORPUS_LIMIT','A build batch exceeds its text allowance.')
            count=(len(chunks)+31)//32
            if db.scalar(select(func.count()).select_from(NeuralIndex).where(NeuralIndex.org_id==user.org_id,NeuralIndex.env==environment))+count>MAX_INDEXES:fail(429,'INDEX_CAPACITY','The whole collection must fit snapshot capacity before any job is queued.')
            if db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind==JOB_KIND,WorkbenchRun.status.in_(ACTIVE),WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==environment))+count>20:
                fail(429,'INDEX_JOB_CAPACITY','The whole collection must fit unfinished-job capacity.')
            admit(db,user)
            row=WorkbenchRun(org_id=user.org_id,env=environment,author_id=user.id,kind=COLLECTION_KIND,status='collection',duration_ms=0,result={})
            db.add(row);db.flush();jobs=[]
            for i,start in enumerate(range(0,len(chunks),32)):
                admit(db,user)
                entries=[{'document_id':chunk.document_id,'document_version':chunk.document_version,'position':chunk.position,'sha256':chunk.content_hash} for chunk in chunks[start:start+32]]
                name=body.name[:110]+f' [{i+1}/{count}]'
                job=create_queued_job(db,user,name,entries,config,digest(row.id+':'+str(i)),digest(canonical(entries)),row.id)
                jobs.append(job.id)
            row.result={'key':key,'fingerprint':fingerprint,'name':body.name,'config':config,'job_ids':jobs,'total_passages':len(chunks),
                'sources':{doc.id:{'version':doc.version,'sha256':doc.content_hash} for doc in docs}}
            audit(db,user.org_id,user.id,'retrieval.index.collection_queued',detail={'collection_id':row.id,'snapshots':count})
            return view(db,row,user)

    @app.post('/v1/neural-index-collections/{id}/cancel')
    def cancel(id:str,body:Cancel,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');locked(db,user.org_id,runtime_environment(db,user.org_id));row=collection_for(db,id,user)
            if len(body.note.strip())<5 or '\x00' in body.note:fail(422,'INDEX_JOB_NOTE_REQUIRED','Use a visible control note.')
            if view(db,row,user)['control_token']!=body.expected_token:fail(409,'STALE_VERSION','Refresh collection progress before cancelling unfinished builds.')
            changed=0
            for job in members(db,row,user):
                if job.status not in ACTIVE:continue
                if job.status=='processing' and job.result.get('lease_until',0)<=now():interrupt(job)
                if job.status=='processing':revise(job,stop_requested='cancelled')
                else:purge(db,job,'cancelled')
                changed+=1
            if not changed:fail(409,'INDEX_COLLECTION_TERMINAL','No unfinished collection jobs remain to cancel.')
            audit(db,user.org_id,user.id,'retrieval.index.collection_cancelled',detail={'collection_id':row.id,'unfinished_jobs':changed,'note':body.note.strip()})
            return view(db,row,user)
