"""Real lexical ranking: group documents after scoring, before top-k."""
import uuid
import pytest
from sqlalchemy import select
from conftest import auth
from test_documents import payload
from nexus.db import KnowledgeDocument, DocumentChunk
from nexus.documents import search_documents
from nexus.runtime_context import bind_runtime_context

def upload(ctx,text,roles=None,org='northstar'):
    headers,_=auth(ctx,org=org);headers['Idempotency-Key']='lexical-diversity-'+uuid.uuid4().hex
    result=ctx['client'].post('/v1/documents',headers=headers,json=payload(text=text,allowed_roles=roles or []))
    assert result.status_code==201,result.text
    return result.json()

def search(ctx,**params):
    return ctx['client'].get('/v1/documents/search',params={'q':'needle','top_k':2,**params})

def test_document_grouping_precedes_top_k_without_changing_scores(ctx):
    dominant=upload(ctx,'needle '*650)
    secondary=upload(ctx,'needle '+'unrelated '*70)
    legacy=search(ctx).json();explicit=search(ctx,one_per_document='false').json()
    assert legacy==explicit and legacy['one_per_document'] is False
    assert [r['document_id'] for r in legacy['items']]==[dominant['id']]*2
    result=search(ctx,one_per_document='true').json()
    assert result['one_per_document'] is True and result['provider_calls']==0
    assert [r['document_id'] for r in result['items']]==[dominant['id'],secondary['id']]
    assert result['items'][0]==legacy['items'][0]
    assert search(ctx,one_per_document='true',top_k=1).json()['items']==result['items'][:1]
    for row in result['items']:
        assert ctx['client'].get(f"/v1/documents/{row['document_id']}/citations/{row['document_version']}/{row['chunk']}").status_code==200

def test_grouping_keeps_distinct_records_even_when_text_matches(ctx):
    first=upload(ctx,'needle identical text')
    second=upload(ctx,'needle identical text')
    result=search(ctx,one_per_document='true').json()
    assert {r['document_id'] for r in result['items']}=={first['id'],second['id']}
    assert len(search(ctx,q='absentword',one_per_document='true').json()['items'])==0

def test_acl_before_ranking_revocation_and_other_tenant(ctx):
    visible=upload(ctx,'needle shared text',['auditor'])
    hidden=upload(ctx,'needle '*600)
    upload(ctx,'needle '*600,org='other')
    auth(ctx,'auditor');result=search(ctx,one_per_document='true').json()
    assert [r['document_id'] for r in result['items']]==[visible['id']]
    assert hidden['id'] not in str(result)
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+visible['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Revoke synthetic search reader.'}).status_code==200
    auth(ctx,'auditor');assert search(ctx,one_per_document='true').json()['items']==[]

def test_internal_scope_and_stale_chunks_still_filter_before_grouping(ctx):
    doc=upload(ctx,'needle current source')
    with ctx['db'].begin() as db:
        db.add(DocumentChunk(org_id='northstar',env='staging',document_id=doc['id'],document_version=0,position=99,text='obsoleteuniquemarker',content_hash='obsolete'))
        from nexus.db import User
        user=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
        bind_runtime_context(db,user.org_id,'production')
        assert search_documents(db,user,'needle',10,one_per_document=True)==[]
    assert search(ctx,q='obsoleteuniquemarker',one_per_document='true').json()['items']==[]

@pytest.mark.parametrize('params',[{'one_per_document':'invalid'},{'top_k':0},{'top_k':11}])
def test_search_query_validation(ctx,params):
    auth(ctx);assert search(ctx,**params).status_code==422
