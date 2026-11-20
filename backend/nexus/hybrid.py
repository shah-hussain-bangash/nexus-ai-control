"""ACL-first local hybrid retrieval. No provider calls, generated answers or business effects."""
from .search_text import NORMALIZATION_VERSION
import hashlib,json,math,os,re,signal,subprocess,sys,tempfile,time
from pathlib import Path
from typing import Literal
from fastapi import Request,Header,Query
from pydantic import Field,field_validator
from sqlalchemy import select,update,func
from .db import WorkbenchRun,DocumentChunk,KnowledgeDocument,User,Organization,now
from .documents import allowed_docs,can_read
from .schemas import Strict
from .security import fail,PERMISSIONS
from .service import audit,canonical
from .runtime_context import runtime_environment
KIND='hybrid_search'
METHOD='Local TF-IDF / corpus-fitted LSA + normalized BM25; no neural model'

class Source(Strict):
 id:str=Field(min_length=1,max_length=64)
 version:int=Field(ge=1)
class Search(Strict):
 query:str=Field(min_length=1,max_length=500)
 sources:list[Source]=Field(default_factory=list,max_length=20)
 dimensions:int=Field(default=8,ge=1,le=32)
 semantic_weight:float=Field(default=.6,ge=0,le=1,allow_inf_nan=False)
 min_score:float=Field(default=.15,ge=0,le=1,allow_inf_nan=False)
 top_k:int=Field(default=5,ge=1,le=10)
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
class Recover(Strict):key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')

def compute(payload):
 with tempfile.TemporaryDirectory(prefix='nexus-search-') as temp:
  root=Path(temp);source=root/'input.json';out=root/'output.json';source.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
  env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL')};env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
  process=subprocess.Popen([sys.executable,'-m','nexus.hybrid_worker',str(source),str(out)],cwd=Path(__file__).parent.parent,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name=='posix',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
  try:process.wait(timeout=8)
  except subprocess.TimeoutExpired:
   if os.name=='posix':
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
   else:
    try:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,timeout=2)
    except (subprocess.TimeoutExpired,OSError):pass
    if process.poll() is None:process.kill()
   process.wait();return {'error_code':'SEARCH_TIMEOUT'}
  if process.returncode or not out.exists() or out.stat().st_size>32768:return {'error_code':'RANKING_FAILED'}
  try:return json.loads(out.read_text())
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
 return {'id':row.id,'status':row.status,'created':row.created,'duration_ms':row.duration_ms,'method':METHOD,'items':items,'withheld_stale_or_inaccessible':hidden,'rank':result.get('rank',0),'vocabulary':result.get('vocabulary',0),'corpus_chunks':result.get('corpus_chunks',0),'source_count':result.get('source_count',0),'error_code':result.get('error_code',''),'parameters':result.get('parameters',{}),'provider_calls':0,'query_text_stored':False,'normalization_version':result.get('normalization_version','legacy-unversioned'),'normalization_current':result.get('normalization_version')==NORMALIZATION_VERSION,'boundary':'Ranked source excerpts only. Scores are not calibrated confidence. Current ACL/version checks apply again to saved history.'}

def owned_run(db,id,user):
 row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==id,WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND))
 if not row or (row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set())):fail(404,'SEARCH_NOT_FOUND','Search history is not visible to this account.')
 return row

