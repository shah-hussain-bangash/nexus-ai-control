"""Model admission containment over disposable accounting and mock transports."""
import httpx,pytest
from sqlalchemy import select,func
from conftest import auth
from test_inference import setup
from test_model_spending import policy as spend_policy,config as spend_config
from nexus.db import InferenceCall,InferenceBudget,WorkbenchRun,WorkspaceAsset

URL='/v1/model-uncertainty-controls'
NOTE='Reviewed synthetic unresolved model outcomes.'

def config(body,limit=1,version=0):
    return {'expected_version':version,'rules':[{'model_id':body['model_id'],'expected_model_version':2,'unknown_limit':limit}],'note':NOTE}

def policy(ctx,value,key='uncertainty-policy-intent-0001',role='owner'):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].put(URL,headers=headers,json=value)

def infer(ctx,body,key='uncertainty-call-intent-0001'):
    headers,_=auth(ctx);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/inference',headers=headers,json=body)

def seed_call(ctx,body,key='prior-unknown',org='northstar',env='staging',status='unknown',period='2024-01',model=None):
    with ctx['db'].begin() as db:
        db.add(InferenceCall(org_id=org,env=env,author_id='synthetic',asset_id=model or body['model_id'],asset_version=1,period=period,key_hash=key,request_hash='synthetic',status=status,reserved=0,input_rate='0',output_rate='0',result={'answer':'PRIVATE-ANSWER-NOT-EXPORTED'}))


def test_default_has_no_added_guard_and_configured_receipt_preserves_admission_context(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);auth(ctx)
    assert ctx['client'].get(URL).json()['version']==0
    assert infer(ctx,body).json()['status']=='completed'
    saved=policy(ctx,config(body));assert saved.status_code==201,saved.text
    result=infer(ctx,body,key='uncertainty-call-intent-0002').json()
    assert result['status']=='completed' and result['result']['uncertainty_control']['policy_id']==saved.json()['id']
    assert result['result']['uncertainty_control']['unknown_before_admission']==0 and len(sent)==2
    assert saved.json()['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


def test_unknown_outcome_blocks_next_admission_without_new_reservation_or_retry(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch,handler=lambda _:httpx.Response(503,json={}))
    saved=policy(ctx,config(body)).json();first=infer(ctx,body).json()
    assert first['status']=='unknown' and first['result']['uncertainty_control']['policy_id']==saved['id']
    with ctx['db']() as db:held=db.scalar(select(InferenceBudget.held))
    blocked=infer(ctx,body,key='uncertainty-call-intent-0002')
    assert blocked.status_code==429 and blocked.json()['error']['code']=='MODEL_UNCERTAINTY_LIMIT' and len(sent)==1
    assert infer(ctx,body).json()['id']==first['id'] and len(sent)==1
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(InferenceCall))==1 and db.scalar(select(InferenceBudget.held))==held
    overview=ctx['client'].get(URL).json();assert overview['models'][0]['unknown_calls']==1 and overview['models'][0]['blocked']
    assert 'answer' not in str(overview) and 'credential_ref' not in str(overview)


def test_owner_reconciliation_reopens_admission_and_preserves_spend_and_uncertainty_context(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch,handler=lambda _:httpx.Response(503,json={}))
    spend_policy(ctx,spend_config(body,limit=10000));policy(ctx,config(body))
    first=infer(ctx,body).json();original=first['result']
    headers,_=auth(ctx)
    settled=ctx['client'].post('/v1/inference/'+first['id']+'/reconcile',headers=headers,json={'input_tokens':12,'output_tokens':4,'note':'Reviewed synthetic provider outcome and usage.'})
    assert settled.status_code==200,settled.text
    assert settled.json()['result']['uncertainty_control']==original['uncertainty_control']
    assert settled.json()['result']['spend_control']==original['spend_control']
    assert not ctx['client'].get(URL).json()['models'][0]['blocked']
    second=infer(ctx,body,key='uncertainty-call-intent-0002').json()
    assert second['status']=='unknown' and len(sent)==2 and second['result']['uncertainty_control']['unknown_before_admission']==0


def test_counts_span_periods_but_exclude_pending_completed_other_routes_and_scopes(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch)
    seed_call(ctx,body);seed_call(ctx,body,key='foreign-org',org='other');seed_call(ctx,body,key='foreign-env',env='development')
    seed_call(ctx,body,key='pending',status='pending');seed_call(ctx,body,key='completed',status='completed');seed_call(ctx,body,key='other-model',model='another-route')
    policy(ctx,config(body,limit=2));result=infer(ctx,body).json()
    assert result['status']=='completed' and result['result']['uncertainty_control']['unknown_before_admission']==1 and len(sent)==1
    overview=ctx['client'].get(URL).json();assert overview['models'][0]['unknown_calls']==1 and not overview['models'][0]['blocked']
    assert 'PRIVATE-ANSWER' not in str(overview)


