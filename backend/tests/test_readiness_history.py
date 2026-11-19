import time
import pytest
from sqlalchemy import select, func
from conftest import auth,assign_staging
from test_inference import setup
from nexus.db import ReadinessEvidence, SchemaVersion, InferenceCall, User, Audit, migrate


def test_readiness_delivery_and_acceptance_separate(ctx):
    assert ctx['client'].get('/v1/production-readiness').status_code==401
    h,_=auth(ctx);report=ctx['client'].get('/v1/production-readiness').json()
    assert report['total_workstreams']==18 and report['implemented']==1 and report['partial']==16 and report['not_implemented']==1
    assert report['accepted']==0 and not report['production_ready']
    payload={'outcome':'passed','summary':'SQLite admission contention was tested in a disposable local environment.','reference':'https://example.invalid/evidence/run-1','expected_version':0}
    saved=ctx['client'].put('/v1/production-readiness/traffic_controls',headers=h,json=payload)
    assert saved.status_code==200 and saved.json()['version']==1
    assert ctx['client'].put('/v1/production-readiness/traffic_controls',headers=h,json=payload).status_code==409
    report=ctx['client'].get('/v1/production-readiness').json();assert report['accepted']==1 and not report['production_ready']
    changed=ctx['client'].put('/v1/production-readiness/traffic_controls',headers=h,json={**payload,'outcome':'failed','expected_version':1})
    assert changed.json()['version']==2
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Audit).where(Audit.event=='readiness.evidence_recorded'))==2


def test_missing_capability_cannot_be_attested_complete(ctx):
    h,_=auth(ctx)
    payload={'outcome':'passed','summary':'Claimed acceptance cannot implement missing software.','reference':'','expected_version':0}
    assert ctx['client'].put('/v1/production-readiness/workspace_lifecycle',headers=h,json=payload).status_code==422
    assert ctx['client'].put('/v1/production-readiness/missing',headers=h,json=payload).status_code==404


def test_evidence_roles_scope_csrf_and_reference(ctx):
    body={'outcome':'failed','summary':'Synthetic evidence for a private organization gate.','reference':'','expected_version':0}
    h,_=auth(ctx,'approver');assert ctx['client'].put('/v1/production-readiness/recovery',headers=h,json=body).status_code==403
    h,_=auth(ctx);assert ctx['client'].put('/v1/production-readiness/recovery',json=body).status_code==403
    for url in ['http://example.invalid/report','https://token@example.invalid','https://example.invalid/report?token=secret','https://example.invalid/report#token']:
        assert ctx['client'].put('/v1/production-readiness/recovery',headers=h,json={**body,'reference':url}).status_code==422
    assert ctx['client'].put('/v1/production-readiness/recovery',headers=h,json=body).status_code==200
    h,_=auth(ctx,org='other');report=ctx['client'].get('/v1/production-readiness').json()
    assert all(g['evidence'] is None for g in report['gates'])
    assert ctx['client'].put('/v1/production-readiness/recovery',headers=h,json=body).status_code==200
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(ReadinessEvidence))==2


