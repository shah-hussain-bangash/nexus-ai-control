import base64
from sqlalchemy import select,func,delete
from conftest import auth
from test_documents import upload,payload
from nexus.db import DocumentChunk,KnowledgeDocument,DocumentUpdate,RetrievalCheck,IngestionJob,User,Audit,SchemaVersion,migrate

def replace_body(version=1,text='Updated procurement replacement evidence.',**changes):
    return {'title':'Updated evidence','filename':'updated.txt','content_base64':base64.b64encode(text.encode()).decode(),'language':'English','expected_version':version,'note':'Replace obsolete purchasing guidance.',**changes}

def replace(ctx,id,**changes):
    h,_=auth(ctx);h['Idempotency-Key']='document-content-key-001'
    return ctx['client'].put('/v1/documents/'+id+'/content',headers=h,json=replace_body(**changes))

def suite(id,**changes):
    return {'name':'Purchasing source checks','top_k':5,'cases':[{'query':'procurement','expected_document_ids':[id]},{'query':'unmatchablewordxyz','expectation':'no_results','expected_document_ids':[]}],**changes}

def run(ctx,body,key='retrieval-check-key-001',role='owner'):
    h,_=auth(ctx,role);h['Idempotency-Key']=key
    return ctx['client'].post('/v1/retrieval-checks',headers=h,json=body)

def test_replace_is_atomic_idempotent_preserves_acl_and_invalidates_citations(ctx):
    doc=upload(ctx,allowed_roles=['auditor']);id=doc['id'];url='/v1/documents/'+id
    old=ctx['client'].get('/v1/documents/search?q=needle').json()['items'][0]
    assert ctx['client'].get(url+'/citations/1/1').json()['verified_current']
    updated=replace(ctx,id);assert updated.status_code==200,updated.text
    assert updated.json()['version']==2 and updated.json()['allowed_roles']==['auditor']
    assert ctx['client'].get(url+'/citations/1/1').status_code==409
    assert ctx['client'].get(url+'/citations/2/1').json()['excerpt'].startswith('Updated')
    assert ctx['client'].get('/v1/documents/search?q=needle').json()['items']==[]
    hits=ctx['client'].get('/v1/documents/search?q=replacement').json()['items'];assert hits[0]['citation']==id+':v2:chunk1'
    assert replace(ctx,id).json()['replayed'] is True
    assert replace(ctx,id,text='Different content').status_code==409
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(DocumentUpdate))==1
        assert all(c.document_version==2 and 'needle' not in c.text for c in db.scalars(select(DocumentChunk)).all())
        assert not any('replacement evidence' in str(a.detail) for a in db.scalars(select(Audit)).all())
    h,_=auth(ctx);assert ctx['client'].post(url+'/updates/recover',headers=h,json={'key':'document-content-key-001'}).json()['version']==2
    auth(ctx,'auditor');assert ctx['client'].get(url+'/citations/2/1').status_code==200
    assert ctx['client'].get(url+'/citations/2/999').status_code==404
    auth(ctx,org='other');assert ctx['client'].get(url+'/citations/1/1').status_code==404

def test_replace_requires_current_version_csrf_author_and_valid_content(ctx):
    doc=upload(ctx);id=doc['id'];url='/v1/documents/'+id+'/content'
    assert replace(ctx,id,version=99).status_code==409
    assert replace(ctx,id,filename='unsafe.pdf').status_code==422
    assert ctx['client'].get('/v1/documents/'+id).json()['version']==1
    assert ctx['client'].put(url,json=replace_body()).status_code==403
    with ctx['db'].begin() as db:
        db.add(User(id='reader-eng',org_id='northstar',email='reader@x.invalid',name='Reader',role='engineer'))
        db.get(KnowledgeDocument,id).allowed_roles=['engineer']
    h,_=auth(ctx,'engineer');h['Idempotency-Key']='other-author-update-01'
    assert ctx['client'].put(url,headers=h,json=replace_body()).status_code==403
    assert ctx['client'].post('/v1/documents/'+id+'/updates/recover',headers=h,json={'key':'document-content-key-001'}).status_code==403

def test_acl_change_invalidates_old_citation_and_deleted_source_does_not_leak(ctx):
    doc=upload(ctx);h,_=auth(ctx);id=doc['id'];url='/v1/documents/'+id
    assert ctx['client'].put(url+'/access',headers=h,json={'expected_version':1,'allowed_roles':['auditor'],'note':'Share purchasing source for review.'}).status_code==200
    assert ctx['client'].get(url+'/citations/1/1').status_code==409
    assert ctx['client'].request('DELETE',url,headers=h,json={'expected_version':2,'note':'Remove test source permanently.'}).status_code==200
    assert ctx['client'].get(url+'/citations/2/1').status_code==404
    assert replace(ctx,id).status_code==404