def test_limits_follow_route_id_across_versions_and_policy_changes_do_not_settle_outcomes(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);seed_call(ctx,body);policy(ctx,config(body))
    with ctx['db'].begin() as db:db.get(WorkspaceAsset,body['model_id']).version=3
    assert infer(ctx,{**body,'expected_version':3}).status_code==429 and sent==[]
    assert policy(ctx,config(body,version=1),key='uncertainty-policy-stale-model').status_code==409
    assert policy(ctx,{'expected_version':1,'rules':[],'note':NOTE},key='uncertainty-policy-clear-all').status_code==201
    assert infer(ctx,{**body,'expected_version':3},key='uncertainty-call-after-clear').json()['status']=='completed'
    with ctx['db']() as db:assert db.scalar(select(InferenceCall).where(InferenceCall.key_hash=='prior-unknown')).status=='unknown'


@pytest.mark.parametrize('limit',[0,101,True,1.5])
def test_strict_limits_reject_without_policy_write(ctx,monkeypatch,limit):
    _,body,_=setup(ctx,monkeypatch);assert policy(ctx,config(body,limit)).status_code==422
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind=='model_uncertainty_policy'))==0


def test_duplicate_models_owner_permission_csrf_and_archived_rules(ctx,monkeypatch):
    _,body,_=setup(ctx,monkeypatch);value=config(body)
    assert policy(ctx,{**value,'rules':value['rules']*2}).status_code==422
    assert policy(ctx,value,role='auditor').status_code==403
    headers,_=auth(ctx);assert ctx['client'].put(URL,headers=headers,json=value).status_code==422
    assert ctx['client'].put(URL,headers={'Idempotency-Key':'uncertainty-no-csrf-intent'},json=value).status_code==403
    with ctx['db'].begin() as db:db.get(WorkspaceAsset,body['model_id']).status='archived'
    assert policy(ctx,value).status_code==404


def test_recovery_and_replay_preserve_superseded_receipt_and_scope(ctx,monkeypatch):
    _,body,_=setup(ctx,monkeypatch);value=config(body)
    first=policy(ctx,value).json();assert policy(ctx,value).json()['id']==first['id']
    assert policy(ctx,config(body,2)).status_code==409
    assert policy(ctx,{'expected_version':1,'rules':[],'note':NOTE},key='uncertainty-policy-intent-0002').status_code==201
    headers,_=auth(ctx)
    recovered=ctx['client'].post(URL+'/recover',headers=headers,json={'key':'uncertainty-policy-intent-0001'}).json()
    assert recovered['id']==first['id'] and recovered['status']=='superseded'
    assert ctx['client'].get(URL).json()['version']==2 and ctx['client'].get(URL).json()['rules']==[]
    assert len(ctx['client'].get(URL+'/history').json()['items'])==2
    headers,_=auth(ctx,org='other')
    assert ctx['client'].get(URL).json()['version']==0
    assert ctx['client'].post(URL+'/recover',headers=headers,json={'key':'uncertainty-policy-intent-0001'}).status_code==404
    auth(ctx);assert ctx['client'].get(URL,headers={'X-Nexus-Environment':'production'}).status_code==409


def test_final_history_slot_can_clear_all_guards(ctx,monkeypatch):
    _,body,_=setup(ctx,monkeypatch);policy(ctx,config(body))
    with ctx['db'].begin() as db:
        for i in range(198):db.add(WorkbenchRun(org_id='northstar',env='staging',author_id='synthetic',kind='model_uncertainty_policy',status='superseded',duration_ms=0,result={'version':i+2,'rules':[],'note':NOTE}))
    assert policy(ctx,config(body,version=1),key='uncertainty-policy-over-bound').status_code==429
    assert policy(ctx,{'expected_version':1,'rules':[],'note':NOTE},key='uncertainty-policy-final-disable').status_code==201
    assert ctx['client'].get(URL).json()['rules']==[]


def test_inconsistent_active_policy_fails_closed_before_provider(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);policy(ctx,config(body))
    with ctx['db'].begin() as db:
        db.add(WorkbenchRun(org_id='northstar',env='staging',author_id='synthetic',kind='model_uncertainty_policy',status='active',duration_ms=0,result={'version':2,'rules':[],'note':NOTE}))
    response=infer(ctx,body)
    assert response.status_code==409 and response.json()['error']['code']=='UNCERTAINTY_POLICY_INCONSISTENT' and sent==[]
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(InferenceCall))==0
