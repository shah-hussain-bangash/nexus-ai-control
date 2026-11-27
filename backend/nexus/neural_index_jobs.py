"""Durable bounded index builds; checkpoints contain vectors only in vector tables."""
import time
from typing import Literal
from fastapi import Request,Header,HTTPException
from pydantic import Field
from sqlalchemy import select,update,delete,func,and_,or_,case
from .db import WorkbenchRun,NeuralIndex,NeuralVector,Organization,User,DocumentChunk,now,uid
from .runtime_context import bind_runtime_context,runtime_environment
from .security import fail,PERMISSIONS,digest
from .service import canonical,audit
from .schemas import Strict
from .neural_search import configuration
from .neural_index_runtime import Build,Recover,intent,previous,compute,packet
from .neural_index_store import (metadata,current_actor,checked_sources,prepare_entries,snapshot_hash,vector_values,MAX_INDEXES)
from .retrieval_admission import admit,KINDS,JOB_KIND

BATCH_SIZE=8
LEASE_SECONDS=120
ACTIVE=('queued','processing','paused','interrupted')


class Control(Strict):
    expected_version:int=Field(strict=True,ge=1)
    note:str=Field(min_length=5,max_length=500)
    confirm_uncertain:bool=Field(default=False,strict=True)


def locked(db,org,environment):
    bind_runtime_context(db,org,environment)
    db.execute(update(Organization).where(Organization.id==org).values(name=Organization.name))


def job_for(db,id,user):
    row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==id,WorkbenchRun.kind==JOB_KIND,
        WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id)))
    if not row or row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set()):
        fail(404,'INDEX_JOB_NOT_FOUND','Build job is unavailable in your scope.')
    return row


def view(db,row):
    value=row.result;stage=db.get(NeuralIndex,value['index_id'])
    return {'id':row.id,'status':row.status,'created':row.created,'version':value['version'],
        'collection_id':value.get('collection_id'),'name':value['name'],'index_id':value['index_id'],'index':metadata(stage) if stage else None,
        'completed_passages':value['offset'],'total_passages':len(value['entries']),
        'stop_requested':value.get('stop_requested',''),'error_code':value.get('error_code',''),
        'lease_expired':row.status=='processing' and value.get('lease_until',0)<=now(),
        'uncertain_batch':value.get('uncertain',False),'confirmed_http_calls':value.get('confirmed_calls',0),
        'provider_calls':None if value.get('uncertain') else value.get('confirmed_calls',0),
        'model':value['config']['embedding_model'],'model_digest':value['config']['embedding_digest'],
        'boundary':'Checkpointed local build. Unfinished vectors cannot be searched. Recovery reads this job without execution; interrupted batches require explicit acknowledged resume.'}


def revise(row,**changes):
    row.result={**row.result,**changes,'version':row.result['version']+1}


def interrupt(row):
    row.status='interrupted';revise(row,lease_token='',lease_until=0,uncertain=True,error_code='INDEX_BATCH_OUTCOME_UNKNOWN')


def purge(db,row,status,code=''):
    stage=db.get(NeuralIndex,row.result['index_id'])
    if stage:
        db.execute(delete(NeuralVector).where(NeuralVector.index_id==stage.id))
        stage.status='invalidated';stage.version+=1
    row.status=status;revise(row,lease_token='',lease_until=0,stop_requested='',error_code=code)


def expire(db,row):
    if row.result.get('stop_requested')=='cancelled':
        revise(row,uncertain=True);purge(db,row,'cancelled')
    else:interrupt(row)


