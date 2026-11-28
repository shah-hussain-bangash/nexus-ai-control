"""Persistent scoped intake, bounded process extraction and explicit publication review."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import signal
import subprocess
import sys
import tempfile
from typing import Literal
from fastapi import Request,Header,Query
from pydantic import Field,field_validator
from sqlalchemy import select,update,func
from .db import IngestionJob,KnowledgeDocument,Organization,User,now,uid
from .documents import validate_members,index_document
from .schemas import Strict
from .security import fail,digest,PERMISSIONS
from .service import audit,canonical
from .runtime_context import environment_user_allowed,runtime_environment
from .extraction_result import normalize_result

ACTIVE=('queued','processing','awaiting_review')
class Intake(Strict):
    title:str=Field(min_length=2,max_length=120)
    filename:str=Field(min_length=3,max_length=120)
    content_base64:str=Field(min_length=1,max_length=1398104)
    language:Literal['English','Arabic','Bilingual']='English'
    extraction_mode:Literal['auto','ocr']='auto'
    allowed_roles:list[Literal['engineer','approver','auditor']]=Field(default_factory=list,max_length=3)
    allowed_users:list[str]=Field(default_factory=list,max_length=30)
    @field_validator('title')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<2:raise ValueError('Use a visible title.')
        return value.strip()

class Control(Strict):
    expected_version:int=Field(ge=1)
    note:str=Field(min_length=5,max_length=500)
    @field_validator('note')
    @classmethod
    def visible(cls,value):
        if len(value.strip())<5:raise ValueError('Include a visible review note.')
        return value.strip()
class Publish(Control):reviewed:Literal[True]
class Recover(Strict):key:str=Field(min_length=8,max_length=128)


def manageable(job,user,environment):return bool(user.active) and job.org_id==user.org_id and job.env==environment and (job.author_id==user.id or 'policy' in PERMISSIONS.get(user.role,set()))
def job_for(db,id,user,lock=False):
    q=select(IngestionJob).where(IngestionJob.id==id,IngestionJob.org_id==user.org_id,IngestionJob.env==runtime_environment(db,user.org_id))
    job=db.scalar(q.with_for_update() if lock else q)
    if not job or not manageable(job,user,runtime_environment(db,user.org_id)):fail(404,'INTAKE_NOT_FOUND','Intake record is not visible to this account.')
    return job

def serialize(job,detail=False):
    data={k:getattr(job,k) for k in ('id','author_id','title','filename','format','language','extraction_mode','original_sha256','original_bytes','extraction','allowed_roles','allowed_users','status','version','attempts','error_code','created','updated','expires','document_id','published_version')}
    data['can_retry']=job.status=='failed' and job.attempts<3 and job.expires>now()
    if detail and job.status=='awaiting_review':data['extracted_text']=job.extracted_text
    return data

def check_version(job,body):
    if job.version!=body.expected_version:fail(409,'STALE_VERSION','The worker or another operator changed this intake. Refresh before acting.')

def release(job,status,error=''):
    job.status=status;job.error_code=error;job.version+=1;job.updated=now();job.lease_token='';job.lease_until=0

def decode(body):
    ext=body.filename.rsplit('.',1)[-1].lower()
    if body.filename!=PurePosixPath(body.filename).name or '\\' in body.filename or ext not in ('pdf','docx','png','jpg','jpeg','csv'):fail(422,'UNSUPPORTED_INTAKE_FORMAT','Use a plain PDF, DOCX, PNG, JPEG or CSV filename.')
    try:data=base64.b64decode(body.content_base64,validate=True)
    except (ValueError,binascii.Error):fail(422,'INVALID_FILE_ENCODING','Use valid base64 content.')
    if not 1<=len(data)<=1048576:fail(413,'INTAKE_FILE_TOO_LARGE','Intake supports files up to 1 MiB.')
    signatures={'pdf':data.startswith(b'%PDF-'),'docx':data.startswith(b'PK\x03\x04'),'png':data.startswith(b'\x89PNG\r\n\x1a\n'),'jpg':data.startswith(b'\xff\xd8'),'jpeg':data.startswith(b'\xff\xd8')}
    if ext!='csv' and not signatures[ext]:fail(422,'FILE_SIGNATURE_MISMATCH','The file does not match its declared format.')
    if ext in ('docx','csv') and body.extraction_mode=='ocr':fail(422,'UNSUPPORTED_EXTRACTION_MODE','DOCX and CSV support text extraction, not forced image OCR.')
    return ext,data


def register_ingestion(app,factory,settings,human):
    @app.get('/v1/ingestion-capabilities')
    def capabilities(request:Request):
        with factory() as db:human(request,db)
        return {'formats':['pdf','docx','png','jpg','jpeg','csv'],'csv_max_rows':500,'csv_max_columns':32,'csv_max_cell_bytes':2048,'csv_encoding':'UTF-8 (optional BOM)','csv_delimiter':',','max_file_bytes':1048576,'max_pdf_pages':12,'max_extracted_text_bytes':32768,'ocr_enabled':bool(settings.ingestion_ocr_enabled),'ocr_executable_available':bool(shutil.which(settings.tesseract_command)),'ocr_languages_configured':settings.ingestion_ocr_languages,'language_data_verified':False,'review_before_publication':True,'timeout_seconds':settings.ingestion_timeout_seconds,'boundary':'Bounded local extraction, not malware scanning or a complete OS sandbox. OCR language data, isolated worker resources and production acceptance require operator provisioning.'}

    @app.get('/v1/ingestion-jobs')
    def listing(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db);q=select(IngestionJob).where(IngestionJob.org_id==user.org_id,IngestionJob.env==runtime_environment(db,user.org_id),IngestionJob.status!='archived')
            if 'policy' not in PERMISSIONS.get(user.role,set()):q=q.where(IngestionJob.author_id==user.id)
            rows=db.scalars(q.order_by(IngestionJob.created.desc(),IngestionJob.id).offset(offset).limit(limit+1)).all()
            return {'items':[serialize(j) for j in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}

    @app.post('/v1/ingestion-jobs',status_code=201)
    def create(body:Intake,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        with factory.begin() as db:
            user=human(request,db,True,'operate')
            if not 8<=len(idempotency_key)<=128:fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use an 8–128 character intake key.')
            ext,data=decode(body)
            if not settings.ingestion_ocr_enabled and (ext in ('png','jpg','jpeg') or body.extraction_mode=='ocr'):fail(422,'OCR_DISABLED','The operator must enable OCR and provision its language data first.')
            db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));hashed=digest(canonical(body.model_dump()))
            old=db.scalar(select(IngestionJob).where(IngestionJob.org_id==user.org_id,IngestionJob.env==runtime_environment(db,user.org_id),IngestionJob.author_id==user.id,IngestionJob.idem_key==idempotency_key))
            if old:
                if old.request_digest!=hashed:fail(409,'IDEMPOTENCY_CONFLICT','This intake key belongs to a different immutable file request.')
                return serialize(old)
            validate_members(db,user.org_id,body.allowed_users)
            q=select(func.count()).select_from(IngestionJob).where(IngestionJob.org_id==user.org_id,IngestionJob.env==runtime_environment(db,user.org_id))
            if db.scalar(q)>=500 or db.scalar(q.where(IngestionJob.status!='archived'))>=50 or db.scalar(q.where(IngestionJob.status.in_(ACTIVE)))>=10:fail(429,'INTAKE_CAPACITY','This bounded workspace permits 10 active jobs, 50 retained jobs and 500 lifetime receipts. Archive obsolete terminal records or review retention with the operator.')
            job=IngestionJob(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,title=body.title,filename=body.filename,format=ext,language=body.language,extraction_mode=body.extraction_mode,original_data=data,original_sha256=hashlib.sha256(data).hexdigest(),original_bytes=len(data),allowed_roles=sorted(set(body.allowed_roles)),allowed_users=sorted(set(body.allowed_users)),idem_key=idempotency_key,request_digest=hashed)
            db.add(job);db.flush();audit(db,user.org_id,user.id,'intake.queued',detail={'job_id':job.id,'format':ext,'bytes':len(data),'sha256':job.original_sha256})
            return serialize(job)

    @app.post('/v1/ingestion-jobs/recover')
    def recover(body:Recover,request:Request):
        with factory() as db:
            user=human(request,db,True);job=db.scalar(select(IngestionJob).where(IngestionJob.org_id==user.org_id,IngestionJob.env==runtime_environment(db,user.org_id),IngestionJob.author_id==user.id,IngestionJob.idem_key==body.key))
            if not job:fail(404,'INTAKE_INTENT_NOT_FOUND','No committed intake is visible. Retry the unchanged request with its same key.')
            return serialize(job)

    @app.get('/v1/ingestion-jobs/{id}')
    def detail(id:str,request:Request):
        with factory() as db:
            user=human(request,db);return serialize(job_for(db,id,user),True)

    @app.post('/v1/ingestion-jobs/{id}/control/{command}')
    def control(id:str,command:Literal['retry','cancel','archive'],body:Control,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));job=job_for(db,id,user,True);check_version(job,body)
            if command=='retry':
                if job.status!='failed' or job.expires<=now() or job.attempts>=3 or not job.original_data:fail(409,'INTAKE_RETRY_UNAVAILABLE','Only an unexpired failed job below three attempts can retry.')
                release(job,'queued');job.extracted_text='';job.extraction={}
            elif command=='cancel':
                if job.status not in ACTIVE+('failed',):fail(409,'INTAKE_STATE','This intake cannot be cancelled.')
                release(job,'cancelled');job.original_data=b'';job.extracted_text=''
            else:
                if job.status not in ('indexed','cancelled','expired','failed'):fail(409,'INTAKE_STATE','Cancel active work before archiving it.')
                release(job,'archived');job.original_data=b'';job.extracted_text=''
            audit(db,user.org_id,user.id,'intake.'+command,detail={'job_id':job.id,'note':body.note});return serialize(job)

    @app.post('/v1/ingestion-jobs/{id}/publish')
    def publish(id:str,body:Publish,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));job=job_for(db,id,user,True)
            # A repeated publication acknowledges the original source; never duplicates it.
            if job.status=='indexed':return serialize(job)
            check_version(job,body)
            if job.status!='awaiting_review' or job.expires<=now() or not job.extracted_text:fail(409,'INTAKE_NOT_REVIEWABLE','Only an unexpired extracted result can be reviewed and published.')
            author=db.get(User,job.author_id)
            if not author or author.org_id!=job.org_id or not author.active or 'operate' not in PERMISSIONS.get(author.role,set()) or not environment_user_allowed(db,author.id,job.org_id,job.env,allow_non_staging=settings.mode=='local'):fail(403,'INTAKE_AUTHOR_REVOKED','The original requesting author is no longer authorized.')
            validate_members(db,user.org_id,job.allowed_users)
            count=db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.org_id==user.org_id,KnowledgeDocument.env==runtime_environment(db,user.org_id),KnowledgeDocument.status=='indexed'))
            if count>=200:fail(429,'DOCUMENT_CAPACITY','This workspace already has 200 active source documents.')
            doc=KnowledgeDocument(org_id=user.org_id,env=job.env,title=job.title,filename=job.filename,author_id=job.author_id,language=job.language,content=job.extracted_text,content_hash=digest(job.extracted_text),byte_count=len(job.extracted_text.encode()),allowed_roles=job.allowed_roles,allowed_users=job.allowed_users,idem_key='intake-'+job.id,request_digest=job.request_digest)
            db.add(doc);db.flush();index_document(db,doc);job.document_id=doc.id;job.published_version=doc.version;release(job,'indexed');job.original_data=b'';job.extracted_text=''
            audit(db,user.org_id,user.id,'intake.published',detail={'job_id':job.id,'document_id':doc.id,'version':doc.version,'original_sha256':job.original_sha256,'text_sha256':doc.content_hash,'review_note':body.note,'reviewed':True});return serialize(job)


def extract_file(data,job,settings):
    with tempfile.TemporaryDirectory(prefix='nexus-intake-') as temp:
        root=Path(temp);os.chmod(root,0o700);source=root/'source.bin';source.write_bytes(data)
        config={'format':job.format,'language':job.language,'mode':job.extraction_mode,'ocr_enabled':bool(settings.ingestion_ocr_enabled),'ocr_languages':settings.ingestion_ocr_languages,'tesseract':settings.tesseract_command}
        (root/'config.json').write_text(json.dumps(config));output=root/'result.json'
        env={k:v for k,v in os.environ.items() if k in ('PATH','SystemRoot','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL','TESSDATA_PREFIX')};env['OMP_THREAD_LIMIT']='1'
        process=subprocess.Popen([sys.executable,'-m','nexus.extract_worker',str(source),str(root/'config.json'),str(output)],cwd=Path(__file__).parent.parent,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name=='posix',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        try:process.wait(timeout=settings.ingestion_timeout_seconds)
        except subprocess.TimeoutExpired:
            if os.name=='posix':
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            else:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                process.kill()
            process.wait();return {'error_code':'EXTRACTION_TIMEOUT'}
        if process.returncode or not output.exists() or output.stat().st_size>131072:return {'error_code':'EXTRACTOR_RESOURCE_OR_PROCESS_FAILURE'}
        try:return json.loads(output.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):return {'error_code':'EXTRACTOR_RESULT_INVALID'}


def run_ingestion_once(factory,settings,extractor=None):
    with factory.begin() as db:
        for job in db.scalars(select(IngestionJob).where(IngestionJob.status.in_(ACTIVE+('failed',)),IngestionJob.expires<=now()).with_for_update()).all():
            release(job,'expired','REVIEW_WINDOW_EXPIRED');job.original_data=b'';job.extracted_text='';audit(db,job.org_id,'worker','intake.expired',detail={'job_id':job.id},env=job.env)
        for job in db.scalars(select(IngestionJob).where(IngestionJob.status=='processing',IngestionJob.lease_until<now()).with_for_update()).all():
            release(job,'failed','WORKER_INTERRUPTED');audit(db,job.org_id,'worker','intake.interrupted',detail={'job_id':job.id},env=job.env)
        job=db.scalar(select(IngestionJob).where(IngestionJob.status=='queued').order_by(IngestionJob.created).with_for_update(skip_locked=True).limit(1))
        if not job:return False
        token=uid();claimed=db.execute(update(IngestionJob).where(IngestionJob.id==job.id,IngestionJob.org_id==job.org_id,IngestionJob.env==job.env,IngestionJob.version==job.version,IngestionJob.status=='queued').values(status='processing',version=job.version+1,attempts=job.attempts+1,lease_token=token,lease_until=now()+90,updated=now()))
        if not claimed.rowcount:return False
        id=job.id;org=job.org_id;environment=job.env;data=bytes(job.original_data);author=db.get(User,job.author_id)
        permitted=author and author.org_id==job.org_id and author.active and 'operate' in PERMISSIONS.get(author.role,set()) and environment_user_allowed(db,author.id,job.org_id,job.env,allow_non_staging=settings.mode=='local')
        db.expunge(job)
    try:result=(extractor or extract_file)(data,job,settings) if permitted else {'error_code':'REQUESTER_REVOKED'}
    except Exception:result={'error_code':'EXTRACTION_UNAVAILABLE'}
    with factory.begin() as db:
        current=db.scalar(select(IngestionJob).where(IngestionJob.id==id,IngestionJob.org_id==org,IngestionJob.env==environment,IngestionJob.status=='processing',IngestionJob.lease_token==token).with_for_update())
        if not current:return True  # cancellation/expiry fences off stale publication
        # A matching token cannot authorize a late result. Check the deadlines
        # again under the completion row lock, even if no other worker swept it.
        completed=now()
        if current.expires<=completed:
            release(current,'expired','REVIEW_WINDOW_EXPIRED');current.original_data=b'';current.extracted_text=''
        elif current.lease_until<=completed:
            release(current,'failed','WORKER_INTERRUPTED');current.extracted_text=''
        else:
            author=db.get(User,current.author_id)
            if not author or not environment_user_allowed(db,current.author_id,current.org_id,current.env,allow_non_staging=settings.mode=='local') or 'operate' not in PERMISSIONS.get(author.role,set()):
                result={'error_code':'REQUESTER_REVOKED'}
            result=normalize_result(result)
            text=result.get('text','');error=result.get('error_code','')
            if error or not text.strip():
                current.extracted_text='';current.extraction={};release(current,'failed',error or 'NO_EXTRACTABLE_TEXT')
            else:current.extracted_text=text;current.extraction=result.get('info',{});release(current,'awaiting_review')
        audit(db,current.org_id,'worker','intake.'+current.status,detail={'job_id':id,'attempt':current.attempts,'error_code':current.error_code},env=current.env)
    return True
