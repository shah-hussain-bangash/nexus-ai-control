"""Bounded UTF-8 document ingestion, persisted chunks and ACL-filtered lexical retrieval."""
from .search_text import search_tokens, NORMALIZATION_VERSION
import base64
import binascii
import csv
import io
import json
import math
import re
from collections import Counter
from pathlib import PurePosixPath
from typing import Literal
from fastapi import Request,Response,Header,Query
from pydantic import Field,field_validator
from sqlalchemy import select,update,delete,func
from sqlalchemy.orm import aliased
from .schemas import Strict
from .db import KnowledgeDocument,DocumentChunk,Organization,User,DocumentUpdate,IngestionJob,now,public
from .security import fail,digest,PERMISSIONS
from .service import audit,canonical
from .runtime_context import runtime_environment

ROLES=('owner','security','engineer','approver','auditor')

class Upload(Strict):
    title: str = Field(min_length=2,max_length=120)
    filename: str = Field(min_length=3,max_length=120)
    content_base64: str = Field(min_length=1,max_length=44000)
    language: Literal['English','Arabic','Bilingual'] = 'English'
    allowed_roles: list[Literal['owner','security','engineer','approver','auditor']] = Field(default_factory=list,max_length=5)
    allowed_users: list[str] = Field(default_factory=list,max_length=30)

    @field_validator('title')
    @classmethod
    def visible_title(cls,value):
        if len(value.strip())<2:raise ValueError('Use a visible document title.')
        return value.strip()

class Note(Strict):
    note: str = Field(min_length=5,max_length=500)

    @field_validator('note')
    @classmethod
    def visible_note(cls,value):
        if len(value.strip())<5:raise ValueError('Include a visible access or deletion note.')
        return value.strip()

class Access(Note):
    expected_version: int = Field(ge=1)
    allowed_roles: list[Literal['owner','security','engineer','approver','auditor']] = Field(max_length=5)
    allowed_users: list[str] = Field(default_factory=list,max_length=30)
    note: str = Field(min_length=5,max_length=500)

class Remove(Note):
    expected_version: int = Field(ge=1)
    note: str = Field(min_length=5,max_length=500)

class Replace(Note):
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=2,max_length=120)
    filename: str = Field(min_length=3,max_length=120)
    content_base64: str = Field(min_length=1,max_length=44000)
    language: Literal['English','Arabic','Bilingual'] = 'English'

    @field_validator('title')
    @classmethod
    def visible_title(cls,value):
        if len(value.strip())<2:raise ValueError('Use a visible document title.')
        return value.strip()

class Recover(Strict):
    key: str = Field(min_length=8,max_length=128)

def can_read(doc,user,environment):
    return bool(user.active) and doc.org_id==user.org_id and doc.env==environment and doc.status=='indexed' and (user.role in ('owner','security') or doc.author_id==user.id or user.role in doc.allowed_roles or user.id in doc.allowed_users)

def can_manage(doc,user,environment):
    return can_read(doc,user,environment) and (doc.author_id==user.id or 'policy' in PERMISSIONS.get(user.role,set()))

def metadata(doc):
    return {key:getattr(doc,key) for key in ('id','org_id','env','title','filename','author_id','language','content_hash','byte_count','allowed_roles','allowed_users','version','status','created','updated')}

def document_for(db,id,user,manage=False,environment=None):
    environment=runtime_environment(db,user.org_id,environment)
    doc=db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id==id,KnowledgeDocument.org_id==user.org_id,KnowledgeDocument.env==environment))
    if not doc or not can_read(doc,user,environment):fail(404,'DOCUMENT_NOT_FOUND','Document not found in your authorized scope.')
    if manage and not can_manage(doc,user,environment):fail(403,'DOCUMENT_OWNER_REQUIRED','Only the author or an authorized security/owner role can manage this document.')
    return doc

def validate_members(db,org,users):
    if users:
        valid=set(db.scalars(select(User.id).where(User.id.in_(users),User.org_id==org,User.active==1)).all())
        if valid!=set(users):fail(422,'INVALID_DOCUMENT_MEMBERS','All document readers must be active members of this organization.')