def validate_job(db,row,settings):
    user=db.get(User,row.author_id)
    if not user or user.org_id!=row.org_id or 'operate' not in PERMISSIONS.get(user.role,set()):fail(403,'INDEX_JOB_ACTOR_CHANGED','Build author is unavailable.')
    user,environment=current_actor(db,user)
    if configuration(settings)!=row.result['config']:fail(409,'INDEX_JOB_MODEL_CHANGED','Pinned embedding configuration changed.')
    stage=db.get(NeuralIndex,row.result['index_id'])
    if (not stage or stage.status!='building' or stage.version!=1 or stage.author_id!=row.author_id or stage.idem_key!='job-'+row.id or stage.model!=row.result['config']['embedding_model'] or stage.model_digest!=row.result['config']['embedding_digest'] or stage.entry_count!=len(row.result['entries'])):fail(409,'INDEX_JOB_SOURCE_CHANGED','Staging snapshot is unavailable.')
    sources,_,chunks=checked_sources(db,user,environment,row.result['entries'])
    if stage.sources!=sources:fail(409,'INDEX_JOB_SOURCE_CHANGED','Build sources changed.')
    vectors=db.scalars(select(NeuralVector).where(NeuralVector.index_id==stage.id).order_by(NeuralVector.document_id,NeuralVector.position)).all()
    entries=[{'document_id':v.document_id,'document_version':v.document_version,'position':v.position,'sha256':v.chunk_hash,
        'vector':vector_values(v.vector,stage.dimensions,normalize=False)} for v in vectors]
    if len(entries)!=row.result['offset'] or [{k:v for k,v in e.items() if k!='vector'} for e in entries]!=row.result['entries'][:row.result['offset']]:
        fail(409,'INDEX_JOB_CHECKPOINT_INVALID','Build checkpoint is inconsistent.')
    if snapshot_hash(stage.model,stage.model_digest,stage.sources,entries)!=row.result['checkpoint_hash']:
        fail(409,'INDEX_JOB_CHECKPOINT_INVALID','Build checkpoint is inconsistent.')
    return user,stage,chunks,entries


def safe_error(exc):
    if isinstance(exc,HTTPException) and isinstance(exc.detail,dict):
        code=exc.detail.get('code','')
        if code.startswith(('INDEX_','SOURCE_')):return code
    return 'INDEX_JOB_FAILED'


def create_queued_job(db,user,name,entries,config,key,fingerprint,collection_id=None):
    environment=runtime_environment(db,user.org_id)
    sources,_,_=checked_sources(db,user,environment,entries)
    row=WorkbenchRun(org_id=user.org_id,env=environment,author_id=user.id,kind=JOB_KIND,status='queued',duration_ms=0,result={})
    db.add(row);db.flush()
    stage=NeuralIndex(org_id=user.org_id,env=environment,author_id=user.id,name=name,model=config['embedding_model'],model_digest=config['embedding_digest'],
        dimensions=0,entry_count=len(entries),sources=sources,content_hash='',status='building',idem_key='job-'+row.id,request_digest=fingerprint)
    db.add(stage);db.flush()
    row.result={'key':key,'fingerprint':fingerprint,'name':name,'config':config,'entries':entries,'index_id':stage.id,
        'offset':0,'version':1,'confirmed_calls':0,'uncertain':False,'attempts':0,
        'checkpoint_hash':snapshot_hash(stage.model,stage.model_digest,sources,[])}
    audit(db,user.org_id,user.id,'retrieval.index.job_queued',detail={'job_id':row.id})
    if collection_id:row.result={**row.result,'collection_id':collection_id}
    return row


