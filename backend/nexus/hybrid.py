"""ACL-first local hybrid retrieval. No provider calls, generated answers or business effects."""
from .search_text import NORMALIZATION_VERSION
import hashlib,json,os,re,signal,subprocess,sys,tempfile,time
from pathlib import Path
from typing import Literal
from fastapi import Request,Header,Query
from pydantic import Field,field_validator,model_validator
from sqlalchemy import select,update,func
from .db import WorkbenchRun,DocumentChunk,KnowledgeDocument,User,Organization,now
from .documents import allowed_docs,can_read
from .schemas import Strict
from .security import fail,PERMISSIONS
from .service import audit,canonical
from .runtime_context import runtime_environment
from .ranking_result import normalize_result
from . import neural_search
from .retrieval_admission import admit
KIND='hybrid_search'
METHOD='Local TF-IDF / corpus-fitted LSA + normalized BM25; no neural model'

class Source(Strict):
 id:str=Field(min_length=1,max_length=64)
 version:int=Field(ge=1)
class Search(Strict):
 retrieval_mode:Literal['local_lsa','local_neural']='local_lsa'
 query:str=Field(min_length=1,max_length=500)
 sources:list[Source]=Field(default_factory=list,max_length=20)
 dimensions:int=Field(default=8,ge=1,le=32)
 semantic_weight:float=Field(default=.6,ge=0,le=1,allow_inf_nan=False)
 min_score:float=Field(default=.15,ge=0,le=1,allow_inf_nan=False)
 top_k:int=Field(default=5,ge=1,le=10)
 one_per_document:bool=Field(default=False,strict=True)
 @field_validator('query')
 @classmethod
 def nonempty(cls,v):
  if not v.strip() or '\x00' in v:raise ValueError('Use a visible text query without null bytes.')
  return v.strip()
 @field_validator('sources')
 @classmethod
 def unique(cls,v):
  if len({x.id for x in v})!=len(v):raise ValueError('Choose unique source documents.')
  return v
 @model_validator(mode='after')
 def neural_controls(self):
  if self.retrieval_mode=='local_neural' and (self.dimensions!=8 or self.semantic_weight!=.6):raise ValueError('LSA dimensions and blend weight do not apply to neural search.')
  return self
class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')

def compute(payload):
 with tempfile.TemporaryDirectory(prefix='nexus-search-') as temp:
  root=Path(temp);source=root/'input.json';out=root/'output.json';source.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
  env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL')};env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
  neural=payload.get('retrieval_mode')=='local_neural'
  process=subprocess.Popen([sys.executable,'-m','nexus.neural_worker' if neural else 'nexus.hybrid_worker',str(source),str(out)],cwd=Path(__file__).parent.parent,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name=='posix',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
  try:process.wait(timeout=12 if neural else 8)
  except subprocess.TimeoutExpired:
   if os.name=='posix':
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
   else:
    try:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,timeout=2)
    except (subprocess.TimeoutExpired,OSError):pass
    if process.poll() is None:process.kill()
   process.wait();return {'error_code':'SEARCH_TIMEOUT'}
  maximum=2097152 if neural and payload.get('task')=='index_build' else 262144 if neural and payload.get('task')=='index_query' else 32768
  if process.returncode or not out.exists() or out.stat().st_size>maximum:return {'error_code':'RANKING_FAILED'}
  try:return json.loads(out.read_text(encoding='utf-8'))
  except (ValueError,UnicodeError):return {'error_code':'RANKING_FAILED'}

def visible_run(db,row,user):
 environment=runtime_environment(db,user.org_id)
 if not row or row.org_id!=user.org_id or row.env!=environment or row.kind!=KIND or not user.active or (row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set())):fail(404,'SEARCH_NOT_FOUND','Search history is not visible to this account.')
 result=row.result or {};items=[];hidden=0
 for hit in result.get('hits',[]):
  doc=db.get(KnowledgeDocument,hit['document_id'])
  if not doc or not can_read(doc,user,environment) or doc.version!=hit['document_version']:hidden+=1;continue
  chunk=db.scalar(select(DocumentChunk).where(DocumentChunk.org_id==user.org_id,DocumentChunk.env==runtime_environment(db,user.org_id),DocumentChunk.document_id==doc.id,DocumentChunk.document_version==doc.version,DocumentChunk.position==hit['position'],DocumentChunk.content_hash==hit['sha256']))
  if not chunk:hidden+=1;continue
  items.append({'document_id':doc.id,'document_version':doc.version,'title':doc.title,'filename':doc.filename,'chunk':chunk.position+1,'excerpt':chunk.text,'sha256':chunk.content_hash,'citation':f'{doc.id}:v{doc.version}:chunk{chunk.position+1}',**{k:hit[k] for k in ('score','semantic_score','lexical_score')}})
 neural=result.get('parameters',{}).get('retrieval_mode') in ('local_neural','local_indexed')
 calls=result.get('embedding_requests',0)+result.get('metadata_requests',0) if row.status=='completed' else None
 return {'id':row.id,'status':row.status,'created':row.created,'duration_ms':row.duration_ms,'method':neural_search.METHOD if neural else METHOD,'items':items,'withheld_stale_or_inaccessible':hidden,'rank':result.get('rank',0),'vocabulary':result.get('vocabulary',0),'corpus_chunks':result.get('corpus_chunks',0),'source_count':result.get('source_count',0),'error_code':result.get('error_code',''),'parameters':result.get('parameters',{}),'provider_calls':calls if neural else 0,'embedding_dimensions':result.get('embedding_dimensions',0),'query_text_stored':False,'normalization_version':result.get('normalization_version','legacy-unversioned'),'normalization_current':result.get('normalization_version')==(neural_search.NORMALIZATION_VERSION if neural else NORMALIZATION_VERSION),'boundary':'Ranked source excerpts only. Scores are not calibrated confidence. Current ACL/version checks apply again to saved history. Failed neural requests have unknown local HTTP-call counts.'}