def records(ctx,count=25):
    h,owner=auth(ctx)
    with ctx['db'].begin() as db:
        for i in range(count):db.add(InferenceCall(id='page-'+str(i).zfill(3),org_id='northstar',key_hash='key-'+str(i),request_hash='payload',author_id=owner,asset_id='model-ref',asset_version=1,period='2026-11',status='completed' if i%2 else 'unknown',reserved=1,input_rate='1',output_rate='2',created=1000+i//2,result={'answer':'Synthetic saved response'}))
    return h


def test_inference_keyset_ties_search_and_query_binding(ctx):
    records(ctx);cursor='';ids=[]
    while True:
        page=ctx['client'].get('/v1/inference-calls',params={'limit':4,'cursor':cursor}).json()
        ids += [r['id'] for r in page['items']]
        if not page['has_more']:break
        cursor=page['next_cursor']
    assert len(ids)==25 and len(set(ids))==25
    first=ctx['client'].get('/v1/inference-calls',params={'limit':1}).json()['next_cursor']
    for params in [{'q':'different'},{'status':'unknown'}]:assert ctx['client'].get('/v1/inference-calls',params={'cursor':first,**params}).status_code==400
    assert ctx['client'].get('/v1/inference-calls',params={'cursor':first+'bad'}).status_code==400
    assert len(ctx['client'].get('/v1/inference-calls',params={'q':'page-024'}).json()['items'])==1
    auth(ctx,org='other');assert ctx['client'].get('/v1/inference-calls',params={'cursor':first}).status_code==400
    assert ctx['client'].get('/v1/inference-calls').json()['items']==[]


def test_history_cursor_expiry_limits_and_anonymous(ctx,monkeypatch):
    assert ctx['client'].get('/v1/inference-calls').status_code==401
    records(ctx,3)
    import nexus.inference_history as history
    monkeypatch.setattr(history.time,'time',lambda:1)
    cursor=ctx['client'].get('/v1/inference-calls',params={'limit':1}).json()['next_cursor']
    assert ctx['client'].get('/v1/inference-calls',params={'cursor':cursor}).status_code==400
    for params in [{'limit':0},{'limit':26},{'q':'x'*121},{'status':'invalid'}]:assert ctx['client'].get('/v1/inference-calls',params=params).status_code==422


def test_recover_only_own_key_without_provider_replay(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch)
    result=ctx['client'].post('/v1/inference',headers=h,json=b).json()
    saved=ctx['client'].post('/v1/inference/recover',headers=h,json={'key':h['Idempotency-Key']})
    assert saved.status_code==200 and saved.json()['id']==result['id'] and len(sent)==1
    assert ctx['client'].post('/v1/inference/recover',json={'key':h['Idempotency-Key']}).status_code==403
    other,_=auth(ctx,org='other');assert ctx['client'].post('/v1/inference/recover',headers=other,json={'key':h['Idempotency-Key']}).status_code==404
    with ctx['db'].begin() as db:
        user=User(org_id='northstar',email='second@synthetic.invalid',name='Second owner',role='owner');db.add(user);db.flush()
        assign_staging(db,user)
        from nexus.security import issue_session
        token,csrf=issue_session(db,user,ctx['settings'])
    ctx['client'].cookies.set('nexus_session',token)
    assert ctx['client'].post('/v1/inference/recover',headers={'X-CSRF-Token':csrf},json={'key':h['Idempotency-Key']}).status_code==404


def test_admitted_request_rate_and_idempotent_replay(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch);ctx['settings'].inference_requests_per_minute=1
    assert ctx['client'].post('/v1/inference',headers=h,json=b).status_code==200
    assert ctx['client'].post('/v1/inference',headers=h,json=b).status_code==200
    h['Idempotency-Key']='rate-limited-intent-0002'
    response=ctx['client'].post('/v1/inference',headers=h,json=b)
    assert response.status_code==429 and response.json()['error']['code']=='INFERENCE_RATE_LIMIT' and len(sent)==1
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(InferenceCall))==1


def test_pending_concurrency_admission_and_stale_window(ctx,monkeypatch):
    import httpx
    h,b,sent=setup(ctx,monkeypatch,lambda req:httpx.Response(500));ctx['settings'].inference_max_inflight=1
    record=ctx['client'].post('/v1/inference',headers=h,json=b).json()
    with ctx['db'].begin() as db:db.get(InferenceCall,record['id']).status='pending'
    h['Idempotency-Key']='concurrency-intent-0002'
    response=ctx['client'].post('/v1/inference',headers=h,json=b)
    assert response.status_code==429 and response.json()['error']['code']=='INFERENCE_CONCURRENCY_LIMIT' and len(sent)==1
    with ctx['db'].begin() as db:db.get(InferenceCall,record['id']).created=time.time()-400
    assert ctx['client'].post('/v1/inference',headers=h,json=b).status_code==200 and len(sent)==2


def test_schema_four_upgrade_preserves_accounts(ctx):
    with ctx['app'].state.engine.begin() as connection:
        ReadinessEvidence.__table__.drop(connection);connection.execute(SchemaVersion.__table__.delete().where(SchemaVersion.version>=5))
    migrate(ctx['app'].state.engine,ctx['db'])
    with ctx['db']() as db:assert db.get(SchemaVersion,5) and db.scalar(select(User))


def test_concurrent_admission_never_dispatches_second_inflight(ctx,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from fastapi.testclient import TestClient
    import httpx
    entered=Event();release=Event()
    def provider(req):
        entered.set();assert release.wait(timeout=4)
        return httpx.Response(200,json={'id':'bounded-test','choices':[{'message':{'content':'Synthetic result'},'finish_reason':'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':1}})
    h,b,sent=setup(ctx,monkeypatch,provider);ctx['settings'].inference_max_inflight=1
    cookie=ctx['client'].cookies.get('nexus_session')
    def run(key):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post('/v1/inference',headers={**h,'Idempotency-Key':key},json=b)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(run,'parallel-active-0001')
        try:
            assert entered.wait(timeout=3)
            second=pool.submit(run,'parallel-active-0002').result(timeout=3)
            assert second.status_code==429 and second.json()['error']['code']=='INFERENCE_CONCURRENCY_LIMIT'
        finally:release.set()
        assert first.result(timeout=3).json()['status']=='completed'
    assert len(sent)==1
