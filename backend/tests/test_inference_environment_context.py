"""Internal propagation and shared accounting; every provider uses MockTransport."""
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from conftest import auth
from test_inference import setup
from nexus.db import User, WorkspaceAsset, InferenceCall, InferenceBudget, Audit
from nexus.inference import register_inference, period, settle
from nexus.runtime_context import bind_runtime_context


@pytest.fixture
def internal(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch)
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'));owner_id=owner.id
        stage=db.get(WorkspaceAsset,body['model_id'])
        prod=WorkspaceAsset(org_id=stage.org_id,env='production',kind='model',name='Production private model',status='validated',version=2,author_id=owner_id,config=stage.config)
        db.add(prod);db.flush();prod_id=prod.id
    selected={'environment':'staging','auth_count':0,'hook':None}
    def human(request,db,*args,**kwargs):
        selected['auth_count']+=1
        if selected['hook']:selected['hook'](db,selected['auth_count'])
        user=db.get(User,owner_id)
        bind_runtime_context(db,user.org_id,request.headers.get('X-Test-Context',selected['environment']))
        return user
    app=FastAPI();app.state.provider_transport=ctx['app'].state.provider_transport
    register_inference(app,ctx['db'],ctx['settings'],human)
    with TestClient(app) as client:
        yield {'client':client,'app':app,'selected':selected,'owner':owner_id,'body':body,'production_body':{**body,'model_id':prod_id},'sent':sent}


def infer(internal,environment='staging',key='internal-inference-0001'):
    return internal['client'].post('/v1/inference',headers={'Idempotency-Key':key,'X-Test-Context':environment},json=internal['production_body'] if environment=='production' else internal['body'])


def seed_call(db,owner,environment='staging',key='seed',status='pending',reserved=10):
    row=InferenceCall(org_id='northstar',env=environment,key_hash=hashlib.sha256(key.encode()).hexdigest(),request_hash='synthetic',author_id=owner,asset_id='synthetic',asset_version=1,period=period(),status=status,reserved=reserved,input_rate='1',output_rate='3',result={'answer':'private '+environment} if status=='completed' else {})
    db.add(row);db.flush();return row


def test_workspace_budget_is_shared_but_call_results_are_context_scoped(ctx,internal):
    ids={}
    for environment in ('staging','production'):
        response=infer(internal,environment,'shared-budget-'+environment)
        assert response.status_code==200,response.text
        ids[environment]=response.json()['id']
        assert response.json()['env']==environment
    for environment in ids:
        response=internal['client'].get('/v1/runtime',headers={'X-Test-Context':environment}).json()
        assert response['budget_scope']==response['admission_scope']=='workspace'
        assert response['spent_micro_usd']==48 and response['held_micro_usd']==0
        assert response['completed_calls']==1 and [r['id'] for r in response['calls']]==[ids[environment]]
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(InferenceBudget))==1
        assert db.scalar(select(InferenceBudget)).spent==48
        events=db.scalars(select(Audit).where(Audit.event=='inference.completed')).all()
        assert {a.env for a in events}=={'staging','production'}


def test_competing_environments_cannot_multiply_workspace_budget(ctx,internal):
    ctx['settings'].monthly_budget_usd='0.003'
    internal['app'].state.provider_transport=httpx.MockTransport(lambda req:httpx.Response(500))
    def request(environment):
        with TestClient(internal['app']) as client:
            body=internal['production_body'] if environment=='production' else internal['body']
            return client.post('/v1/inference',headers={'X-Test-Context':environment,'Idempotency-Key':'compete-'+environment+'-0001'},json=body).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(request,['staging','production']))
    assert sorted(statuses)==[200,429]
    with ctx['db']() as db:
        ledger=db.scalar(select(InferenceBudget));assert 0<ledger.held<=3000 and ledger.spent==0
        assert db.scalar(select(func.count()).select_from(InferenceCall))==1


