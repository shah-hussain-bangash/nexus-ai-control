import time
from sqlalchemy import select, func
from conftest import auth,assign_staging
from nexus.db import Audit, SessionRecord, OIDCTransaction, Export, User
from nexus.operations import housekeeping


def add_events(ctx, count=8, org='northstar', prefix='page'):
    with ctx['db'].begin() as db:
        for i in range(count):
            db.add(Audit(id=f'{prefix}-{i:03}', org_id=org, event='action.verified', actor='worker',
                detail={'keyword': 'retained needle' if i == 0 else 'ordinary'}, created=1000 + i // 2))


def test_keyset_pages_include_ties_without_duplicates(ctx):
    add_events(ctx); auth(ctx)
    ids=[]; cursor=''
    while True:
        r=ctx['client'].get('/v1/audit-page',params={'limit':3,'cursor':cursor});assert r.status_code==200
        page=r.json();ids += [x['id'] for x in page['items']]
        if not page['has_more']:break
        cursor=page['next_cursor']
    assert len(ids)==8 and len(set(ids))==8
    assert ids[:2]==['page-007','page-006']


def test_search_happens_before_limit_and_searches_details(ctx):
    add_events(ctx,20);auth(ctx)
    r=ctx['client'].get('/v1/audit-page',params={'q':'retained needle','limit':1})
    assert [x['id'] for x in r.json()['items']]==['page-000']


def test_cursor_is_tenant_query_bound_and_tamper_resistant(ctx):
    add_events(ctx);auth(ctx)
    cursor=ctx['client'].get('/v1/audit-page',params={'limit':1}).json()['next_cursor']
    assert ctx['client'].get('/v1/audit-page',params={'cursor':cursor,'q':'different'}).status_code==400
    assert ctx['client'].get('/v1/audit-page',params={'cursor':cursor+'bad'}).status_code==400
    auth(ctx,org='other')
    assert ctx['client'].get('/v1/audit-page',params={'cursor':cursor}).status_code==400
    assert ctx['client'].get('/v1/audit-page').json()['items']==[]


def test_pagination_validation_and_anonymous_access(ctx):
    assert ctx['client'].get('/v1/audit-page').status_code==401
    auth(ctx)
    for params in [{'limit':0},{'limit':201},{'q':'x'*121},{'cursor':'x'*2049}]:
        assert ctx['client'].get('/v1/audit-page',params=params).status_code==422


def test_pagination_cursor_expires(ctx,monkeypatch):
    import nexus.operations as op
    add_events(ctx);auth(ctx)
    monkeypatch.setattr(op.time,'time',lambda:1)
    cursor=ctx['client'].get('/v1/audit-page',params={'limit':1}).json()['next_cursor']
    assert ctx['client'].get('/v1/audit-page',params={'cursor':cursor}).status_code==400


def test_housekeeping_dry_run_apply_and_preserves_evidence(ctx):
    stamp=time.time()
    with ctx['db'].begin() as db:
        db.add_all([SessionRecord(id='expired',user_id='unused',csrf='not-a-secret',expires=stamp-10),SessionRecord(id='live',user_id='unused',csrf='not-a-secret',expires=stamp+3600)])
        for id,expires in [('expired',stamp-7200),('grace',stamp-10),('live',stamp+3600)]:
            db.add(OIDCTransaction(id=id,binding_hash='synthetic',nonce='synthetic',verifier_ciphertext='synthetic',expires=expires))
        for id,expires in [('old-export',stamp-10),('live-export',stamp+3600)]:db.add(Export(id=id,org_id='northstar',owner_id='unused',records=[],expires=expires))
        db.add(Audit(id='evidence',org_id='northstar',event='keep',actor='system',created=1))
    preview=housekeeping(ctx['db'],cutoff=stamp)
    assert preview['expired_records']=={'sessions':1,'oidc_transactions':1,'exports':1}
    with ctx['db']() as db:assert db.get(SessionRecord,'expired')
    result=housekeeping(ctx['db'],apply=True,cutoff=stamp)
    assert result['expired_records']==preview['expired_records']
    with ctx['db']() as db:
        assert db.get(SessionRecord,'expired') is None and db.get(SessionRecord,'live')
        assert db.get(OIDCTransaction,'grace') and db.get(OIDCTransaction,'live')
        assert db.get(Export,'live-export') and db.get(Audit,'evidence')
    assert all(x==0 for x in housekeeping(ctx['db'],apply=True,cutoff=stamp)['expired_records'].values())


def test_owner_revokes_member_and_existing_session(ctx):
    _, target=auth(ctx,'approver');old=ctx['client'].cookies.get('nexus_session')
    headers,owner=auth(ctx)
    r=ctx['client'].post('/v1/members/'+target+'/revoke',json={'reason':'Synthetic offboarding test'},headers=headers)
    assert r.status_code==200 and r.json()['sessions_revoked']
    with ctx['db']() as db:
        assert not db.get(User,target).active
        assert db.scalar(select(Audit).where(Audit.event=='member.revoked')).detail['member_id']==target
    ctx['client'].cookies.set('nexus_session',old)
    assert ctx['client'].get('/v1/me').status_code==401
    r=ctx['client'].post('/auth/local/login',json={'email':'reviewer@nexus.local','password':'Test-Only-Password-123!'})
    assert r.status_code==401


def test_member_revocation_protects_scope_self_role_and_csrf(ctx):
    headers,owner=auth(ctx)
    assert ctx['client'].post('/v1/members/'+owner+'/revoke',headers=headers,json={'reason':'Self revocation test'}).status_code==409
    assert ctx['client'].post('/v1/members/other-user/revoke',headers=headers,json={'reason':'Cross tenant test'}).status_code==404
    _,target=auth(ctx,'approver');headers,_=auth(ctx,'auditor')
    assert ctx['client'].post('/v1/members/'+target+'/revoke',headers=headers,json={'reason':'Forbidden test'}).status_code==403
    with ctx['db'].begin() as db:
        db.add(User(id='security-member',org_id='northstar',email='security@test.invalid',name='Security',role='security'))
        db.add(User(id='second-owner',org_id='northstar',email='owner2@test.invalid',name='Second owner',role='owner'))
        db.flush()
        for user_id in ('security-member','second-owner'):assign_staging(db,db.get(User,user_id))
    security_headers,_=auth(ctx,'security')
    assert ctx['client'].post('/v1/members/'+target+'/revoke',headers=security_headers,json={'reason':'Role boundary test'}).status_code==403
    headers,_=auth(ctx)
    assert ctx['client'].post('/v1/members/second-owner/revoke',headers=headers,json={'reason':'Owner protection test'}).status_code==409
    assert ctx['client'].post('/v1/members/'+target+'/revoke',json={'reason':'No csrf token'}).status_code==403


def test_operations_does_not_leak_other_tenant_counts(ctx):
    with ctx['db'].begin() as db:db.add(Export(org_id='other',owner_id='other-user',expires=1,records=[]))
    auth(ctx)
    r=ctx['client'].get('/v1/operations');assert r.status_code==200
    assert r.json()['expired_exports']==0
    assert any(x['name']=='Business connector' and x['state']=='local' for x in r.json()['checks'])
