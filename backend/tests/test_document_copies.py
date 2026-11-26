"""Disposable exact-text copy review: visibility precedes counts and pagination."""
import uuid
import pytest
from sqlalchemy import select, func, delete
from conftest import auth
from test_documents import payload
from nexus.db import KnowledgeDocument, Audit, DocumentChunk

TEXT='Disposable exact indexed text. الموافقة مطلوبة.'

def create(ctx, text=TEXT, roles=None):
    headers,_=auth(ctx);headers['Idempotency-Key']='copy-review-'+uuid.uuid4().hex
    result=ctx['client'].post('/v1/documents',headers=headers,json=payload(text=text, title='Copy '+uuid.uuid4().hex[:8],allowed_roles=roles or []))
    assert result.status_code==201,result.text
    return result.json()

def review(ctx, source, **query):
    return ctx['client'].get('/v1/documents/'+source['id']+'/copies',params={'expected_version':source['version'],**query})

def test_exact_text_across_metadata_and_read_only_receipt(ctx):
    source=create(ctx);copy=create(ctx);create(ctx,text=TEXT+' ')
    with ctx['db']() as db:
        before=(db.scalar(select(func.count()).select_from(Audit)),db.scalar(select(func.count()).select_from(DocumentChunk)))
    result=review(ctx,source);assert result.status_code==200,result.text
    value=result.json();assert result.headers['cache-control']=='no-store'
    assert value['visible_count']==1 and value['items'][0]['id']==copy['id']
    assert value['source']=={'id':source['id'],'version':1,'content_sha256':source['content_hash']}
    assert value['scope']['workspace_id']=='northstar' and value['scope']['environment']=='staging'
    assert set(value['items'][0])=={'id','title','filename','language','version','updated'}
    assert TEXT not in result.text and 'allowed_users' not in result.text
    with ctx['db']() as db:
        assert before==(db.scalar(select(func.count()).select_from(Audit)),db.scalar(select(func.count()).select_from(DocumentChunk)))
        assert db.get(KnowledgeDocument,source['id']).version==1
    assert ctx['client'].get(f"/v1/documents/{copy['id']}/citations/1/1").status_code==200

def test_only_visible_copies_are_counted_and_paged(ctx):
    source=create(ctx,roles=['auditor']);visible=[create(ctx,roles=['auditor']) for _ in range(3)]
    hidden=create(ctx);auth(ctx,'auditor')
    first=review(ctx,source,limit=2).json();second=review(ctx,source,offset=2,limit=2).json()
    assert first['visible_count']==second['visible_count']==3 and first['next_offset']==2 and second['next_offset'] is None
    assert {d['id'] for d in first['items']+second['items']}=={d['id'] for d in visible}
    assert hidden['id'] not in str(first)+str(second)
    assert review(ctx,hidden).status_code==404
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+visible[0]['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Revoke synthetic reviewer access.'}).status_code==200
    auth(ctx,'auditor');assert review(ctx,source).json()['visible_count']==2
    auth(ctx,org='other');assert review(ctx,source).status_code==404
    assert review(ctx,{'id':'missing','version':1}).status_code==404

def test_scope_status_and_hash_collision_are_excluded(ctx):
    source=create(ctx);copy=create(ctx);other_env=create(ctx);deleted=create(ctx);collision=create(ctx,text='Different private text')
    with ctx['db'].begin() as db:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id==other_env['id']))
        db.get(KnowledgeDocument,other_env['id']).env='production'
        db.get(KnowledgeDocument,deleted['id']).status='deleted'
        db.get(KnowledgeDocument,collision['id']).content_hash=source['content_hash']
    value=review(ctx,source).json();assert [d['id'] for d in value['items']]==[copy['id']]
    assert review(ctx,other_env).status_code==404

def test_stale_source_and_inconsistent_source_fail_closed(ctx):
    source=create(ctx);create(ctx)
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,source['id']).version=2
    result=review(ctx,source);assert result.status_code==409 and result.json()['error']['code']=='STALE_VERSION'
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,source['id']).content='Changed without hash update'
    result=review(ctx,source,expected_version=2);assert result.status_code==409 and result.json()['error']['code']=='DOCUMENT_INTEGRITY_FAILED'
    assert TEXT not in result.text

def test_replaced_and_deleted_candidates_disappear(ctx):
    source=create(ctx);copy=create(ctx);headers,_=auth(ctx)
    body=payload(text='New indexed text',expected_version=1,note='Replace synthetic copy content.');body.pop('allowed_roles')
    result=ctx['client'].put('/v1/documents/'+copy['id']+'/content',headers={**headers,'Idempotency-Key':'replace-copy-001'},json=body)
    assert result.status_code==200,result.text
    assert review(ctx,source).json()['visible_count']==0
    assert ctx['client'].request('DELETE','/v1/documents/'+source['id'],headers=headers,json={'expected_version':1,'note':'Remove synthetic source document.'}).status_code==200
    assert review(ctx,source).status_code==404

@pytest.mark.parametrize('query',[{'expected_version':0},{'limit':0},{'limit':51},{'offset':-1},{'offset':10001}])
def test_query_bounds(ctx,query):
    source=create(ctx);assert review(ctx,source,**query).status_code==422

def test_normal_auth_and_required_version(ctx):
    source=create(ctx);ctx['client'].cookies.clear()
    assert review(ctx,source).status_code==401
    auth(ctx);assert ctx['client'].get('/v1/documents/'+source['id']+'/copies').status_code==422
