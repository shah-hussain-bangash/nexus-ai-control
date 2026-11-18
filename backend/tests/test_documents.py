import base64
from sqlalchemy import select,func
from conftest import auth,assign_staging
from nexus.db import DocumentChunk,KnowledgeDocument,Audit

def payload(text='Restricted procurement needle: independent review above USD 5,000.',**changes):
    return {'title':'Procurement evidence','filename':'policy.txt','content_base64':base64.b64encode(text.encode()).decode(),'allowed_roles':[],**changes}

def upload(ctx,**changes):
    h,_=auth(ctx);h['Idempotency-Key']='document-upload-key-001';r=ctx['client'].post('/v1/documents',headers=h,json=payload(**changes));assert r.status_code==201,r.text;return r.json()

def test_ingestion_real_content_chunks_hashes_and_acl_filtered_search(ctx):
    doc=upload(ctx);result=ctx['client'].get('/v1/documents/search?q=procurement').json();assert result['provider_calls']==0 and result['items'][0]['document_id']==doc['id']
    assert ctx['client'].get('/v1/documents/'+doc['id']).json()['content'].startswith('Restricted')
    auth(ctx,'auditor');assert ctx['client'].get('/v1/documents').json()['items']==[]
    assert ctx['client'].get('/v1/documents/search?q=needle').json()['items']==[]
    assert ctx['client'].get('/v1/documents/'+doc['id']).status_code==404
    auth(ctx,org='other');assert ctx['client'].get('/v1/documents/'+doc['id']).status_code==404

def test_access_updates_take_effect_before_search_and_deletion_removes_chunks(ctx):
    doc=upload(ctx);h,_=auth(ctx)
    access={'expected_version':1,'allowed_roles':['auditor'],'allowed_users':[],'note':'Share evidence with audit reviewers.'}
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=h,json=access).json()['version']==2
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=h,json=access).status_code==409
    auth(ctx,'auditor');assert len(ctx['client'].get('/v1/documents/search?q=needle').json()['items'])==1
    h,_=auth(ctx);assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=h,json={**access,'expected_version':2,'allowed_roles':[]}).status_code==200
    auth(ctx,'auditor');assert ctx['client'].get('/v1/documents/search?q=needle').json()['items']==[]
    h,_=auth(ctx);deleted=ctx['client'].request('DELETE','/v1/documents/'+doc['id'],headers=h,json={'expected_version':3,'note':'Delete obsolete procurement evidence.'});assert deleted.status_code==200
    assert ctx['client'].get('/v1/documents/'+doc['id']).status_code==404
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(DocumentChunk))==0
        assert db.get(KnowledgeDocument,doc['id']).content==''
        assert not any('needle' in str(e.detail) for e in db.scalars(select(Audit)).all())

def test_upload_idempotency_encoding_formats_and_member_scope(ctx):
    doc=upload(ctx);h,_=auth(ctx);h['Idempotency-Key']='document-upload-key-001'
    assert ctx['client'].post('/v1/documents',headers=h,json=payload()).json()['id']==doc['id']
    assert ctx['client'].post('/v1/documents',headers=h,json=payload(title='Different request')).status_code==409
    h['Idempotency-Key']='document-upload-key-002'
    for change in [{'filename':'policy.pdf'},{'filename':'../policy.txt'},{'content_base64':'not-base64'},{'allowed_users':['other-user']},{'filename':'bad.json','content_base64':base64.b64encode(b'{oops').decode()}]:
        assert ctx['client'].post('/v1/documents',headers=h,json=payload(**change)).status_code==422
    assert ctx['client'].post('/v1/documents',json=payload()).status_code==403
    h,_=auth(ctx,'auditor');h['Idempotency-Key']='document-upload-key-003';assert ctx['client'].post('/v1/documents',headers=h,json=payload()).status_code==403

def test_arabic_utf8_and_size_bounds(ctx):
    doc=upload(ctx,text='الموافقة البشرية المستقلة مطلوبة لطلبات الشراء الكبيرة.',language='Arabic');assert doc['byte_count']>0
    assert ctx['client'].get('/v1/documents/search?q=الموافقة').json()['items'][0]['document_id']==doc['id']
    h,_=auth(ctx);h['Idempotency-Key']='document-upload-key-004'
    assert ctx['client'].post('/v1/documents',headers=h,json=payload(text='x'*32769)).status_code==413

def test_upload_recovery_never_ingests_again_and_rejects_another_author(ctx):
    doc=upload(ctx);h,_=auth(ctx)
    response=ctx['client'].post('/v1/documents/recover',headers=h,json={'key':'document-upload-key-001'})
    assert response.status_code==200 and response.json()['id']==doc['id']
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==1
    h,_=auth(ctx,'auditor');assert ctx['client'].post('/v1/documents/recover',headers=h,json={'key':'document-upload-key-001'}).status_code==404

def test_a_shared_reader_cannot_change_permissions_or_delete_a_document(ctx):
    from nexus.db import User
    with ctx['db'].begin() as db:
        db.add(User(id='same-org-engineer',org_id='northstar',email='engineer@test.invalid',name='Scoped engineer',role='engineer'))
        db.flush();assign_staging(db,db.get(User,'same-org-engineer'))
    doc=upload(ctx,allowed_roles=['engineer']);h,_=auth(ctx,'engineer')
    assert ctx['client'].get('/v1/documents/'+doc['id']).status_code==200
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=h,json={'expected_version':1,'allowed_roles':['auditor'],'note':'Try changing another author access.'}).status_code==403
    assert ctx['client'].request('DELETE','/v1/documents/'+doc['id'],headers=h,json={'expected_version':1,'note':'Try deleting another author document.'}).status_code==403