@pytest.mark.parametrize('setting,code',[('inference_requests_per_minute','INFERENCE_RATE_LIMIT'),('inference_max_inflight','INFERENCE_CONCURRENCY_LIMIT')])
def test_admission_counts_other_environments_without_exposing_their_calls(ctx,internal,setting,code):
    setattr(ctx['settings'],setting,1)
    with ctx['db'].begin() as db:
        seed_call(db,internal['owner']);db.add(InferenceBudget(org_id='northstar',env='staging',period=period(),held=10,spent=0))
    response=infer(internal,'production')
    assert response.status_code==429,response.text
    assert response.json()['detail']['code']==code and not internal['sent']
    runtime=internal['client'].get('/v1/runtime',headers={'X-Test-Context':'production'}).json()
    assert runtime['calls']==[] and runtime['held_micro_usd']==10


def test_recovery_replay_and_reconciliation_do_not_cross_context(ctx,internal):
    response=infer(internal);assert response.status_code==200,response.text
    call=response.json()
    production=infer(internal,'production');assert production.status_code==200,production.text
    assert production.json()['id']!=call['id'] and len(internal['sent'])==2
    recover=internal['client'].post('/v1/inference/recover',headers={'X-Test-Context':'production'},json={'key':'internal-inference-0001'})
    assert recover.status_code==200 and recover.json()['id']==production.json()['id']
    reconcile=internal['client'].post('/v1/inference/'+call['id']+'/reconcile',headers={'X-Test-Context':'production'},json={'input_tokens':1,'output_tokens':1,'note':'Do not reconcile another environment record.'})
    assert reconcile.status_code==404


def test_history_cursor_and_model_search_are_environment_bound(ctx,internal):
    with ctx['db'].begin() as db:
        for environment in ('staging','production'):
            for index in range(3):
                row=seed_call(db,internal['owner'],environment,environment+str(index),'completed')
                row.asset_id=internal['production_body']['model_id'] if environment=='production' else internal['body']['model_id']
    client=internal['client']
    first=client.get('/v1/inference-calls',params={'limit':1}).json()
    cursor=first['next_cursor'];assert cursor
    assert client.get('/v1/inference-calls',headers={'X-Test-Context':'production'},params={'cursor':cursor}).status_code==400
    assert client.get('/v1/inference-calls',params={'q':'Production private model'}).json()['items']==[]
    assert len(client.get('/v1/inference-calls',headers={'X-Test-Context':'production'},params={'q':'Production private model'}).json()['items'])==3
    # Old signed cursors implied staging. Preserve that compatibility only there.
    key=hmac.new(ctx['settings'].secret.encode(),b'nexus-inference-pages-v1',hashlib.sha256).digest()
    claims=jwt.decode(cursor,key,algorithms=['HS256'],audience='nexus-inference-history');claims.pop('env')
    legacy=jwt.encode(claims,key,algorithm='HS256')
    assert client.get('/v1/inference-calls',params={'cursor':legacy}).status_code==200
    assert client.get('/v1/inference-calls',headers={'X-Test-Context':'production'},params={'cursor':legacy}).status_code==400


def test_late_context_change_preserves_accounting_but_withholds_answer(ctx,internal):
    def response(request):
        internal['selected']['environment']='production'
        return httpx.Response(200,json={'choices':[{'message':{'content':'must stay private'}}],'usage':{'prompt_tokens':12,'completion_tokens':4}})
    internal['app'].state.provider_transport=httpx.MockTransport(response)
    # Omit the fixed test header so authentication observes the changed context.
    result=internal['client'].post('/v1/inference',headers={'Idempotency-Key':'late-context-0001'},json=internal['body'])
    assert result.status_code==403,result.text
    assert 'must stay private' not in result.text
    with ctx['db']() as db:
        call=db.scalar(select(InferenceCall));ledger=db.scalar(select(InferenceBudget))
        assert call.env=='staging' and call.status=='completed' and ledger.spent==24 and ledger.held==0


