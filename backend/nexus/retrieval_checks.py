"""Persisted retrieval regression evidence for the current authorized text corpus.

No answer generation, external provider, semantic relevance grading or automated
production certification is performed by these checks.
"""
from typing import Literal
from fastapi import Request, Header, Query
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select, update, func
from .schemas import Strict
from .db import RetrievalCheck, Organization, KnowledgeDocument, now, public
from .documents import document_for, search_documents, can_read
from .service import audit, canonical
from .security import fail, digest, PERMISSIONS


class CheckCase(Strict):
    query: str = Field(min_length=2,max_length=300)
    expected_document_ids: list[str] = Field(default_factory=list,max_length=5)
    expectation: Literal['retrieve','no_results'] = 'retrieve'

    @field_validator('query')
    @classmethod
    def visible_query(cls,value):
        if len(value.strip())<2:raise ValueError('Include a visible test query.')
        return value.strip()

    @model_validator(mode='after')
    def expected_sources(self):
        if len(set(self.expected_document_ids))!=len(self.expected_document_ids):raise ValueError('Expected documents must be distinct.')
        if self.expectation=='retrieve' and not self.expected_document_ids:raise ValueError('Positive cases require at least one expected document.')
        if self.expectation=='no_results' and self.expected_document_ids:raise ValueError('Negative cases cannot declare expected documents.')
        return self


class CheckInput(Strict):
    name: str = Field(min_length=2,max_length=120)
    top_k: int = Field(default=5,ge=1,le=10)
    cases: list[CheckCase] = Field(min_length=1,max_length=20)

    @field_validator('name')
    @classmethod
    def visible_name(cls,value):
        if len(value.strip())<2:raise ValueError('Use a visible check name.')
        return value.strip()


class Recover(Strict):
    key: str = Field(min_length=8,max_length=128)


class Removal(Strict):
    note: str = Field(min_length=5,max_length=500)

    @field_validator('note')
    @classmethod
    def visible_note(cls,value):
        if len(value.strip())<5:raise ValueError('Include a visible removal note.')
        return value.strip()


def accessible(record,user):
    return record.org_id==user.org_id and record.env=='staging' and (record.author_id==user.id or 'policy' in PERMISSIONS.get(user.role,set()))


def summary(record):
    return {'id':record.id,'name':record.name,'author_id':record.author_id,'created':record.created,'status':'passed' if record.result['all_cases_passed'] else 'failed','case_count':len(record.config['cases']),'passed_cases':record.result['passed_cases'],'top_k':record.config['top_k']}


def checked_detail(db,record,user):
    # Saved test queries/results are author/admin-only. Historical evidence never
    # bypasses a revoked/deleted source ACL. No excerpts are retained in evidence.
    versions=record.result['source_versions'];current={}
    for id in versions:
        doc=db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id==id,KnowledgeDocument.org_id==user.org_id))
        if not doc or not can_read(doc,user):fail(409,'EVIDENCE_ACCESS_CHANGED','A referenced source is no longer readable. Create a new suite from currently authorized sources.')
        current[id]=doc.version
    from .documents import allowed_docs
    corpus=[{'id':doc.id,'version':doc.version,'sha256':doc.content_hash} for doc in allowed_docs(db,user)]
    fingerprint=digest(canonical(sorted(corpus,key=lambda r:r['id'])))
    return {**summary(record),'config':record.config,'result':record.result,'stale':fingerprint!=record.result['corpus_fingerprint'] or any(current[id]!=v for id,v in versions.items()),'boundary':'Measured document retrieval for the recorded actor and corpus at one time. No generated-answer grading or production acceptance.'}


def record_for(db,id,user):
    record=db.scalar(select(RetrievalCheck).where(RetrievalCheck.id==id,RetrievalCheck.org_id==user.org_id,RetrievalCheck.env=='staging'))
    if not record or not accessible(record,user):fail(404,'RETRIEVAL_CHECK_NOT_FOUND','Retrieval evidence is not visible to this account.')
    return record