def register_hybrid(app,factory,settings,human):
 @app.get('/v1/hybrid-search/capabilities')
 def capabilities(request:Request):
  with factory() as db:human(request,db)
  return {'method':METHOD,'max_chunks':128,'max_vocabulary':1024,'max_selected_sources':20,'max_requests_per_minute':30,'max_inflight':2,'history_limit':1000,'timeout_seconds':8,'provider_calls':0,'neural_embeddings':False,'persistent_vector_index':False,'language_boundary':'Unicode word tokens and corpus co-occurrence; no translation or pretrained multilingual semantics.'}
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
  key=hashlib.sha256(idempotency_key.encode()).hexdigest();fingerprint=hashlib.sha256(canonical(body.model_dump()).encode()).hexdigest()
  with factory.begin() as db:
   user=human(request,db,True)
   db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
   records=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND)).all()
   previous=next((r for r in records if r.author_id==user.id and r.result.get('key')==key),None)
   if previous:
    if previous.result.get('fingerprint')!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different search.')
    return visible_run(db,previous,user)
   stamp=now()
   if len(records)>=1000:fail(429,'SEARCH_HISTORY_CAPACITY','The workspace reached its bounded 1,000-search receipt limit. Review retention before continuing.')
   if sum(r.created>stamp-60 for r in records)>=30:fail(429,'SEARCH_RATE_LIMIT','The workspace reached 30 local search requests per minute.')
   for r in records:
    if r.status=='processing' and r.created<stamp-120:r.status='interrupted';r.result={**r.result,'error_code':'SEARCH_INTERRUPTED'}
   if sum(r.status=='processing' for r in records)>=2:fail(429,'SEARCH_CONCURRENCY_LIMIT','Two local searches are already running. Retry later with the same intent key.')
   docs=allowed_docs(db,user);byid={d.id:d for d in docs}
   if body.sources:
    for s in body.sources:
     if s.id not in byid:fail(404,'SOURCE_NOT_FOUND','A selected source is not in your authorized scope.')
     if byid[s.id].version!=s.version:fail(409,'SOURCE_CHANGED','A selected source revision changed. Refresh before searching.')
    docs=[byid[s.id] for s in body.sources];byid={d.id:d for d in docs}
   if len(docs)>20:fail(422,'SOURCE_SELECTION_REQUIRED','Select at most 20 authorized documents for this bounded corpus search.')
   chunks=db.scalars(select(DocumentChunk).where(DocumentChunk.org_id==user.org_id,DocumentChunk.env==runtime_environment(db,user.org_id),DocumentChunk.document_id.in_(byid)).order_by(DocumentChunk.document_id,DocumentChunk.position)).all() if docs else []
   chunks=[c for c in chunks if c.document_version==byid[c.document_id].version]
   if len(chunks)>128:fail(422,'CORPUS_LIMIT','Select a smaller corpus of at most 128 chunks. No sources were silently omitted.')
   snapshots=[{'id':d.id,'version':d.version,'hash':d.content_hash} for d in docs];metadata=[{'document_id':c.document_id,'document_version':c.document_version,'position':c.position,'sha256':c.content_hash} for c in chunks]
   payload={'texts':[c.text for c in chunks],**body.model_dump(exclude={'sources'})};author=user.id;org=user.org_id;environment=runtime_environment(db,org)
   parameters=body.model_dump(exclude={'query','sources'});row=WorkbenchRun(org_id=org,env=environment,kind=KIND,status='processing',duration_ms=0,author_id=author,result={'key':key,'fingerprint':fingerprint,'parameters':parameters,'normalization_version':NORMALIZATION_VERSION,'source_count':len(docs),'corpus_chunks':len(chunks)})
   db.add(row);db.flush();id=row.id;audit(db,org,author,'retrieval.hybrid.started',detail={'run_id':id,'source_count':len(docs),'corpus_chunks':len(chunks)})
  start=time.perf_counter()
  try:result=compute(payload) if chunks else {'scores':[],'rank':0,'vocabulary':0}
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
   error=result.get('error_code','')
   if not valid:error='SOURCE_SCOPE_CHANGED'
   hits=[];seen=set()
   if not error:
    try:
     if type(result['rank']) is not int or not 0<=result['rank']<=32 or type(result['vocabulary']) is not int or not 0<=result['vocabulary']<=1024 or len(result['scores'])>body.top_k:raise ValueError()
     for score in result['scores']:
      pos=score['position']
      if type(pos) is not int or not 0<=pos<len(metadata) or pos in seen or not all(type(score[k]) in (int,float) and math.isfinite(score[k]) and 0<=score[k]<=1 for k in ('score','semantic_score','lexical_score')):raise ValueError()
      seen.add(pos);hits.append({**metadata[pos],**{k:score[k] for k in ('score','semantic_score','lexical_score')}})
    except (KeyError,TypeError,ValueError):error='RANKING_FAILED';hits=[]
   row.status='failed' if error else 'completed';row.result={**row.result,'error_code':error,'rank':result.get('rank',0) if not error else 0,'vocabulary':result.get('vocabulary',0) if not error else 0,'hits':hits if not error else []}
   audit(db,org,author,'retrieval.hybrid.'+row.status,detail={'run_id':id,'hits':len(hits),'error_code':error})
   return visible_run(db,row,user)
