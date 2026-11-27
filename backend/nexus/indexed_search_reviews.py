"""Reviewer-labelled measurements of saved indexed searches; never reruns a model."""
import re
from typing import Literal
from fastapi import Request,Header,Query
from pydantic import Field,field_validator,model_validator
from sqlalchemy import select,update,func
from .db import WorkbenchRun,NeuralIndex,KnowledgeDocument,Organization
from .hybrid import owned_run,visible_run
from .neural_index_store import load_index
from .retrieval_checks import CheckCase
from .retrieval_metrics import measure_case
from .schemas import Strict
from .documents import document_for,can_read
from .runtime_context import runtime_environment
from .security import fail,digest,PERMISSIONS
from .service import canonical,audit

KIND='indexed_search_review'
BOUNDARY='Reviewer-labelled saved retrieval measurements only. No model execution, generated-answer grading, independent quality acceptance or production certification.'


class Review(Strict):
    search_id:str=Field(min_length=1,max_length=64)
    expectation:Literal['retrieve','no_results']='retrieve'
    expected_document_ids:list[str]=Field(default_factory=list,max_length=5)
    query_language:Literal['English','Arabic','Bilingual']|None=None
    minimum_precision_percent:int|None=Field(default=None,ge=0,le=100,strict=True)
    note:str=Field(min_length=5,max_length=500)

    @model_validator(mode='after')
    def valid_labels(self):
        CheckCase(query='saved search',expectation=self.expectation,expected_document_ids=self.expected_document_ids,
            query_language=self.query_language,minimum_precision_percent=self.minimum_precision_percent)
        return self

    @field_validator('note')
    @classmethod
    def visible_note(cls,value):
        if len(value.strip())<5:raise ValueError('Include a reviewer note.')
        return value.strip()


class Compare(Strict):
    baseline_id:str=Field(min_length=1,max_length=64)
    candidate_id:str=Field(min_length=1,max_length=64)


class Recover(Strict):
    key:str=Field(pattern=r'^[A-Za-z0-9_-]{16,100}$')


def search_digest(row):
    return digest(canonical({'status':row.status,'result':row.result}))


def review_for(db,id,user):
    row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.id==id,WorkbenchRun.org_id==user.org_id,
        WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND))
    if not row or row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set()):
        fail(404,'INDEX_REVIEW_NOT_FOUND','Review is unavailable in your scope.')
    return row


def detail(db,row,user):
    result=row.result;environment=runtime_environment(db,user.org_id);stale=False
    for id,snapshot in result['source_versions'].items():
        doc=db.get(KnowledgeDocument,id)
        if not doc or not can_read(doc,user,environment):fail(404,'INDEX_REVIEW_NOT_FOUND','Review sources are no longer visible in this scope.')
        stale=stale or doc.version!=snapshot['version'] or doc.content_hash!=snapshot['sha256']
    search=owned_run(db,result['labels']['search_id'],user)
    if search_digest(search)!=result['search_digest']:fail(409,'INDEX_REVIEW_CHANGED','The underlying saved search changed.')
    snapshots=result.get('indexes') or {result['index']['id']:result['index']}
    for id,snapshot in snapshots.items():
        index=db.scalar(select(NeuralIndex).where(NeuralIndex.id==id,NeuralIndex.org_id==user.org_id,NeuralIndex.env==environment))
        stale=stale or not index or index.status!='ready' or index.version!=snapshot['version'] or index.content_hash!=snapshot['sha256']
    return {'id':row.id,'created':row.created,'status':row.status,'labels':result['labels'],'measurements':result['measurements'],
        'search_id':search.id,'index_ids':list(snapshots),'index_id':result['index']['id'],'parameters':search.result['parameters'],
        'stale':bool(stale),'review_provider_calls':0,'original_search_provider_calls':visible_run(db,search,user)['provider_calls'],
        'query_text_stored':False,'boundary':BOUNDARY}