def execute(db,user,body):
    source_versions={};results=[]
    for case in body.cases:
        for id in case.expected_document_ids:
            doc=document_for(db,id,user);source_versions[id]=doc.version
        hits=search_documents(db,user,case.query,body.top_k)
        ids=list(dict.fromkeys(hit['document_id'] for hit in hits))
        for hit in hits:source_versions[hit['document_id']]=hit['document_version']
        expected=set(case.expected_document_ids);found=expected.intersection(ids)
        ranks=[i+1 for i,hit in enumerate(hits) if hit['document_id'] in expected]
        passed=bool(not ids) if case.expectation=='no_results' else found==expected
        results.append({'query':case.query,'expectation':case.expectation,'expected_document_ids':case.expected_document_ids,'retrieved_document_ids':ids,'citations':[hit['citation'] for hit in hits],'passed':passed,'document_recall_at_k':len(found)/len(expected) if expected else None,'reciprocal_rank':1/min(ranks) if ranks else 0})
    positives=[r for r in results if r['expectation']=='retrieve'];passed=sum(r['passed'] for r in results)
    # Fingerprint all currently readable source versions, including sources that
    # did not match; later evidence can distinguish a changed corpus.
    from .documents import allowed_docs
    corpus=[{'id':doc.id,'version':doc.version,'sha256':doc.content_hash} for doc in allowed_docs(db,user)]
    return {'all_cases_passed':passed==len(results),'passed_cases':passed,'total_cases':len(results),'mean_document_recall_at_k':sum(r['document_recall_at_k'] for r in positives)/len(positives) if positives else None,'mean_reciprocal_rank':sum(r['reciprocal_rank'] for r in positives)/len(positives) if positives else None,'cases':results,'source_versions':source_versions,'corpus_fingerprint':digest(canonical(sorted(corpus,key=lambda r:r['id']))),'authorized_corpus_count':len(corpus),'actor_id':user.id,'actor_role':user.role,'checked_at':now(),'provider_calls':0,'method':'Current-ACL BM25-style lexical retrieval; document recall and first expected chunk rank'}


def register_retrieval_checks(app,factory,settings,human):
    @app.get('/v1/retrieval-checks')
    def listing(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db)
            query=select(RetrievalCheck).where(RetrievalCheck.org_id==user.org_id,RetrievalCheck.env=='staging')
            if 'policy' not in PERMISSIONS.get(user.role,set()):query=query.where(RetrievalCheck.author_id==user.id)
            rows=db.scalars(query.order_by(RetrievalCheck.created.desc(),RetrievalCheck.id).offset(offset).limit(limit+1)).all()
            return {'items':[summary(r) for r in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}

    @app.post('/v1/retrieval-checks',status_code=201)
    def create(body:CheckInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        with factory.begin() as db:
            user=human(request,db,True,'operate')
            if not 8<=len(idempotency_key)<=128:fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use an 8–128 character check key.')
            db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            hashed=digest(canonical(body.model_dump()));previous=db.scalar(select(RetrievalCheck).where(RetrievalCheck.org_id==user.org_id,RetrievalCheck.author_id==user.id,RetrievalCheck.idem_key==idempotency_key))
            if previous:
                if previous.request_digest!=hashed:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another retrieval check.')
                return checked_detail(db,previous,user)
            count=db.scalar(select(func.count()).select_from(RetrievalCheck).where(RetrievalCheck.org_id==user.org_id))
            if count>=100:fail(429,'CHECK_CAPACITY','Retain at most 100 check records per workspace; remove obsolete evidence before creating more.')
            result=execute(db,user,body)
            record=RetrievalCheck(org_id=user.org_id,author_id=user.id,name=body.name,config=body.model_dump(),result=result,idem_key=idempotency_key,request_digest=hashed)
            db.add(record);db.flush()
            audit(db,user.org_id,user.id,'retrieval.checked',detail={'check_id':record.id,'cases':len(body.cases),'passed':result['passed_cases'],'corpus_fingerprint':result['corpus_fingerprint']})
            return checked_detail(db,record,user)

    @app.post('/v1/retrieval-checks/recover')
    def recover(body:Recover,request:Request):
        with factory() as db:
            user=human(request,db,True)
            record=db.scalar(select(RetrievalCheck).where(RetrievalCheck.org_id==user.org_id,RetrievalCheck.env=='staging',RetrievalCheck.author_id==user.id,RetrievalCheck.idem_key==body.key))
            if not record:fail(404,'CHECK_INTENT_NOT_FOUND','No committed check is visible. Retry the unchanged request using the same key.')
            return summary(record)

    @app.get('/v1/retrieval-checks/{id}')
    def detail(id:str,request:Request):
        with factory() as db:
            user=human(request,db);return checked_detail(db,record_for(db,id,user),user)

    @app.delete('/v1/retrieval-checks/{id}')
    def remove(id:str,body:Removal,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));record=record_for(db,id,user)
            db.delete(record);audit(db,user.org_id,user.id,'retrieval.evidence_removed',detail={'check_id':id,'note':body.note})
            return {'id':id,'status':'removed','boundary':'Active evidence removed; audit and backup retention remain separate.'}
