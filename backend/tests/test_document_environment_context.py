"""Synthetic internal contexts test propagation; public switching stays disabled."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from conftest import auth
from nexus.db import User, KnowledgeDocument, DocumentChunk, RetrievalCheck, WorkbenchRun, IngestionJob
from nexus.documents import index_document, allowed_docs, search_documents, document_for, can_read
from nexus.runtime_context import bind_runtime_context
from nexus.retrieval_checks import CheckInput, execute, checked_detail
from nexus.hybrid import visible_run, register_hybrid, KIND
from nexus.ingestion import run_ingestion_once, job_for
from nexus.security import digest


@pytest.fixture
def corpus(ctx):
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
        ids={'owner':owner.id}
        for environment in ('staging','production'):
            text=f'{environment} procurement evidence needle'
            doc=KnowledgeDocument(org_id=owner.org_id,env=environment,title=environment,filename='evidence.txt',author_id=owner.id,content=text,content_hash=digest(text),byte_count=len(text),idem_key='synthetic-'+environment,request_digest=environment)
            db.add(doc);db.flush();index_document(db,doc);ids[environment]=doc.id
    return ids


def test_document_corpus_chunks_and_cached_acl_follow_bound_context(ctx,corpus):
    with ctx['db']() as db:
        owner=db.get(User,corpus['owner'])
        stage=db.get(KnowledgeDocument,corpus['staging'])
        production=db.get(KnowledgeDocument,corpus['production'])
        bind_runtime_context(db,owner.org_id,'production')
        assert not can_read(stage,owner,'production')
        assert can_read(production,owner,'production')
        assert [d.id for d in allowed_docs(db,owner)]==[production.id]
        assert {h['document_id'] for h in search_documents(db,owner,'needle',5)}=={production.id}
        assert document_for(db,production.id,owner).id==production.id
        with pytest.raises(HTTPException) as denied:document_for(db,stage.id,owner)
        assert denied.value.status_code==404
        assert {c.env for c in db.scalars(select(DocumentChunk))}=={'production'}
        owner.active=0
        assert not can_read(production,owner,'production')


def test_lexical_search_excludes_chunks_from_old_document_revision(ctx,corpus):
    with ctx['db'].begin() as db:
        db.add(DocumentChunk(org_id='northstar',env='production',document_id=corpus['production'],document_version=0,position=99,text='obsoleteuniquemarker',content_hash=digest('obsoleteuniquemarker')))
    with ctx['db']() as db:
        owner=db.get(User,corpus['owner']);bind_runtime_context(db,owner.org_id,'production')
        assert search_documents(db,owner,'obsoleteuniquemarker',5)==[]
        assert search_documents(db,owner,'needle',5)[0]['document_version']==1


def test_retrieval_evidence_rejects_cached_foreign_context_and_sources(ctx,corpus):
    body=CheckInput(name='Production evidence',cases=[{'query':'needle','expected_document_ids':[corpus['production']]}])
    with ctx['db'].begin() as db:
        owner=db.get(User,corpus['owner']);bind_runtime_context(db,owner.org_id,'production')
        result=execute(db,owner,body)
        assert result['all_cases_passed'] and result['authorized_corpus_count']==1
        assert set(result['source_versions'])=={corpus['production']}
        record=RetrievalCheck(org_id=owner.org_id,env='production',author_id=owner.id,name=body.name,config=body.model_dump(),result=result,idem_key='synthetic-check',request_digest='check')
        db.add(record);db.flush();record_id=record.id
        assert checked_detail(db,record,owner)['stale'] is False
    with ctx['db']() as db:
        owner=db.get(User,corpus['owner']);record=db.get(RetrievalCheck,record_id)
        bind_runtime_context(db,owner.org_id,'staging')
        with pytest.raises(HTTPException) as denied:checked_detail(db,record,owner)
        assert denied.value.status_code==404
        # Even a same-context receipt cannot deliver evidence referencing another context.
        record.env='staging'
        with db.no_autoflush:
            with pytest.raises(HTTPException) as denied:checked_detail(db,record,owner)
        assert denied.value.status_code==409


def test_hybrid_history_rechecks_cached_run_and_source_scope(ctx,corpus):
    with ctx['db']() as db:
        owner=db.get(User,corpus['owner']);doc=db.get(KnowledgeDocument,corpus['production'])
        chunk=db.scalar(select(DocumentChunk).where(DocumentChunk.document_id==doc.id))
        hit={'document_id':doc.id,'document_version':1,'position':0,'sha256':chunk.content_hash,'score':1,'semantic_score':1,'lexical_score':1}
        foreign=WorkbenchRun(org_id=owner.org_id,env='production',kind=KIND,status='completed',author_id=owner.id,duration_ms=0,result={'hits':[hit]})
        local=WorkbenchRun(org_id=owner.org_id,env='staging',kind=KIND,status='completed',author_id=owner.id,duration_ms=0,result={'hits':[hit]})
        bind_runtime_context(db,owner.org_id,'staging')
        with pytest.raises(HTTPException) as denied:visible_run(db,foreign,owner)
        assert denied.value.status_code==404
        rendered=visible_run(db,local,owner)
        assert rendered['items']==[] and rendered['withheld_stale_or_inaccessible']==1


def test_hybrid_late_context_change_withholds_computed_result(ctx,corpus,monkeypatch):
    # Only this isolated test app binds synthetic contexts; real authorization is unchanged.
    selected={'environment':'staging'}
    def human(request,db,*args,**kwargs):
        user=db.get(User,corpus['owner']);bind_runtime_context(db,user.org_id,selected['environment']);return user
    def compute(payload):
        selected['environment']='production'
        return {'scores':[],'rank':0,'vocabulary':0}
    monkeypatch.setattr('nexus.hybrid.compute',compute)
    app=FastAPI();register_hybrid(app,ctx['db'],ctx['settings'],human)
    with TestClient(app) as client:
        response=client.post('/v1/hybrid-search',headers={'Idempotency-Key':'context-change-001'},json={'query':'needle','dimensions':2})
    assert response.status_code==403,response.text
    assert response.json()['detail']['code']=='SEARCH_SCOPE_CHANGED'
    with ctx['db']() as db:
        row=db.scalar(select(WorkbenchRun).where(WorkbenchRun.kind==KIND))
        assert row.env=='staging' and not row.result.get('hits')


def test_intake_result_cannot_follow_job_into_another_context(ctx):
    from test_ingestion import create
    job=create(ctx)
    def changed(data,record,settings):
        # Simulate an out-of-band operator repair while extraction is running.
        with ctx['db'].begin() as db:
            db.execute(update(IngestionJob).where(IngestionJob.id==record.id).values(env='production'))
        return {'text':'must not be delivered','info':{}}
    assert run_ingestion_once(ctx['db'],ctx['settings'],extractor=changed)
    with ctx['db']() as db:
        row=db.get(IngestionJob,job['id']);owner=db.get(User,row.author_id)
        assert row.env=='production' and row.status=='processing'
        assert row.extracted_text=='' and row.document_id is None
        bind_runtime_context(db,owner.org_id,'staging')
        with pytest.raises(HTTPException) as denied:job_for(db,row.id,owner)
        assert denied.value.status_code==404


def test_public_document_request_cannot_select_production(ctx,corpus):
    headers,_=auth(ctx);headers['X-Nexus-Environment']='production'
    response=ctx['client'].get('/v1/documents',headers=headers)
    assert response.status_code==409,response.text


def test_internal_document_lifecycle_and_recovery_keep_environment(ctx,corpus):
    from nexus.documents import register_documents
    from nexus.retrieval_checks import register_retrieval_checks
    from test_documents import payload
    from test_document_lifecycle import replace_body, suite
    selected={'environment':'production'}
    def human(request,db,*args,**kwargs):
        user=db.get(User,corpus['owner']);bind_runtime_context(db,user.org_id,selected['environment']);return user
    app=FastAPI()
    register_documents(app,ctx['db'],ctx['settings'],human)
    register_retrieval_checks(app,ctx['db'],ctx['settings'],human)
    with TestClient(app) as client:
        key='production-upload-001'
        uploaded=client.post('/v1/documents',headers={'Idempotency-Key':key},json=payload())
        assert uploaded.status_code==201,uploaded.text
        doc=uploaded.json();assert doc['env']=='production'
        url='/v1/documents/'+doc['id']
        assert client.get(url+'/citations/1/1').status_code==200
        response=client.put(url+'/content',headers={'Idempotency-Key':'production-replace-001'},json=replace_body())
        assert response.status_code==200,response.text
        assert response.json()['env']=='production'
        assert client.post(url+'/updates/recover',json={'key':'production-replace-001'}).json()['version']==2
        check=client.post('/v1/retrieval-checks',headers={'Idempotency-Key':'production-check-001'},json=suite(doc['id']))
        assert check.status_code==201,check.text
        selected['environment']='staging'
        assert client.get(url).status_code==404
        assert client.post('/v1/documents/recover',json={'key':key}).status_code==404
        assert client.post('/v1/retrieval-checks/recover',json={'key':'production-check-001'}).status_code==404
        selected['environment']='production'
        assert client.post('/v1/documents/recover',json={'key':key}).json()['id']==doc['id']
        removed=client.request('DELETE',url,json={'expected_version':2,'note':'Remove synthetic production source.'})
        assert removed.status_code==200,removed.text
    with ctx['db']() as db:
        assert db.get(KnowledgeDocument,corpus['staging']).status=='indexed'
        assert db.get(KnowledgeDocument,doc['id']).env=='production'
        assert db.scalars(select(DocumentChunk).where(DocumentChunk.document_id==doc['id'])).all()==[]
