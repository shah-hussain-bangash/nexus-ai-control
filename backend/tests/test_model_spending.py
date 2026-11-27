"""Model-route admission ceilings over existing inference rows; no live providers."""
import httpx,pytest
from sqlalchemy import select,func
from conftest import auth
from test_inference import setup
from nexus.db import InferenceCall,InferenceBudget,WorkbenchRun,WorkspaceAsset


def policy(ctx,body,key='model-spend-policy-0001',role='owner'):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].put('/v1/inference-spend-controls',headers=headers,json=body)


def config(body,limit=10000,version=0,required=False):
    return {'expected_version':version,'require_model_caps':required,'caps':[{'model_id':body['model_id'],'expected_model_version':2,'monthly_limit_micro_usd':limit}],
        'note':'Reviewed synthetic model spending ceiling.'}


def infer(ctx,body,key='model-spend-call-0001'):
    headers,_=auth(ctx);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/inference',headers=headers,json=body)


def test_default_has_no_new_limit_and_checked_policy_is_preserved_in_call(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);auth(ctx)
    assert ctx['client'].get('/v1/inference-spend-controls').json()['version']==0
    response=policy(ctx,config(body));assert response.status_code==201,response.text
    saved=response.json();assert saved['version']==1
    result=infer(ctx,body).json();assert result['status']=='completed' and result['result']['spend_control']['policy_id']==saved['id']
    auth(ctx);state=ctx['client'].get('/v1/inference-spend-controls').json();model=next(m for m in state['models'] if m['id']==body['model_id'])
    assert model['spent_micro_usd']=='24' and model['held_micro_usd']=='0' and model['remaining_micro_usd']==9976
    assert len(sent)==1 and 'test-transport-only' not in str(state) and 'credential_ref' not in str(state)
    assert saved['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


def test_projection_blocks_before_provider_and_rolls_back_new_reservation(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);policy(ctx,config(body,limit=1))
    response=infer(ctx,body);assert response.status_code==429,response.text
    assert response.json()['error']['code']=='MODEL_SPEND_LIMIT' and sent==[]
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(InferenceCall))==0
        assert db.scalar(select(func.count()).select_from(InferenceBudget))==0


def test_unknown_reservations_count_and_usage_settlement_retains_policy_evidence(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch,handler=lambda _:httpx.Response(503,json={}))
    policy(ctx,config(body,limit=3000))
    first=infer(ctx,body).json();assert first['status']=='unknown' and first['result']['spend_control']['policy_version']==1
    assert infer(ctx,body,key='model-spend-call-0002').status_code==429 and len(sent)==1
    headers,_=auth(ctx)
    settled=ctx['client'].post('/v1/inference/'+first['id']+'/reconcile',headers=headers,json={'input_tokens':12,'output_tokens':4,'note':'Reviewed synthetic provider usage before settling.'})
    assert settled.status_code==200 and settled.json()['result']['spend_control']['policy_version']==1
    state=ctx['client'].get('/v1/inference-spend-controls').json();model=next(m for m in state['models'] if m['id']==body['model_id'])
    assert model['spent_micro_usd']=='24' and model['held_micro_usd']=='0'


def test_required_mode_blocks_unassigned_new_route_and_does_not_replay_old_calls(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);first=infer(ctx,body).json()
    value=policy(ctx,{'expected_version':0,'require_model_caps':True,'caps':[],'note':'Require owner caps for every new model request.'}).json()
    assert infer(ctx,body).json()['id']==first['id'] and len(sent)==1
    response=infer(ctx,body,key='required-cap-new-call-001');assert response.status_code==429 and response.json()['error']['code']=='MODEL_SPEND_CAP_REQUIRED'
    assert len(sent)==1


def test_cap_applies_across_model_versions_and_lowering_does_not_change_history(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);policy(ctx,config(body));first=infer(ctx,body).json()
    before=first['charged']
    with ctx['db'].begin() as db:db.get(WorkspaceAsset,body['model_id']).version=3
    changed=config(body,limit=10,version=1);changed['caps'][0]['expected_model_version']=3
    assert policy(ctx,changed,key='lowered-model-cap-001').status_code==201
    assert infer(ctx,{**body,'expected_version':3},key='new-version-call-001').status_code==429
    with ctx['db']() as db:assert db.get(InferenceCall,first['id']).charged==before
    auth(ctx);model=next(m for m in ctx['client'].get('/v1/inference-spend-controls').json()['models'] if m['id']==body['model_id'])
    assert model['over_limit'] and model['remaining_micro_usd']==0 and len(sent)==1


