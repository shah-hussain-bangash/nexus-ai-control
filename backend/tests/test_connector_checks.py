from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from conftest import auth
from test_local_switching import current,headers,prepare,switch
from nexus.db import Action,Agent,WorkbenchRun,Audit
from nexus.worker import run_once
from nexus.business_connector import HTTPBusiness

URL='/v1/connector-checks';KEY='governed-supplier-check-001'

def config(ctx):
    result=ctx['client'].get(URL+'/config',headers=headers(current(ctx)))
    assert result.status_code==200,result.text
    return result.json()

def setup(ctx):
    auth(ctx);settings=config(ctx);route=settings['choices'][0]
    return {'agent_id':route['agent_id'],'tool_id':route['tool_id'],'expected_grant_id':route['grant_id'],'expected_agent_generation':route['agent_generation'],
        'expected_tool_version':route['tool_version'],'expected_destination':settings['connector']['destination'],'supplier_id':'SUP-DEMO-104',
        'note':'Review the configured connector and supplier route.','reviewed':True}

def submit(ctx,body,key=KEY):return ctx['client'].post(URL,headers={**headers(current(ctx)),'Idempotency-Key':key},json=body)
def resolve(ctx,command,key=KEY):return ctx['client'].post(URL+'/'+command,headers=headers(current(ctx)),json={'key':key})
def history(ctx):return ctx['client'].get(URL,headers=headers(current(ctx))).json()

def test_supplier_check_uses_governed_outbox_and_worker_with_no_intake_network(ctx,monkeypatch):
    body=setup(ctx);calls=[];original=ctx['connector'].invoke
    def invoke(*args,**kwargs):calls.append(args);return original(*args,**kwargs)
    monkeypatch.setattr(ctx['connector'],'invoke',invoke)
    response=submit(ctx,body);assert response.status_code==202,response.text
    value=response.json();assert value['status']=='submitted' and value['check']['status']=='queued' and not calls
    assert history(ctx)['open_check']['id']==value['check']['id']
    assert resolve(ctx,'recover').json()['check']['id']==value['check']['id'] and not calls
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    assert len(calls)==1
    result=history(ctx);assert result['open_check'] is None
    assert result['items'][0]['verified'] and result['items'][0]['connector_mode']=='synthetic'
    with ctx['db']() as db:
        row=db.get(Action,value['check']['id'])
        assert row.envelope['action']=='supplier:read' and row.envelope['resource']=='suppliers' and row.principal.startswith('connector-check:')
        assert set(row.envelope['arguments'])=={'supplier_id'}
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.event=='connector.check_submitted'))==1
    assert not ctx['client'].get('/v1/workbench',headers=headers(current(ctx))).json()['runs']

def test_replay_and_recovery_never_admit_a_second_action_or_cancel_admitted_work(ctx):
    body=setup(ctx);first=submit(ctx,body);assert first.status_code==202
    assert submit(ctx,body).json()==first.json()
    assert submit(ctx,{**body,'supplier_id':'ANOTHER'}).status_code==409
    assert resolve(ctx,'cancel-pending').json()==first.json()
    assert resolve(ctx,'recover').json()==first.json()
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==1

def test_pending_cancellation_fences_late_check_submission(ctx):
    body=setup(ctx)
    assert resolve(ctx,'recover').status_code==404
    cancelled=resolve(ctx,'cancel-pending');assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
    assert resolve(ctx,'recover').json()==cancelled.json()
    assert submit(ctx,body).json()['error']['code']=='CHECK_CANCELLED'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0

@pytest.mark.parametrize('change',[{'expected_destination':'http-business-v1:'+'a'*64},{'expected_agent_generation':999},{'expected_grant_id':'missing'}])
def test_admission_pins_reviewed_connector_and_granted_route(ctx,change):
    body=setup(ctx);response=submit(ctx,{**body,**change});assert response.status_code==409,response.text
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0

@pytest.mark.parametrize('changes',[{'action':'purchase:create'},{'amount':'100.00'},{'business_base_url':'https://untrusted.invalid'},{'reviewed':False},{'supplier_id':'bad/../../supplier'}])
def test_check_contract_accepts_only_reviewed_fixed_supplier_reads(ctx,changes):
    body=setup(ctx);assert submit(ctx,{**body,**changes}).status_code==422

def test_unknown_or_unfinished_check_blocks_new_intents_until_resolved(ctx):
    body=setup(ctx);first=submit(ctx,body);assert first.status_code==202
    for status in ('queued','executing','awaiting_approval','outcome_unknown','future_status'):
        with ctx['db'].begin() as db:db.get(Action,first.json()['check']['id']).status=status
        response=submit(ctx,body,key='another-check-intent-001')
        assert response.status_code==409 and response.json()['error']['code']=='CHECK_IN_PROGRESS'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==1

def test_worker_rechecks_authorization_before_supplier_dispatch(ctx,monkeypatch):
    body=setup(ctx);first=submit(ctx,body)
    with ctx['db'].begin() as db:db.get(Agent,body['agent_id']).status='suspended'
    def forbidden(*args):raise AssertionError('Revoked route must not dispatch')
    monkeypatch.setattr(ctx['connector'],'invoke',forbidden)
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    with ctx['db']() as db:assert db.get(Action,first.json()['check']['id']).status=='blocked'