def decode(body):
    if body.filename!=PurePosixPath(body.filename).name or '\\' in body.filename or body.filename.rsplit('.',1)[-1].lower() not in ('txt','md','csv','json'):fail(422,'UNSUPPORTED_DOCUMENT','Use a plain filename ending in TXT, MD, CSV or JSON. PDF, DOCX and OCR are not enabled.')
    try:raw=base64.b64decode(body.content_base64,validate=True)
    except (ValueError,binascii.Error):fail(422,'INVALID_DOCUMENT_ENCODING','The document must use valid base64 encoding.')
    if not 1<=len(raw)<=32768:fail(413,'DOCUMENT_TOO_LARGE','UTF-8 document intake is limited to 32 KiB per file.')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:fail(422,'INVALID_DOCUMENT_TEXT','Use valid UTF-8 text.')
    if not text.strip() or '\x00' in text:fail(422,'INVALID_DOCUMENT_TEXT','Use nonempty UTF-8 text without null bytes.')
    ext=body.filename.rsplit('.',1)[-1].lower()
    if ext=='json':
        def reject_constant(value):raise ValueError('Non-finite JSON value')
        try:json.loads(text,parse_constant=reject_constant)
        except (ValueError,RecursionError):fail(422,'INVALID_DOCUMENT_JSON','The JSON document cannot be parsed.')
    if ext=='csv':
        try:list(csv.reader(io.StringIO(text),strict=True))
        except csv.Error:fail(422,'INVALID_DOCUMENT_CSV','The CSV document cannot be parsed.')
    return raw,text

def index_document(db,doc):
    environment=runtime_environment(db,doc.org_id,doc.env)
    for pos,start in enumerate(range(0,len(doc.content),620)):
        text=doc.content[start:start+700]
        db.add(DocumentChunk(org_id=doc.org_id,env=environment,document_id=doc.id,document_version=doc.version,position=pos,text=text,content_hash=digest(text)))

def allowed_docs(db,user,environment=None):
    environment=runtime_environment(db,user.org_id,environment)
    # Access is checked before any text/chunk enters the retrieval corpus.
    rows=db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.org_id==user.org_id,KnowledgeDocument.env==environment,KnowledgeDocument.status=='indexed').order_by(KnowledgeDocument.created.desc())).all()
    return [doc for doc in rows if can_read(doc,user,environment)]

def search_documents(db,user,query,top_k,environment=None,*,one_per_document=False):
    environment=runtime_environment(db,user.org_id,environment)
    docs=allowed_docs(db,user,environment);by_id={d.id:d for d in docs}
    terms=list(dict.fromkeys(search_tokens(query)))[:64]
    if not docs or not terms:return []
    corpus=db.scalars(select(DocumentChunk).where(DocumentChunk.org_id==user.org_id,DocumentChunk.env==environment,DocumentChunk.document_id.in_(by_id)).order_by(DocumentChunk.document_id,DocumentChunk.position)).all()
    corpus=[chunk for chunk in corpus if chunk.document_version==by_id[chunk.document_id].version]
    tokens=[Counter(search_tokens(c.text)) for c in corpus];average=sum(sum(t.values()) for t in tokens)/max(1,len(tokens)) or 1
    df={term:sum(term in t for t in tokens) for term in terms};ranked=[]
    for chunk,token in zip(corpus,tokens):
        score=0
        for term in terms:
            freq=token[term]
            if freq:score+=math.log(1+(len(tokens)-df[term]+.5)/(df[term]+.5))*freq*2.2/(freq+1.2*(.25+.75*sum(token.values())/average))
        if score:
            doc=by_id[chunk.document_id]
            ranked.append({'document_id':doc.id,'document_version':doc.version,'title':doc.title,'filename':doc.filename,'chunk':chunk.position+1,'excerpt':chunk.text,'sha256':chunk.content_hash,'score':round(score,5),'citation':f'{doc.id}:v{doc.version}:chunk{chunk.position+1}'})
    ordered=sorted(ranked,key=lambda r:(-r['score'],r['document_id'],r['chunk']))
    if one_per_document:
        seen=set();distinct=[]
        for hit in ordered:
            if hit['document_id'] not in seen:
                seen.add(hit['document_id']);distinct.append(hit)
        ordered=distinct
    return ordered[:top_k]