def test_policy_replay_recovery_and_stale_version_cannot_reactivate_old_limits(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);original=config(body);one=policy(ctx,original).json()
    two=policy(ctx,config(body,limit=20000,version=1),key='second-spending-policy-001').json()
    old=policy(ctx,original).json();assert old['id']==one['id'] and old['status']=='superseded'
    assert policy(ctx,config(body,limit=3),key='stale-spend-policy-001').status_code==409
    assert policy(ctx,config(body,limit=3)).status_code==409
    headers,_=auth(ctx);recovered=ctx['client'].post('/v1/inference-spend-controls/recover',headers=headers,json={'key':'model-spend-policy-0001'}).json()
    assert recovered['id']==one['id'] and recovered['status']=='superseded'
    assert ctx['client'].get('/v1/inference-spend-controls').json()['version']==2 and sent==[]


def test_owner_write_export_read_and_workspace_scope(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch)
    assert policy(ctx,config(body),role='auditor').status_code==403
    policy(ctx,config(body))
    auth(ctx,'auditor');assert ctx['client'].get('/v1/inference-spend-controls').status_code==200
    auth(ctx,'approver');assert ctx['client'].get('/v1/inference-spend-controls').status_code==403
    auth(ctx,org='other');assert ctx['client'].get('/v1/inference-spend-controls').json()['version']==0
    assert ctx['client'].get('/v1/inference-spend-controls/history').json()['items']==[]


@pytest.mark.parametrize('limit',[-1,True,1.5,1000000000001])
def test_limits_are_bounded_strict_micro_usd(ctx,monkeypatch,limit):
    _,body,sent=setup(ctx,monkeypatch)
    assert policy(ctx,config(body,limit)).status_code==422 and sent==[]


def test_server_workspace_budget_still_applies_under_a_larger_route_cap(ctx,monkeypatch):
    _,body,sent=setup(ctx,monkeypatch);ctx['settings'].monthly_budget_usd='0.000001'
    policy(ctx,config(body,limit=1000000));response=infer(ctx,body)
    assert response.status_code==429 and response.json()['error']['code']=='MONTHLY_BUDGET_EXCEEDED' and sent==[]


def test_pending_request_reservation_blocks_overlapping_model_admission(ctx,monkeypatch):
    observed=[];body_holder={}
    def handler(_):
        response=infer(ctx,body_holder['body'],key='overlapping-model-call-001');observed.append(response.status_code)
        return httpx.Response(200,json={'id':'synthetic-provider-id','choices':[{'message':{'content':'Synthetic reply'},'finish_reason':'stop'}],'usage':{'prompt_tokens':12,'completion_tokens':4}})
    _,body,sent=setup(ctx,monkeypatch,handler=handler);body_holder['body']=body
    policy(ctx,config(body,limit=3000));response=infer(ctx,body)
    assert response.status_code==200,response.text
    assert observed==[429] and len(sent)==1


def test_zero_dollar_cap_allows_zero_provider_cost_local_inference(ctx):
    from test_ollama import setup as local_setup
    headers,body,sent=local_setup(ctx)
    response=policy(ctx,config(body,limit=0,required=True));assert response.status_code==201,response.text
    value=infer(ctx,body).json();assert value['status']=='completed' and value['charged']==0
    assert value['result']['spend_control']['monthly_limit_micro_usd']==0 and len(sent)==2


def test_policy_and_usage_are_isolated_between_environments(ctx,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nexus.db import User
    from nexus.runtime_context import bind_runtime_context
    from nexus.model_spending import register_model_spending
    _,body,sent=setup(ctx,monkeypatch);policy(ctx,config(body,required=True));_,owner=auth(ctx)
    selected={'environment':'production'}
    def human(request,db,*args,**kwargs):
        user=db.get(User,owner);bind_runtime_context(db,user.org_id,selected['environment']);return user
    app=FastAPI();register_model_spending(app,ctx['db'],human)
    with TestClient(app) as client:
        state=client.get('/v1/inference-spend-controls').json();assert state['version']==0 and state['models']==[]
        assert client.get('/v1/inference-spend-controls/history').json()['items']==[]
        assert client.put('/v1/inference-spend-controls',headers={'Idempotency-Key':'wrong-env-model-policy'},json=config(body)).status_code==404
        selected['environment']='staging';assert client.get('/v1/inference-spend-controls').json()['version']==1
    assert sent==[]