def test_retrieval_suite_stores_real_metrics_idempotent_and_author_scoped(ctx):
    doc=upload(ctx);r=run(ctx,suite(doc['id']));assert r.status_code==201,r.text
    e=r.json();assert e['status']=='passed' and e['passed_cases']==2 and e['stale'] is False
    assert e['result']['mean_document_recall_at_k']==1 and e['result']['mean_reciprocal_rank']==1
    assert e['result']['provider_calls']==0 and len(e['result']['corpus_fingerprint'])==64
    assert run(ctx,suite(doc['id'])).json()['id']==e['id']
    assert run(ctx,suite(doc['id'],name='Different suite')).status_code==409
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(RetrievalCheck))==1
    h,_=auth(ctx);assert ctx['client'].post('/v1/retrieval-checks/recover',headers=h,json={'key':'retrieval-check-key-001'}).json()['id']==e['id']
    auth(ctx,'auditor');assert ctx['client'].get('/v1/retrieval-checks').json()['items']==[]
    assert ctx['client'].get('/v1/retrieval-checks/'+e['id']).status_code==404
    auth(ctx,org='other');assert ctx['client'].get('/v1/retrieval-checks/'+e['id']).status_code==404

def test_failed_expectations_are_evidence_not_api_errors_and_update_marks_stale(ctx):
    doc=upload(ctx);body=suite(doc['id'],cases=[{'query':'unmatchablewordxyz','expected_document_ids':[doc['id']]},{'query':'procurement','expectation':'no_results'}])
    e=run(ctx,body).json();assert e['status']=='failed' and e['passed_cases']==0
    assert e['result']['mean_document_recall_at_k']==0
    assert replace(ctx,doc['id']).status_code==200
    assert ctx['client'].get('/v1/retrieval-checks/'+e['id']).json()['stale'] is True
    assert run(ctx,body,key='retrieval-check-key-002').json()['stale'] is False

def test_checks_revalidate_acl_and_never_retain_excerpts(ctx):
    with ctx['db'].begin() as db:db.add(User(id='check-eng',org_id='northstar',email='check@x.invalid',name='Checker',role='engineer'))
    doc=upload(ctx,allowed_roles=['engineer']);e=run(ctx,suite(doc['id']),role='engineer').json();assert e['status']=='passed'
    assert 'needle' not in str(e['result'])
    h,_=auth(ctx);assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=h,json={'expected_version':1,'allowed_roles':[],'note':'Revoke access after test completion.'}).status_code==200
    auth(ctx,'engineer');assert ctx['client'].get('/v1/retrieval-checks/'+e['id']).status_code==409
    assert run(ctx,suite(doc['id']),key='retrieval-check-key-002',role='engineer').status_code==404
    h,_=auth(ctx,'engineer');assert ctx['client'].request('DELETE','/v1/retrieval-checks/'+e['id'],headers=h,json={'note':'Remove stale access-limited evidence.'}).status_code==200
    assert ctx['client'].get('/v1/retrieval-checks/'+e['id']).status_code==404

def test_suite_limits_schema_and_csrf(ctx):
    doc=upload(ctx);b=suite(doc['id'])
    for change in [{'cases':[]},{'top_k':11},{'cases':[{'query':'x','expected_document_ids':[doc['id']]}]},{'cases':[{'query':'needle','expected_document_ids':[]}]},{'cases':[{'query':'needle','expectation':'no_results','expected_document_ids':[doc['id']]}]}]:
        assert run(ctx,{**b,**change}).status_code==422
    assert ctx['client'].post('/v1/retrieval-checks',json=b).status_code==403
    assert run(ctx,b,role='auditor').status_code==403
    assert run(ctx,suite('other-source')).status_code==404

def test_schema_six_upgrade_preserves_documents(ctx):
    doc=upload(ctx)
    with ctx['app'].state.engine.begin() as conn:
        IngestionJob.__table__.drop(conn);RetrievalCheck.__table__.drop(conn);DocumentUpdate.__table__.drop(conn)
        conn.execute(delete(SchemaVersion).where(SchemaVersion.version>=7))
    migrate(ctx['app'].state.engine,ctx['db']);migrate(ctx['app'].state.engine,ctx['db'])
    with ctx['db']() as db:
        assert db.get(KnowledgeDocument,doc['id']).content.startswith('Restricted')
        assert db.scalar(select(func.max(SchemaVersion.version)))==8
        assert db.scalar(select(func.count()).select_from(DocumentUpdate))==0