def register_documents(app,factory,settings,human):
    @app.get('/v1/documents')
    def listing(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db);rows=allowed_docs(db,user)
            return {'items':[metadata(d) for d in rows[offset:offset+limit]],'next_offset':offset+limit if len(rows)>offset+limit else None,'authorized_count':len(rows),'boundary':'Authorized text sources include reviewed file-extraction publications. Retrieval is ACL-filtered lexical search; vector retrieval and source ACL federation remain unimplemented.'}

    @app.post('/v1/documents',status_code=201)
    def upload(body:Upload,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        with factory.begin() as db:
            user=human(request,db,True,'operate')
            if not 8<=len(idempotency_key)<=128:fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use an 8–128 character upload key.')
            raw,text=decode(body);validate_members(db,user.org_id,body.allowed_users)
            db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            hashed=digest(canonical(body.model_dump()));existing=db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.org_id==user.org_id,KnowledgeDocument.env==runtime_environment(db,user.org_id),KnowledgeDocument.author_id==user.id,KnowledgeDocument.idem_key==idempotency_key))
            if existing:
                if existing.request_digest!=hashed:fail(409,'IDEMPOTENCY_CONFLICT','This upload key belongs to another document request.')
                if existing.status!='indexed':fail(409,'DOCUMENT_DELETED','This upload was deleted. Choose a new upload key to create a new document.')
                return metadata(existing)
            count=db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.org_id==user.org_id,KnowledgeDocument.env==runtime_environment(db,user.org_id),KnowledgeDocument.status=='indexed'))
            if count>=200:fail(429,'DOCUMENT_CAPACITY','This bounded workspace supports 200 active text documents.')
            doc=KnowledgeDocument(org_id=user.org_id,env=runtime_environment(db,user.org_id),title=body.title,filename=body.filename,author_id=user.id,language=body.language,content=text,content_hash=digest(text),byte_count=len(raw),allowed_roles=sorted(set(body.allowed_roles)),allowed_users=sorted(set(body.allowed_users)),idem_key=idempotency_key,request_digest=hashed)
            db.add(doc);db.flush();index_document(db,doc)
            audit(db,user.org_id,user.id,'document.ingested',detail={'document_id':doc.id,'version':doc.version,'bytes':doc.byte_count,'sha256':doc.content_hash})
            return metadata(doc)

    @app.get('/v1/documents/search')
    def search(request:Request,q:str=Query(min_length=2,max_length=1000),top_k:int=Query(5,ge=1,le=10),one_per_document:bool=False):
        with factory() as db:
            user=human(request,db);return {'items':search_documents(db,user,q,top_k,one_per_document=one_per_document),'method':'ACL-filtered BM25-style lexical ranking'+('; highest-ranked passage per document' if one_per_document else ''),'one_per_document':one_per_document,'normalization_version':NORMALIZATION_VERSION,'provider_calls':0}

    @app.post('/v1/documents/recover')
    def recover(body:Recover,request:Request):
        with factory() as db:
            user=human(request,db,True)
            doc=db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.org_id==user.org_id,KnowledgeDocument.env==runtime_environment(db,user.org_id),KnowledgeDocument.author_id==user.id,KnowledgeDocument.idem_key==body.key))
            if not doc:fail(404,'UPLOAD_INTENT_NOT_FOUND','No committed upload is visible for this intent. Retry the unchanged upload with the same key before starting a different intent.')
            return metadata(doc)

    @app.get('/v1/documents/{id}')
    def detail(id:str,request:Request):
        with factory() as db:
            user=human(request,db);doc=document_for(db,id,user)
            intake=db.scalar(select(IngestionJob).where(IngestionJob.document_id==doc.id,IngestionJob.org_id==user.org_id,IngestionJob.env==runtime_environment(db,user.org_id)))
            provenance=None if not intake else {'original_filename':intake.filename,'original_sha256':intake.original_sha256,'original_bytes':intake.original_bytes,'extraction':intake.extraction,'published_version':intake.published_version,'current_version_matches':intake.published_version==doc.version}
            return {**metadata(doc),'content':doc.content,'can_manage':can_manage(doc,user,runtime_environment(db,user.org_id)),'provenance':provenance}

    @app.get('/v1/documents/{id}/copies')
    def copies(id:str,request:Request,response:Response,expected_version:int=Query(...,ge=1),offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db);environment=runtime_environment(db,user.org_id)
            candidate=aliased(KnowledgeDocument)
            # One statement snapshots source version, candidates and their ACLs together.
            # Admission is bounded to 200 active documents per workspace/environment.
            rows=db.execute(select(KnowledgeDocument,candidate).outerjoin(candidate,
                (candidate.org_id==KnowledgeDocument.org_id)&(candidate.env==KnowledgeDocument.env)&
                (candidate.status=='indexed')&(candidate.content_hash==KnowledgeDocument.content_hash)&
                (candidate.id!=KnowledgeDocument.id)).where(
                    KnowledgeDocument.id==id,KnowledgeDocument.org_id==user.org_id,
                    KnowledgeDocument.env==environment,KnowledgeDocument.status=='indexed'
                ).order_by(candidate.created.desc(),candidate.id)).all()
            source=rows[0][0] if rows else None
            if not source or not can_read(source,user,environment):fail(404,'DOCUMENT_NOT_FOUND','Document not found in your authorized scope.')
            if source.version!=expected_version:fail(409,'STALE_VERSION','The source changed. Refresh it before reviewing copies.')
            if digest(source.content)!=source.content_hash:fail(409,'DOCUMENT_INTEGRITY_FAILED','The indexed source cannot be verified. Review its integrity before comparing copies.')
            # Apply visibility before equality, count and pagination. A digest match alone is insufficient.
            visible=[copy for _,copy in rows if copy is not None and can_read(copy,user,environment) and copy.content==source.content]
            fields=('id','title','filename','language','version','updated')
            response.headers['Cache-Control']='no-store'
            return {'scope':{'workspace_id':user.org_id,'account_id':user.id,'environment':environment},
                'source':{'id':source.id,'version':source.version,'content_sha256':source.content_hash},
                'items':[{key:getattr(copy,key) for key in fields} for copy in visible[offset:offset+limit]],
                'visible_count':len(visible),'offset':offset,'next_offset':offset+limit if len(visible)>offset+limit else None,
                'boundary':'Read-only exact indexed-text comparison of currently readable records. Different formatting, near copies and original binary files are not compared. No records are merged or deleted.'}

    @app.put('/v1/documents/{id}/access')
    def access(id:str,body:Access,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));doc=document_for(db,id,user,True)
            if doc.version!=body.expected_version:fail(409,'STALE_VERSION','Document permissions changed. Refresh before applying access changes.')
            from .neural_index_store import invalidate_source
            invalidate_source(db,user.org_id,doc.env,doc.id)
            validate_members(db,user.org_id,body.allowed_users)
            doc.allowed_roles=sorted(set(body.allowed_roles));doc.allowed_users=sorted(set(body.allowed_users));doc.version+=1;doc.updated=now()
            db.execute(update(DocumentChunk).where(DocumentChunk.document_id==doc.id,DocumentChunk.org_id==doc.org_id,DocumentChunk.env==doc.env).values(document_version=doc.version))
            audit(db,user.org_id,user.id,'document.access_changed',detail={'document_id':doc.id,'version':doc.version,'note':body.note.strip()});return metadata(doc)

    @app.delete('/v1/documents/{id}')
    def remove(id:str,body:Remove,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));doc=document_for(db,id,user,True)
            if doc.version!=body.expected_version:fail(409,'STALE_VERSION','Document changed. Refresh before deletion.')
            from .neural_index_store import invalidate_source
            invalidate_source(db,user.org_id,doc.env,doc.id)
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id==doc.id,DocumentChunk.org_id==user.org_id,DocumentChunk.env==runtime_environment(db,user.org_id)));doc.content='';doc.status='deleted';doc.version+=1;doc.updated=now()
            audit(db,user.org_id,user.id,'document.deleted',detail={'document_id':doc.id,'version':doc.version,'note':body.note.strip()})
            return {'id':doc.id,'status':'deleted','chunks_removed':True,'boundary':'Content is logically removed from active storage and retrieval. Backup/WAL erasure and retention policy remain deployment responsibilities.'}


    @app.get('/v1/documents/{id}/citations/{version}/{chunk}')
    def citation(id:str,version:int,chunk:int,request:Request):
        with factory() as db:
            user=human(request,db);doc=document_for(db,id,user)
            if version!=doc.version:fail(409,'STALE_CITATION','The source content or permissions changed. Search again for a current citation.')
            row=db.scalar(select(DocumentChunk).where(DocumentChunk.document_id==id,DocumentChunk.org_id==user.org_id,DocumentChunk.env==doc.env,DocumentChunk.document_version==version,DocumentChunk.position==chunk-1))
            if not row:fail(404,'CITATION_NOT_FOUND','The citation chunk is unavailable.')
            return {**metadata(doc),'chunk':chunk,'excerpt':row.text,'sha256':row.content_hash,'citation':f'{id}:v{version}:chunk{chunk}','verified_current':True}

    @app.put('/v1/documents/{id}/content')
    def replace(id:str,body:Replace,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        with factory.begin() as db:
            user=human(request,db,True,'operate')
            if not 8<=len(idempotency_key)<=128:fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use an 8–128 character update key.')
            db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            doc=document_for(db,id,user,True);hashed=digest(canonical({'document_id':id,**body.model_dump()}))
            previous=db.scalar(select(DocumentUpdate).where(DocumentUpdate.org_id==user.org_id,DocumentUpdate.env==runtime_environment(db,user.org_id),DocumentUpdate.author_id==user.id,DocumentUpdate.idem_key==idempotency_key))
            if previous:
                if previous.request_digest!=hashed:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to a different document update.')
                return {**previous.receipt,'current_version':doc.version,'replayed':True}
            if doc.version!=body.expected_version:fail(409,'STALE_VERSION','The source or permissions changed. Refresh and review the new source before replacing content.')
            raw,text=decode(body);old_hash=doc.content_hash
            from .neural_index_store import invalidate_source
            invalidate_source(db,user.org_id,doc.env,doc.id)
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id==id,DocumentChunk.org_id==user.org_id,DocumentChunk.env==runtime_environment(db,user.org_id)))
            doc.title=body.title;doc.filename=body.filename;doc.language=body.language;doc.content=text;doc.content_hash=digest(text);doc.byte_count=len(raw);doc.version+=1;doc.updated=now()
            index_document(db,doc);db.flush()
            receipt={**metadata(doc),'current_version':doc.version,'replayed':False}
            db.add(DocumentUpdate(org_id=user.org_id,env=doc.env,document_id=id,author_id=user.id,idem_key=idempotency_key,request_digest=hashed,receipt=receipt))
            audit(db,user.org_id,user.id,'document.content_replaced',detail={'document_id':id,'version':doc.version,'previous_sha256':old_hash,'sha256':doc.content_hash,'note':body.note.strip()})
            return receipt

    @app.post('/v1/documents/{id}/updates/recover')
    def recover_update(id:str,body:Recover,request:Request):
        with factory() as db:
            user=human(request,db,True);doc=document_for(db,id,user,True)
            receipt=db.scalar(select(DocumentUpdate).where(DocumentUpdate.document_id==id,DocumentUpdate.org_id==user.org_id,DocumentUpdate.env==runtime_environment(db,user.org_id),DocumentUpdate.author_id==user.id,DocumentUpdate.idem_key==body.key))
            if not receipt:fail(404,'UPDATE_INTENT_NOT_FOUND','No committed update is visible for this intent. Retry the unchanged request with its same key.')
            return {**receipt.receipt,'current_version':doc.version,'replayed':True}