@pytest.mark.parametrize('change',['context','model','guardrail'])
def test_admission_rechecks_context_and_current_model_and_rules(ctx,internal,change):
    def changed(db,count):
        if count!=2:return
        if change=='context':internal['selected']['environment']='production'
        elif change=='model':db.get(WorkspaceAsset,internal['body']['model_id']).status='draft'
        else:db.add(WorkspaceAsset(org_id='northstar',env='staging',kind='guardrail',name='New admission rule',author_id=internal['owner'],config={'blocked_terms':['Synthetic question'],'detect_email':False,'detect_override':False,'mode':'block'}))
    internal['selected']['hook']=changed
    result=internal['client'].post('/v1/inference',headers={'Idempotency-Key':'changed-admission-0001'},json=internal['body'])
    assert result.status_code=={'context':403,'model':409,'guardrail':422}[change],result.text
    assert not internal['sent']
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(InferenceCall))==0


def test_inconsistent_reservation_fails_without_partial_settlement(ctx,internal):
    with ctx['db'].begin() as db:
        row=seed_call(db,internal['owner'],'production','bad-ledger','unknown',100);call_id=row.id
        db.add(InferenceBudget(org_id='northstar',env='staging',period=period(),held=50,spent=0))
    response=internal['client'].post('/v1/inference/'+call_id+'/reconcile',headers={'X-Test-Context':'production'},json={'input_tokens':10,'output_tokens':1,'note':'Review inconsistent synthetic reservation ledger.'})
    assert response.status_code==409,response.text
    assert response.json()['detail']['code']=='BUDGET_LEDGER_INCONSISTENT'
    with ctx['db']() as db:
        assert db.get(InferenceCall,call_id).status=='unknown'
        ledger=db.scalar(select(InferenceBudget));assert ledger.held==50 and ledger.spent==0


def test_uncertain_completion_does_not_overwrite_reconciliation(ctx,internal):
    def reconciled(request):
        with ctx['db'].begin() as db:
            call=db.scalar(select(InferenceCall).where(InferenceCall.status=='pending'))
            settle(db,call,0,0,'reconciled',{'note':'Retain independent reconciliation'})
        return httpx.Response(500)
    internal['app'].state.provider_transport=httpx.MockTransport(reconciled)
    response=infer(internal)
    assert response.status_code==409,response.text
    with ctx['db']() as db:
        call=db.scalar(select(InferenceCall))
        assert call.status=='reconciled' and call.result=={'note':'Retain independent reconciliation'}
        assert db.scalar(select(InferenceBudget)).held==0


def test_public_inference_context_selection_remains_disabled(ctx):
    headers,_=auth(ctx);headers['X-Nexus-Environment']='production'
    for route in ('/v1/runtime','/v1/inference-calls'):
        assert ctx['client'].get(route,headers=headers).status_code==409


def test_workspace_aggregates_never_charge_another_organization(ctx,internal):
    with ctx['db'].begin() as db:
        db.add(InferenceBudget(org_id='other',env='production',period=period(),held=999,spent=888))
    response=infer(internal,'production');assert response.status_code==200,response.text
    with ctx['db']() as db:
        other=db.scalar(select(InferenceBudget).where(InferenceBudget.org_id=='other'))
        assert other.held==999 and other.spent==888
        own=db.scalar(select(InferenceBudget).where(InferenceBudget.org_id=='northstar'))
        assert own.held==0 and own.spent==24


def test_provider_completion_cannot_follow_relabelled_call(ctx,internal):
    def relabelled(request):
        with ctx['db'].begin() as db:
            db.scalar(select(InferenceCall)).env='production'
        return httpx.Response(200,json={'choices':[{'message':{'content':'withhold changed-context answer'}}],'usage':{'prompt_tokens':12,'completion_tokens':4}})
    internal['app'].state.provider_transport=httpx.MockTransport(relabelled)
    response=infer(internal)
    assert response.status_code==409,response.text
    assert response.json()['detail']['code']=='CALL_CONTEXT_CHANGED'
    assert 'withhold changed-context answer' not in response.text
    with ctx['db']() as db:
        call=db.scalar(select(InferenceCall));ledger=db.scalar(select(InferenceBudget))
        assert call.env=='production' and call.status=='pending' and call.result=={}
        assert ledger.held==call.reserved and ledger.spent==0
