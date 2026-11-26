"""Normal-API cross-feature checks for the combined review candidate only."""
from conftest import auth
from test_lexical_source_diversity import upload
from nexus.db import User
from nexus.environments import assign_staging


def test_copy_review_keyword_diversity_and_saved_quality_share_current_acl(ctx):
    with ctx['db'].begin() as db:
        user=User(id='synthetic-integration-reader',org_id='northstar',email='integration@test.invalid',name='Integration evaluator',role='engineer',password_hash='not-a-login-hash')
        db.add(user);db.flush();assign_staging(db,user)
    first=upload(ctx,'needle shared identical indexed text',['engineer'])
    second=upload(ctx,'needle shared identical indexed text',['engineer'])
    hidden=upload(ctx,'needle shared identical indexed text')
    headers,_=auth(ctx,'engineer');client=ctx['client']
    copies=client.get(f"/v1/documents/{first['id']}/copies?expected_version=1").json()
    assert copies['visible_count']==1 and copies['items'][0]['id']==second['id']
    search=client.get('/v1/documents/search?q=needle&top_k=10&one_per_document=true').json()
    assert {r['document_id'] for r in search['items']}=={first['id'],second['id']}
    assert hidden['id'] not in str(copies)+str(search)
    saved=client.post('/v1/retrieval-checks',headers={**headers,'Idempotency-Key':'combined-quality-check-001'},json={'name':'Combined feature check','top_k':10,'one_per_document':True,'cases':[{'query':'needle','expected_document_ids':[first['id'],second['id']]}]})
    assert saved.status_code==201,saved.text
    evidence=saved.json();assert evidence['passed_cases']==1 and evidence['result']['one_per_document'] is True
    owner_headers,_=auth(ctx)
    assert client.put('/v1/documents/'+second['id']+'/access',headers=owner_headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Revoke synthetic integration reader.'}).status_code==200
    auth(ctx,'engineer')
    assert client.get(f"/v1/documents/{first['id']}/copies?expected_version=1").json()['visible_count']==0
    assert [r['document_id'] for r in client.get('/v1/documents/search?q=needle&one_per_document=true').json()['items']]==[first['id']]
    result=client.get('/v1/retrieval-checks/'+evidence['id'])
    assert result.status_code==409 and result.json()['error']['code']=='EVIDENCE_ACCESS_CHANGED'