def test_owner_csrf_mode_actor_workspace_and_environment_boundaries(ctx):
    body=setup(ctx);first=submit(ctx,body);assert first.status_code==202
    assert ctx['client'].post(URL,headers={'Idempotency-Key':'no-csrf-check-001'},json=body).status_code==403
    assert ctx['client'].post(URL,headers=headers(current(ctx)),json=body).status_code==422
    assert ctx['client'].post(URL+'/cancel-pending',json={'key':KEY}).status_code==403
    target=prepare(ctx);switch(ctx,target)
    assert resolve(ctx,'recover').status_code==404 and not history(ctx)['items'] and not config(ctx)['choices']
    assert resolve(ctx,'cancel-pending').json()['status']=='cancelled'
    auth(ctx,'auditor');assert ctx['client'].get(URL).status_code==403
    auth(ctx,org='other');assert not history(ctx)['items'] and resolve(ctx,'recover').status_code==404
    auth(ctx);ctx['settings'].mode='pilot';assert ctx['client'].get(URL).status_code==403 and submit(ctx,body).status_code==403

def test_http_supplier_check_stays_uncertain_without_retry_until_authoritative_reconciliation(ctx,monkeypatch):
    monkeypatch.setenv('NEXUS_BUSINESS_API_KEY','synthetic-test-only-'+'x'*32)
    settings=ctx['settings'];settings.business_connector='http';settings.business_base_url='https://sandbox.customer.invalid/api/v1';settings.business_host='sandbox.customer.invalid';settings.business_tenant='test-tenant'
    calls=[]
    def handler(request):
        calls.append(request)
        if '/suppliers/' in request.url.path:raise httpx.ReadTimeout('Synthetic uncertainty',request=request)
        return httpx.Response(200,json={'operation_id':request.headers['Idempotency-Key'],'organization_id':'northstar','tenant_id':'test-tenant','result':{'external_ref':'SANDBOX-READ-1','state':'found','supplier_id':'SUP-DEMO-104'}})
    adapter=HTTPBusiness(settings,transport=httpx.MockTransport(handler));ctx['app'].state.connector=adapter
    body=setup(ctx);response=submit(ctx,body);assert response.status_code==202,response.text
    action=response.json()['check']['id'];assert not calls
    run_once(ctx['db'],settings,adapter);assert len(calls)==1 and calls[0].method=='GET'
    assert history(ctx)['items'][0]['status']=='outcome_unknown'
    assert submit(ctx,body,key='do-not-replay-check-001').status_code==409
    assert not run_once(ctx['db'],settings,adapter) and len(calls)==1
    reconciled=ctx['client'].post('/v1/actions/'+action+'/reconcile',headers=headers(current(ctx)))
    assert reconciled.status_code==200,reconciled.text
    assert len(calls)==2 and calls[1].method=='GET'
    assert history(ctx)['items'][0]['verified'] and history(ctx)['items'][0]['connector_mode']=='http'
    assert submit(ctx,body).json()['check']['id']==action and len(calls)==2
    assert 'synthetic-test-only' not in str(config(ctx)) and 'synthetic-test-only' not in str(history(ctx))

def test_racing_admission_and_cancellation_have_one_terminal_receipt(ctx):
    body=setup(ctx);me=current(ctx);cookie=ctx['client'].cookies.get('nexus_session')
    def execute(command):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post(URL+('/cancel-pending' if command=='cancel' else ''),headers={**headers(me),'Idempotency-Key':KEY},json={'key':KEY} if command=='cancel' else body)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,['submit','cancel']))
    submitted,cancelled=results;assert cancelled.status_code==200
    with ctx['db']() as db:
        count=db.scalar(select(func.count()).select_from(Action))
        assert (submitted.status_code,cancelled.json()['status'],count) in ((202,'submitted',1),(409,'cancelled',0))

@pytest.mark.parametrize('decision',['deny','require_approval'])
def test_configured_policy_denial_or_approval_remains_authoritative(ctx,monkeypatch,decision):
    from conftest import approve
    monkeypatch.setattr('nexus.service.evaluate',lambda *args:{'decision':decision,'reason':'SYNTHETIC_POLICY_RESULT'})
    body=setup(ctx);result=submit(ctx,body);assert result.status_code==202,result.text
    assert result.json()['check']['status']==('denied' if decision=='deny' else 'awaiting_approval')
    assert not run_once(ctx['db'],ctx['settings'],ctx['connector'])
    if decision=='require_approval':
        assert approve(ctx,role='owner').status_code==403
        assert approve(ctx).status_code==200
        assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
        auth(ctx);assert history(ctx)['items'][0]['verified']

def test_receipt_storage_failure_rolls_back_the_queued_action(ctx,monkeypatch):
    from sqlalchemy.orm import Session
    body=setup(ctx);original=Session.flush
    def flush(db,*args,**kwargs):
        if any(isinstance(row,WorkbenchRun) and row.kind=='connector_check_intake' for row in db.new):raise RuntimeError('Synthetic receipt storage failure')
        return original(db,*args,**kwargs)
    monkeypatch.setattr(Session,'flush',flush)
    with pytest.raises(RuntimeError,match='Synthetic receipt storage failure'):submit(ctx,body)
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0

def test_missing_http_credential_and_receipt_capacity_do_not_admit_actions(ctx,monkeypatch):
    body=setup(ctx);owner=current(ctx)['user']['id']
    with ctx['db'].begin() as db:db.add_all([WorkbenchRun(org_id='northstar',env='staging',kind='connector_check_intake',status='cancelled',duration_ms=0,author_id=owner,result={'status':'cancelled'}) for _ in range(1000)])
    assert submit(ctx,body).status_code==429
    settings=ctx['settings'];settings.business_connector='http';settings.business_base_url='https://sandbox.customer.invalid/api/v1';settings.business_host='sandbox.customer.invalid';settings.business_tenant='test-tenant'
    monkeypatch.delenv(settings.business_token_env,raising=False)
    body['expected_destination']=config(ctx)['connector']['destination']
    response=submit(ctx,body);assert response.status_code==503 and response.json()['error']['code']=='CONNECTOR_UNAVAILABLE'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0