def register_index_jobs(app,factory,settings,human):
    @app.get('/v1/neural-index-jobs')
    def listing(request:Request):
        with factory() as db:
            user=human(request,db);query=select(WorkbenchRun).where(WorkbenchRun.kind==JOB_KIND,WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id))
            if 'policy' not in PERMISSIONS.get(user.role,set()):query=query.where(WorkbenchRun.author_id==user.id)
            rows=db.scalars(query.order_by(case((WorkbenchRun.status.in_(ACTIVE),0),else_=1),WorkbenchRun.created.desc(),WorkbenchRun.id).limit(50))
            return {'items':[view(db,row) for row in rows]}

    @app.get('/v1/neural-index-jobs/{id}')
    def inspect(id:str,request:Request):
        with factory() as db:
            user=human(request,db);return view(db,job_for(db,id,user))

    @app.post('/v1/neural-index-jobs/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True)
            rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind==JOB_KIND,WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.author_id==user.id))
            row=next((r for r in rows if r.result.get('key')==digest(body.key)),None)
            if not row:fail(404,'INDEX_JOB_NOT_FOUND','No job matches this account and key.')
            return view(db,row)

    @app.post('/v1/neural-index-jobs',status_code=202)
    def enqueue(body:Build,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        key,fingerprint=intent(idempotency_key,body.model_dump())
        with factory.begin() as db:
            user=human(request,db,True,'operate');environment=runtime_environment(db,user.org_id);locked(db,user.org_id,environment)
            old=previous(db,user,JOB_KIND,key,fingerprint)
            if old:return view(db,old)
            config=configuration(settings)
            if not config:fail(503,'NEURAL_SEARCH_DISABLED','Enable a pinned installed local embedding model first.')
            from .documents import document_for
            docs=[document_for(db,s.id,user) for s in body.sources]
            if any(d.version!=s.version for d,s in zip(docs,body.sources)):fail(409,'SOURCE_CHANGED','Refresh selected source versions.')
            chunks=db.scalars(select(DocumentChunk).where(DocumentChunk.document_id.in_([d.id for d in docs])).order_by(DocumentChunk.document_id,DocumentChunk.position)).all()
            versions={d.id:d.version for d in docs};chunks=[c for c in chunks if c.document_version==versions[c.document_id]]
            if not 1<=len(chunks)<=32 or set(versions)!={c.document_id for c in chunks}:fail(422,'CORPUS_LIMIT','Select 1–32 current passages from at most 20 sources.')
            from .local_embeddings import validate_texts,EmbeddingError
            try:validate_texts([c.text for c in chunks])
            except EmbeddingError:fail(422,'CORPUS_LIMIT','Selected text exceeds the build input allowance.')
            entries=[{'document_id':c.document_id,'document_version':c.document_version,'position':c.position,'sha256':c.content_hash} for c in chunks]
            sources,_,_=checked_sources(db,user,environment,entries)
            if db.scalar(select(func.count()).select_from(NeuralIndex))>=MAX_INDEXES:fail(429,'INDEX_CAPACITY','Remove obsolete snapshot metadata first.')
            if db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind==JOB_KIND,WorkbenchRun.status.in_(ACTIVE)))>=20:
                fail(429,'INDEX_JOB_CAPACITY','This environment reached 20 unfinished builds.')
            admit(db,user)
            row=create_queued_job(db,user,body.name,entries,config,key,fingerprint)
            return view(db,row)

    @app.post('/v1/neural-index-jobs/{id}/control/{command}')
    def control(id:str,command:Literal['pause','resume','cancel'],body:Control,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');locked(db,user.org_id,runtime_environment(db,user.org_id));row=job_for(db,id,user)
            if row.result['version']!=body.expected_version:fail(409,'STALE_VERSION','Refresh the build job before changing it.')
            if len(body.note.strip())<5 or '\x00' in body.note:fail(422,'INDEX_JOB_NOTE_REQUIRED','Use a visible control note.')
            if row.status=='processing' and row.result.get('lease_until',0)<=now():interrupt(row)
            if command in ('pause','cancel'):
                if row.status not in ACTIVE:fail(409,'INDEX_JOB_STATE','This build cannot be stopped.')
                if row.status=='processing':revise(row,stop_requested='paused' if command=='pause' else 'cancelled')
                elif command=='pause':row.status='paused';revise(row)
                else:purge(db,row,'cancelled')
            else:
                if row.status not in ('paused','interrupted'):fail(409,'INDEX_JOB_STATE','Only paused or interrupted builds can resume.')
                if row.result.get('uncertain') and not body.confirm_uncertain:fail(409,'INDEX_JOB_ACK_REQUIRED','Acknowledge that the uncommitted batch may execute again.')
                if row.result.get('attempts',0)>=3:fail(409,'INDEX_JOB_ATTEMPTS','This uncommitted batch reached its attempt limit; cancel and review.')
                validate_job(db,row,settings);row.status='queued';revise(row,stop_requested='',error_code='')
            audit(db,user.org_id,user.id,'retrieval.index.job_'+command,detail={'job_id':row.id,'note':body.note.strip()})
            return view(db,row)


def run_index_job_once(factory,settings):
    # Scan without a user context, then lock and bind exactly one workspace job.
    with factory() as db:
        candidate=db.scalar(select(WorkbenchRun).where(WorkbenchRun.kind==JOB_KIND,
            or_(WorkbenchRun.status=='queued',and_(WorkbenchRun.status=='processing',WorkbenchRun.result['lease_until'].as_float()<=now()))).order_by(WorkbenchRun.created,WorkbenchRun.id).limit(1))
        if not candidate:return False
        id,org,environment=candidate.id,candidate.org_id,candidate.env
    with factory.begin() as db:
        locked(db,org,environment);row=db.get(WorkbenchRun,id)
        if not row or row.kind!=JOB_KIND:return False
        if row.status=='processing':
            if row.result.get('lease_until',0)>now():return False
            expire(db,row);return True
        if row.status!='queued':return False
        try:user,stage,chunks,entries=validate_job(db,row,settings)
        except (HTTPException,ValueError,TypeError,KeyError) as exc:purge(db,row,'failed',safe_error(exc));return True
        inflight=db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind.in_(KINDS),WorkbenchRun.status=='processing'))
        if inflight>=2:return False
        offset=row.result['offset'];batch=row.result['entries'][offset:offset+BATCH_SIZE]
        token=uid();row.status='processing';revise(row,lease_token=token,lease_until=now()+LEASE_SECONDS,attempts=row.result.get('attempts',0)+1)
        config=dict(row.result['config']);payload={'retrieval_mode':'local_neural','task':'index_build','texts':[chunks[(e['document_id'],e['position'])].text for e in batch],**config}
    started=time.perf_counter()
    try:value=compute(payload)
    except Exception:value={'error_code':'RANKING_FAILED'}
    with factory.begin() as db:
        locked(db,org,environment);row=db.get(WorkbenchRun,id)
        if not row or row.status!='processing' or row.result.get('lease_token')!=token:return True
        if row.result.get('lease_until',0)<=now():expire(db,row);return True
        row.duration_ms+=round((time.perf_counter()-started)*1000,3)
        try:vectors=packet(value,len(batch),config)
        except (HTTPException,ValueError,TypeError,KeyError):
            revise(row,uncertain=True);purge(db,row,'cancelled' if row.result.get('stop_requested')=='cancelled' else 'failed','INDEX_JOB_EMBEDDING_FAILED');return True
        revise(row,confirmed_calls=row.result.get('confirmed_calls',0)+4)
        if row.result.get('stop_requested')=='cancelled':purge(db,row,'cancelled');return True
        deadline=row.result['lease_until']
        try:
            with db.begin_nested():
                user,stage,_,entries=validate_job(db,row,settings)
                dimensions=len(vectors[0])
                if stage.dimensions and stage.dimensions!=dimensions:fail(409,'INDEX_JOB_DIMENSIONS','Embedding dimensions changed between batches.')
                stage.dimensions=dimensions
                for entry,vector in zip(batch,vectors):
                    db.add(NeuralVector(org_id=org,env=environment,index_id=stage.id,document_id=entry['document_id'],document_version=entry['document_version'],position=entry['position'],chunk_hash=entry['sha256'],vector=vector))
                    entries.append({**entry,'vector':vector})
                completed=offset+len(batch)
                if completed==len(row.result['entries']):
                    prepared,_=prepare_entries(entries);sources,_,_=checked_sources(db,user,environment,prepared)
                    db.flush()
                    by_key={(e['document_id'],e['position']):e for e in prepared}
                    for vector in db.scalars(select(NeuralVector).where(NeuralVector.index_id==stage.id)):
                        vector.vector=by_key[(vector.document_id,vector.position)]['vector']
                    stage.content_hash=snapshot_hash(stage.model,stage.model_digest,sources,prepared);stage.status='ready';stage.version+=1
                    entries=prepared;row.status='completed'
                else:row.status='paused' if row.result.get('stop_requested')=='paused' else 'queued'
                revise(row,offset=completed,attempts=0,lease_token='',lease_until=0,stop_requested='',checkpoint_hash=snapshot_hash(stage.model,stage.model_digest,stage.sources,entries))
                audit(db,org,'worker','retrieval.index.job_checkpoint',detail={'job_id':id,'completed_passages':completed,'status':row.status})
                if now()>=deadline:fail(409,'INDEX_JOB_LEASE_EXPIRED','Build lease expired before checkpoint commit.')
        except (HTTPException,ValueError,TypeError,KeyError) as exc:
            if isinstance(exc,HTTPException) and exc.detail.get('code')=='INDEX_JOB_LEASE_EXPIRED':expire(db,row)
            else:purge(db,row,'failed',safe_error(exc))
    return True
