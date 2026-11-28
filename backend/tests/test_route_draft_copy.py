"""Local reset route copying; no model or business transport is contacted."""
import copy as clone
import httpx,pytest
from sqlalchemy import select,func
from conftest import auth
from test_local_switching import prepare,current,headers,switch
from test_environment_asset_copy import payload,copy,resolve
from nexus.db import WorkspaceAsset,AssetRevision,InferenceCall,Audit,WorkspaceEnvironment


def route(ctx,kind='model'):
    config={'provider':'OpenAI','model':'synthetic-route','endpoint':'https://api.openai.com/v1','credential_ref':'env:NEXUS_PROVIDER_TEAM_KEY','token_limit':1024,'timeout_ms':2000,'temperature':0.3} if kind=='model' else {
        'protocol':'REST','endpoint':'https://customer.test.invalid/api','credential_ref':'env:NEXUS_CUSTOMER_KEY','scopes':['records:read','records:write'],'read_only':False}
    created=ctx['client'].post('/v1/workbench',headers=headers(current(ctx)),json={'kind':kind,'name':'Reviewed route','description':'Synthetic route design.','config':config})
    assert created.status_code==201,created.text
    checked=ctx['client'].post('/v1/workbench/'+created.json()['id']+'/validate',headers=headers(current(ctx)),json={'expected_version':1})
    assert checked.status_code==200,checked.text
    return checked.json()


@pytest.mark.parametrize('kind',['model','connector'])
def test_route_copy_resets_target_config_and_revision_without_mutating_source(ctx,kind):
    target=prepare(ctx);original=route(ctx,kind);before=clone.deepcopy(original['config']);body=payload(original,target)
    result=copy(ctx,body);assert result.status_code==201,result.text
    value=result.json();expected=['credential_ref'] if kind=='model' else ['credential_ref','scopes','read_only']
    assert value['kind']==kind and value['reset_fields']==expected
    with ctx['db']() as db:
        source=db.get(WorkspaceAsset,original['id']);draft=db.get(WorkspaceAsset,value['target_asset_id'])
        assert source.config==before and source.status=='validated' and source.version==original['version']
        assert draft.config['credential_ref']=='' and draft.status=='draft' and draft.version==1 and draft.env=='production'
        assert draft.config['endpoint']==before['endpoint']
        if kind=='connector':assert draft.config['scopes']==[] and draft.config['read_only'] is True and source.config['scopes']==['records:read','records:write']
        snapshot=db.scalar(select(AssetRevision).where(AssetRevision.asset_id==draft.id)).snapshot
        assert snapshot['config']==draft.config and snapshot['copied_from']['reset_fields']==expected
        assert 'env:NEXUS_PROVIDER_TEAM_KEY' not in str(snapshot) and 'env:NEXUS_CUSTOMER_KEY' not in str(snapshot)
        audit=db.scalar(select(Audit).where(Audit.event=='environment.asset_copied'))
        assert audit.detail['reset_fields']==expected
        assert db.scalar(select(func.count()).select_from(InferenceCall))==0
    assert ctx['settings'].live_inference==0 and ctx['settings'].ollama_enabled==0 and ctx['settings'].business_connector=='synthetic'
    assert copy(ctx,body).json()==value and resolve(ctx,'recover').json()==value and resolve(ctx,'cancel').json()==value


def test_copied_hosted_model_cannot_execute_draft_or_reuse_source_secret(ctx,monkeypatch):
    target=prepare(ctx);original=route(ctx);receipt=copy(ctx,payload(original,target)).json();switched=switch(ctx,target)
    sent=[];ctx['app'].state.provider_transport=httpx.MockTransport(lambda request:sent.append(request) or httpx.Response(500))
    ctx['settings'].live_inference=1;ctx['settings'].provider_hosts='api.openai.com';ctx['settings'].provider_prices='{"api.openai.com|synthetic-route":{"input":"1","output":"3"}}';ctx['settings'].monthly_budget_usd='1'
    monkeypatch.setenv('NEXUS_PROVIDER_TEAM_KEY','synthetic-source-secret-available-on-server')
    request_headers={**headers(switched),'Idempotency-Key':'copied-model-execution-0001'}
    body={'model_id':receipt['target_asset_id'],'expected_version':1,'query':'Synthetic question','max_output_tokens':100}
    response=ctx['client'].post('/v1/inference',headers=request_headers,json=body)
    assert response.status_code==409 and response.json()['error']['code']=='MODEL_NOT_CHECKED' and sent==[]
    checked=ctx['client'].post('/v1/workbench/'+receipt['target_asset_id']+'/validate',headers=headers(switched),json={'expected_version':1})
    assert checked.status_code==200
    response=ctx['client'].post('/v1/inference',headers=request_headers,json={**body,'expected_version':checked.json()['version']})
    assert response.status_code==422 and response.json()['error']['code']=='SECRET_REFERENCE_REQUIRED' and sent==[]
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(InferenceCall))==0


def test_route_copy_requires_exact_versions_and_rejects_workflow_mappings(ctx):
    target=prepare(ctx);original=route(ctx,'connector');body=payload(original,target)
    assert copy(ctx,{**body,'expected_source_version':1}).status_code==409
    assert copy(ctx,{**body,'reference_mappings':[{'node_id':'unrelated','target_asset_id':'none','expected_target_asset_version':1}]}).status_code==422
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production'))==0


def test_replay_preserves_original_reset_receipt_after_target_is_edited(ctx):
    target=prepare(ctx);original=route(ctx,'connector');body=payload(original,target);first=copy(ctx,body).json();switched=switch(ctx,target)
    draft=ctx['client'].get('/v1/workbench',headers=headers(switched)).json()['assets'][0]
    updated=ctx['client'].put('/v1/workbench/'+draft['id'],headers=headers(switched),json={'kind':draft['kind'],'expected_version':1,'name':draft['name'],'description':draft['description'],'config':{**draft['config'],'scopes':['explicitly:reviewed'],'read_only':False}})
    assert updated.status_code==200,updated.text
    with ctx['db']() as db:staging=db.get(WorkspaceEnvironment,('northstar','staging'))
    switch(ctx,{'key':'staging','version':staging.version})
    assert resolve(ctx,'recover').json()==first and copy(ctx,body).json()==first