def register_indexed_search_reviews(app,factory,human):
    @app.post('/v1/indexed-search-reviews/compare')
    def compare(body:Compare,request:Request):
        with factory() as db:
            user=human(request,db,True)
            if body.baseline_id==body.candidate_id:fail(422,'INDEX_COMPARE_DISTINCT_REQUIRED','Choose two different saved reviews.')
            left=review_for(db,body.baseline_id,user);right=review_for(db,body.candidate_id,user)
            baseline=detail(db,left,user);candidate=detail(db,right,user)
            from .indexed_review_comparison import compare_reviews
            return compare_reviews(baseline,candidate,owned_run(db,baseline['search_id'],user),owned_run(db,candidate['search_id'],user),left,right)

    @app.get('/v1/indexed-search-reviews')
    def listing(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db);query=select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,
                WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND)
            if 'policy' not in PERMISSIONS.get(user.role,set()):query=query.where(WorkbenchRun.author_id==user.id)
            # Filter inaccessible reviews before counting/paging, without exposing IDs.
            visible=[]
            from fastapi import HTTPException
            for row in db.scalars(query.order_by(WorkbenchRun.created.desc(),WorkbenchRun.id).limit(1000)):
                try:visible.append(detail(db,row,user))
                except HTTPException as exc:
                    if exc.status_code!=404:raise
            return {'items':visible[offset:offset+limit],'next_offset':offset+limit if len(visible)>offset+limit else None,'boundary':BOUNDARY}

    @app.get('/v1/indexed-search-reviews/{id}')
    def inspect(id:str,request:Request):
        with factory() as db:
            user=human(request,db);return detail(db,review_for(db,id,user),user)

    @app.post('/v1/indexed-search-reviews/recover')
    def recover(body:Recover,request:Request):
        with factory.begin() as db:
            user=human(request,db,True)
            rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND,WorkbenchRun.author_id==user.id))
            row=next((r for r in rows if r.result.get('key')==digest(body.key)),None)
            if not row:fail(404,'INDEX_REVIEW_NOT_FOUND','No review matches this account and key.')
            return detail(db,row,user)

    @app.post('/v1/indexed-search-reviews',status_code=201)
    def create(body:Review,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',idempotency_key):fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use a 16–100 character intent key.')
        labels=body.model_dump(exclude_none=True);key=digest(idempotency_key);fingerprint=digest(canonical(labels))
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
            rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND,WorkbenchRun.author_id==user.id))
            previous=next((r for r in rows if r.result.get('key')==key),None)
            if previous:
                if previous.result['fingerprint']!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another review.')
                return detail(db,previous,user)
            search=owned_run(db,body.search_id,user);value=visible_run(db,search,user);parameters=value['parameters']
            if search.status!='completed' or parameters.get('retrieval_mode')!='local_indexed':
                fail(409,'INDEX_REVIEW_SEARCH_UNSUPPORTED','Choose a completed stored-index search.')
            if value['withheld_stale_or_inaccessible'] or not value['normalization_current']:
                fail(409,'INDEX_REVIEW_SEARCH_STALE','Run a new search before reviewing changed evidence.')
            versions=parameters.get('index_versions') or {parameters['index_id']:parameters['index_version']}
            docs={};snapshots={}
            for id,version in versions.items():
                index,_,sources,_=load_index(db,user,id,model=parameters['embedding_model'],model_digest=parameters['embedding_digest'])
                if index.version!=version:fail(409,'INDEX_REVIEW_SEARCH_STALE','An indexed snapshot changed.')
                docs.update(sources);snapshots[id]={'id':id,'version':index.version,'sha256':index.content_hash}
            index_snapshot=next(iter(snapshots.values()))
            for id in set(body.expected_document_ids)|{hit['document_id'] for hit in value['items']}:
                docs[id]=document_for(db,id,user)
            count=db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind==KIND))
            if count>=1000:fail(429,'INDEX_REVIEW_CAPACITY','This environment reached its bounded review capacity.')
            ids=list(dict.fromkeys(hit['document_id'] for hit in value['items']));expected=set(body.expected_document_ids);found=expected.intersection(ids)
            ranks=[i+1 for i,hit in enumerate(value['items']) if hit['document_id'] in expected]
            measured=measure_case({'expectation':body.expectation,'expected_document_ids':body.expected_document_ids,'retrieved_document_ids':ids,
                **({'minimum_precision_percent':body.minimum_precision_percent} if body.minimum_precision_percent is not None else {}),
                'document_recall_at_k':len(found)/len(expected) if expected else None,'reciprocal_rank':1/min(ranks) if ranks else 0})
            passed=(not ids) if body.expectation=='no_results' else found==expected and measured.get('precision_threshold_passed',True)
            measured['passed']=bool(passed)
            row=WorkbenchRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),author_id=user.id,kind=KIND,status='passed' if passed else 'failed',duration_ms=0,
                result={'key':key,'fingerprint':fingerprint,'labels':labels,'measurements':measured,'search_digest':search_digest(search),
                    'index':index_snapshot,'indexes':snapshots,
                    'source_versions':{id:{'version':doc.version,'sha256':doc.content_hash} for id,doc in docs.items()}})
            db.add(row);db.flush();audit(db,user.org_id,user.id,'retrieval.index.reviewed',detail={'review_id':row.id,'search_id':search.id,'status':row.status})
            return detail(db,row,user)