def owned_run(db,id,user):
 row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==id,WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND))
 if not row or (row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set())):fail(404,'SEARCH_NOT_FOUND','Search history is not visible to this account.')
 return row

def register_hybrid(app,factory,settings,human):
 @app.get('/v1/hybrid-search/capabilities')
 def capabilities(request:Request):
  with factory() as db:human(request,db)
  config=neural_search.configuration(settings)
  return {'method':METHOD,'max_chunks':128,'max_vocabulary':1024,'max_selected_sources':20,'max_requests_per_minute':30,'max_inflight':2,'history_limit':1000,'timeout_seconds':8,'provider_calls':0,'neural_embeddings':bool(config),'neural_max_chunks':32,'neural_timeout_seconds':12,'neural_model':config['embedding_model'] if config else None,'neural_model_digest':config['embedding_digest'] if config else None,'persistent_vector_index':bool(config),'persistent_vector_index_supported':True,'one_per_document_supported':True,'language_boundary':'Default LSA uses corpus co-occurrence. Opt-in local neural semantics require representative language-quality acceptance.'}
 @app.get('/v1/hybrid-search/history')
 def history(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(10,ge=1,le=25)):
  with factory() as db:
   user=human(request,db);q=select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND)
   if 'policy' not in PERMISSIONS.get(user.role,set()):q=q.where(WorkbenchRun.author_id==user.id)
   rows=db.scalars(q.order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).offset(offset).limit(limit+1)).all()
   return {'items':[visible_run(db,r,user) for r in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}
 @app.get('/v1/hybrid-search/history/{id}')
 def detail(id:str,request:Request):
  with factory() as db:
   user=human(request,db);return visible_run(db,owned_run(db,id,user),user)
 @app.post('/v1/hybrid-search/recover')
 def recover(body:Recover,request:Request):
  with factory() as db:
   user=human(request,db,True);key=hashlib.sha256(body.key.encode()).hexdigest()
   rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND,WorkbenchRun.author_id==user.id)).all()
   row=next((r for r in rows if r.result.get('key')==key),None)
   if not row:fail(404,'SEARCH_NOT_FOUND','No acknowledged search matches this account and key.')
   return visible_run(db,row,user)
 @app.post('/v1/hybrid-search',status_code=201)
 def search(body:Search,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
  if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character search intent key.')
  intent=body.model_dump()
  if body.retrieval_mode=='local_lsa':intent.pop('retrieval_mode')
  if not body.one_per_document:intent.pop('one_per_document')
  key=hashlib.sha256(idempotency_key.encode()).hexdigest();fingerprint=hashlib.sha256(canonical(intent).encode()).hexdigest()
  with factory.begin() as db:
   user=human(request,db,True)
   db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
   records=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND)).all()
   previous=next((r for r in records if r.author_id==user.id and r.result.get('key')==key),None)
   if previous:
    if previous.result.get('fingerprint')!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different search.')
    return visible_run(db,previous,user)
   config=neural_search.configuration(settings) if body.retrieval_mode=='local_neural' else None
   if body.retrieval_mode=='local_neural' and config is None:fail(503,'NEURAL_SEARCH_DISABLED','The operator must enable a pinned installed local embedding model first.')
   admit(db,user)
   docs=allowed_docs(db,user);byid={d.id:d for d in docs}
   if body.sources:
    for s in body.sources:
     if s.id not in byid:fail(404,'SOURCE_NOT_FOUND','A selected source is not in your authorized scope.')
     if byid[s.id].version!=s.version:fail(409,'SOURCE_CHANGED','A selected source revision changed. Refresh before searching.')
    docs=[byid[s.id] for s in body.sources];byid={d.id:d for d in docs}
   if len(docs)>20:fail(422,'SOURCE_SELECTION_REQUIRED','Select at most 20 authorized documents for this bounded corpus search.')
   chunks=db.scalars(select(DocumentChunk).where(DocumentChunk.org_id==user.org_id,DocumentChunk.env==runtime_environment(db,user.org_id),DocumentChunk.document_id.in_(byid)).order_by(DocumentChunk.document_id,DocumentChunk.position)).all() if docs else []
   chunks=[c for c in chunks if c.document_version==byid[c.document_id].version]
   maximum=32 if config else 128
   if len(chunks)>maximum:fail(422,'CORPUS_LIMIT',f'Select a smaller corpus of at most {maximum} chunks. No sources were silently omitted.')
   if config:
    from .local_embeddings import validate_texts,EmbeddingError
    if chunks:
     try:validate_texts([body.query,*[c.text for c in chunks]])
     except EmbeddingError:fail(422,'CORPUS_LIMIT','Selected neural-search text exceeds the bounded UTF-8 input allowance.')
   snapshots=[{'id':d.id,'version':d.version,'hash':d.content_hash} for d in docs];metadata=[{'document_id':c.document_id,'document_version':c.document_version,'position':c.position,'sha256':c.content_hash} for c in chunks]
   payload={'texts':[c.text for c in chunks],**body.model_dump(exclude={'sources'})};author=user.id;org=user.org_id;environment=runtime_environment(db,org)
   if config:payload.update(config)
   else:payload.pop('retrieval_mode')
   if body.one_per_document:
    groups={doc.id:index for index,doc in enumerate(docs)}
    payload['groups']=[groups[chunk.document_id] for chunk in chunks]
   parameters=body.model_dump(exclude={'query','sources'})
   if config:
    parameters.update(config);parameters.pop('dimensions');parameters.pop('semantic_weight')
   else:parameters.pop('retrieval_mode')
   row=WorkbenchRun(org_id=org,env=environment,kind=KIND,status='processing',duration_ms=0,author_id=author,result={'key':key,'fingerprint':fingerprint,'parameters':parameters,'normalization_version':neural_search.NORMALIZATION_VERSION if config else NORMALIZATION_VERSION,'source_count':len(docs),'corpus_chunks':len(chunks)})
   db.add(row);db.flush();id=row.id;audit(db,org,author,'retrieval.hybrid.started',detail={'run_id':id,'source_count':len(docs),'corpus_chunks':len(chunks)})
  start=time.perf_counter()
  try:result=compute(payload) if chunks else (neural_search.empty_result(config['embedding_model'],config['embedding_digest']) if config else {'scores':[],'rank':0,'vocabulary':0})
  except Exception:result={'error_code':'RANKING_FAILED'}
  with factory.begin() as db:
   # Completion is a write: order identity/source rechecks, receipt persistence
   # and response construction with the same workspace lock as ACL changes.
   # Ranking remains outside this transaction so it does not hold the lock.
   user=human(request,db,True);valid=True
   if user.id!=author or user.org_id!=org or runtime_environment(db,org)!=environment:fail(403,'SEARCH_SCOPE_CHANGED','Session scope changed while searching.')
   row=owned_run(db,id,user)
   if row.status!='processing':return visible_run(db,row,user)
   for source in snapshots:
    doc=db.get(KnowledgeDocument,source['id'])
    if not doc or not can_read(doc,user,environment) or doc.version!=source['version'] or doc.content_hash!=source['hash']:valid=False
   row.duration_ms=round((time.perf_counter()-start)*1000,3)
   result=neural_search.checked_result(result,len(metadata),body.top_k,config['embedding_model'],config['embedding_digest']) if config else normalize_result(result,len(metadata),body.top_k)
   error=result.get('error_code','')
   if not error and body.one_per_document:
    documents=[metadata[score['position']]['document_id'] for score in result['scores']]
    if len(set(documents))!=len(documents):error='RANKING_FAILED'
   if not valid:error='SOURCE_SCOPE_CHANGED'
   if config and neural_search.configuration(settings)!=config:error='NEURAL_CONFIGURATION_CHANGED'
   hits=[]
   if not error:
    hits=[{**metadata[score['position']],**{key:score[key] for key in ('score','semantic_score','lexical_score')}} for score in result['scores']]
   details={key:result[key] for key in ('embedding_dimensions','embedding_requests','metadata_requests') if key in result} if config and not error else {}
   row.status='failed' if error else 'completed';row.result={**row.result,**details,'error_code':error,'rank':result.get('rank',0) if not error else 0,'vocabulary':result.get('vocabulary',0) if not error else 0,'hits':hits if not error else []}
   audit(db,org,author,'retrieval.hybrid.'+row.status,detail={'run_id':id,'hits':len(hits),'error_code':error})
   return visible_run(db,row,user)
