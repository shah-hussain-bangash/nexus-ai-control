import json
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from conftest import auth,assign_staging
from nexus.db import WorkspaceAsset, InferenceCall, InferenceBudget, User, Action, SchemaVersion, migrate
from nexus.config import Settings
from nexus.security import issue_session


def setup(ctx, monkeypatch, handler=None):
    settings=ctx['settings'];settings.live_inference=1;settings.provider_hosts='api.openai.com';settings.provider_prices=json.dumps({'api.openai.com|test-model':{'input':'1','output':'3'}});settings.monthly_budget_usd='1'
    monkeypatch.setenv('NEXUS_PROVIDER_TEST_KEY','test-transport-only')
    with ctx['db'].begin() as db:
        row=WorkspaceAsset(org_id='northstar',kind='model',name='Checked provider',status='validated',version=2,author_id='test',config={'provider':'OpenAI','model':'test-model','endpoint':'https://api.openai.com/v1','credential_ref':'env:NEXUS_PROVIDER_TEST_KEY','token_limit':4096,'timeout_ms':2000,'temperature':0.2});db.add(row);db.flush();model_id=row.id
    sent=[]
    def call(req):
        sent.append(req)
        if handler:return handler(req)
        return httpx.Response(200,json={'id':'provider-test','choices':[{'message':{'content':'Synthetic verified transport answer'},'finish_reason':'stop'}],'usage':{'prompt_tokens':12,'completion_tokens':4}})
    ctx['app'].state.provider_transport=httpx.MockTransport(call)
    headers,_=auth(ctx);headers['Idempotency-Key']='inference-request-0001'
    body={'model_id':model_id,'expected_version':2,'query':'Synthetic question','max_output_tokens':100}
    return headers,body,sent


def test_inference_disabled_and_anonymous(ctx):
    assert ctx['client'].get('/v1/runtime').status_code==401
    h,_=auth(ctx);h['Idempotency-Key']='inference-request-0001'
    assert ctx['client'].post('/v1/inference',headers=h,json={'model_id':'missing','expected_version':1,'query':'Hi'}).status_code==503


def test_real_transport_contract_budget_and_replay(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch)
    r=ctx['client'].post('/v1/inference',json=b,headers=h);assert r.status_code==200,r.text
    call=r.json();assert call['status']=='completed' and call['charged']==24
    assert call['result']['answer']=='Synthetic verified transport answer'
    payload=json.loads(sent[0].content);assert payload['max_completion_tokens']==100 and payload['store'] is False and 'tools' not in payload
    assert sent[0].headers['authorization']=='Bearer test-transport-only'
    assert ctx['client'].post('/v1/inference',json=b,headers=h).json()['id']==call['id']
    assert len(sent)==1
    conflict=ctx['client'].post('/v1/inference',json={**b,'query':'changed'},headers=h);assert conflict.status_code==409
    runtime=ctx['client'].get('/v1/runtime').json();assert runtime['spent_micro_usd']==24 and runtime['held_micro_usd']==0
    assert 'test-transport-only' not in r.text and 'key_hash' not in call and 'request_hash' not in call
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(Action))==0


@pytest.mark.parametrize('handler',[lambda req:httpx.Response(429,json={'error':{'message':'private provider body secret'}}),lambda req:httpx.Response(200,json={'choices':[]}),lambda req:httpx.Response(302,headers={'location':'https://evil.invalid'})])
def test_provider_uncertainty_retains_reservation_no_retry(ctx,monkeypatch,handler):
    h,b,sent=setup(ctx,monkeypatch,handler)
    r=ctx['client'].post('/v1/inference',headers=h,json=b);assert r.status_code==200 and r.json()['status']=='unknown'
    runtime=ctx['client'].get('/v1/runtime').json();assert runtime['held_micro_usd']>0 and runtime['spent_micro_usd']==0
    assert 'private provider body' not in r.text
    assert ctx['client'].post('/v1/inference',headers=h,json=b).json()['status']=='unknown' and len(sent)==1


def test_timeout_is_not_automatically_retried(ctx,monkeypatch):
    def timeout(req):raise httpx.ReadTimeout('Secret upstream details',request=req)
    h,b,sent=setup(ctx,monkeypatch,timeout)
    response=ctx['client'].post('/v1/inference',headers=h,json=b)
    assert response.json()['status']=='unknown' and len(sent)==1 and 'Secret upstream' not in response.text


def test_owner_reconciliation_once_and_cross_tenant(ctx,monkeypatch):
    h,b,_=setup(ctx,monkeypatch,lambda req:httpx.Response(500))
    row=ctx['client'].post('/v1/inference',headers=h,json=b).json()
    url='/v1/inference/'+row['id']+'/reconcile';body={'input_tokens':10,'output_tokens':2,'note':'Verified synthetic provider usage reference 123.'}
    bad,_=auth(ctx,'auditor');assert ctx['client'].post(url,headers=bad,json=body).status_code==403
    other,_=auth(ctx,org='other');assert ctx['client'].post(url,headers=other,json=body).status_code==404
    h,_=auth(ctx);assert ctx['client'].post(url,headers=h,json=body).json()['charged']==16
    assert ctx['client'].post(url,headers=h,json=body).status_code==409
    runtime=ctx['client'].get('/v1/runtime').json();assert runtime['held_micro_usd']==0 and runtime['spent_micro_usd']==16


def test_pending_reconciliation_grace(ctx,monkeypatch):
    h,b,_=setup(ctx,monkeypatch,lambda req:httpx.Response(500))
    row=ctx['client'].post('/v1/inference',headers=h,json=b).json()
    with ctx['db'].begin() as db:db.get(InferenceCall,row['id']).status='pending'
    body={'input_tokens':0,'output_tokens':0,'note':'Verified no provider usage for crashed synthetic request.'}
    url='/v1/inference/'+row['id']+'/reconcile'
    assert ctx['client'].post(url,headers=h,json=body).status_code==409
    with ctx['db'].begin() as db:db.get(InferenceCall,row['id']).created=time.time()-400
    assert ctx['client'].post(url,headers=h,json=body).status_code==200


@pytest.mark.parametrize('change',[{'endpoint':'https://evil.invalid/v1'},{'endpoint':'https://api.openai.com.evil.invalid/v1'},{'endpoint':'https://api.openai.com:8443/v1'},{'endpoint':'https://api.openai.com/v1/other'},{'credential_ref':'env:NEXUS_SECRET'},{'model':'unpriced'}])
def test_egress_and_secret_and_price_boundaries(ctx,monkeypatch,change):
    h,b,sent=setup(ctx,monkeypatch)
    with ctx['db'].begin() as db:
        row=db.get(WorkspaceAsset,b['model_id']);row.config={**row.config,**change}
    assert ctx['client'].post('/v1/inference',headers=h,json=b).status_code==422
    assert not sent


def test_unknown_secret_config_and_schema(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch);monkeypatch.delenv('NEXUS_PROVIDER_TEST_KEY')
    assert ctx['client'].post('/v1/inference',headers=h,json=b).status_code==503 and not sent
    assert ctx['client'].post('/v1/inference',headers=h,json={**b,'unexpected':'secret'}).status_code==422
    assert ctx['client'].post('/v1/inference',headers=h,json={**b,'expected_version':1}).status_code==409


def test_roles_csrf_and_cross_tenant_model(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch)
    assert ctx['client'].post('/v1/inference',headers={'Idempotency-Key':h['Idempotency-Key']},json=b).status_code==403
    reader,_=auth(ctx,'approver');reader['Idempotency-Key']=h['Idempotency-Key'];assert ctx['client'].post('/v1/inference',headers=reader,json=b).status_code==403
    other,_=auth(ctx,org='other');other['Idempotency-Key']=h['Idempotency-Key'];assert ctx['client'].post('/v1/inference',headers=other,json=b).status_code==404
    assert ctx['client'].get('/v1/runtime').json()['calls']==[] and not sent


def test_guardrail_prevents_external_call(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch)
    with ctx['db'].begin() as db:db.add(WorkspaceAsset(org_id='northstar',kind='guardrail',name='Block private test',author_id='test',config={'blocked_terms':['blocked input'],'detect_email':True,'detect_override':True,'mode':'block'}))
    assert ctx['client'].post('/v1/inference',headers=h,json={**b,'query':'blocked input'}).status_code==422 and not sent


def test_atomic_budget_competing_requests(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch)
    # Each reservation exceeds 0.002 USD; only one fits the 0.003 USD cap.
    ctx['settings'].monthly_budget_usd='0.003'
    cookie=ctx['client'].cookies.get('nexus_session')
    def run(index):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post('/v1/inference',headers={**h,'Idempotency-Key':'parallel-request-'+str(index).zfill(4)},json=b).status_code
    # Retain reservations after ambiguous provider outcome so both compete for the same capacity.
    ctx['app'].state.provider_transport=httpx.MockTransport(lambda req:httpx.Response(500))
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(run,[1,2]))
    assert sorted(statuses)==[200,429]
    with ctx['db']() as db:
        budget=db.scalar(select(InferenceBudget));assert budget.held<=3000 and budget.spent==0
        assert db.scalar(select(func.count()).select_from(InferenceCall))==1


def test_operator_configuration_rejects_invalid_limits():
    with pytest.raises(RuntimeError):Settings(secret='s'*48,agent_secret='a'*48,live_inference=1).validate()
    with pytest.raises(RuntimeError):Settings(secret='s'*48,agent_secret='a'*48,provider_prices='{"route":{"input":"NaN","output":"1"}}').validate()


def test_schema_three_upgrade_preserves_assets(ctx):
    with ctx['app'].state.engine.begin() as connection:
        InferenceCall.__table__.drop(connection);InferenceBudget.__table__.drop(connection)
        connection.execute(SchemaVersion.__table__.delete().where(SchemaVersion.version>=4))
    migrate(ctx['app'].state.engine,ctx['db'])
    with ctx['db']() as db:assert db.get(SchemaVersion,4) and db.scalar(select(User))


def test_engineer_cannot_remove_guardrails_or_activate_model(ctx,monkeypatch):
    h,b,_=setup(ctx,monkeypatch)
    with ctx['db'].begin() as db:
        engineer=User(org_id='northstar',email='engineer@synthetic.invalid',name='Engineer',role='engineer');db.add(engineer);db.flush()
        assign_staging(db,engineer)
        token,csrf=issue_session(db,engineer,ctx['settings'])
        guard=WorkspaceAsset(org_id='northstar',kind='guardrail',name='Security owned rules',author_id='test',config={'blocked_terms':[],'detect_email':True,'detect_override':True,'mode':'block'});db.add(guard);db.flush();gid=guard.id
    ctx['client'].cookies.set('nexus_session',token);headers={'X-CSRF-Token':csrf}
    assert ctx['client'].post('/v1/workbench/'+gid+'/archive',headers=headers,json={'expected_version':1}).status_code==403
    assert ctx['client'].post('/v1/workbench/'+b['model_id']+'/validate',headers=headers,json={'expected_version':2}).status_code==403
    assert ctx['client'].post('/v1/workbench-starter',headers=headers).status_code==403


def test_azure_v1_contract(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch)
    ctx['settings'].provider_hosts='verified-resource.openai.azure.com'
    ctx['settings'].provider_prices=json.dumps({'verified-resource.openai.azure.com|test-model':{'input':'1','output':'3'}})
    with ctx['db'].begin() as db:
        row=db.get(WorkspaceAsset,b['model_id']);row.config={**row.config,'provider':'Azure OpenAI','endpoint':'https://verified-resource.openai.azure.com/openai/v1'}
    assert ctx['client'].post('/v1/inference',headers=h,json=b).json()['status']=='completed'
    assert str(sent[0].url)=='https://verified-resource.openai.azure.com/openai/v1/chat/completions'
    assert sent[0].headers['api-key']=='test-transport-only' and 'authorization' not in sent[0].headers


def test_response_cap_and_input_redaction(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch,lambda req:httpx.Response(200,content=b'x'*10000))
    ctx['settings'].inference_response_bytes=4096
    with ctx['db'].begin() as db:db.add(WorkspaceAsset(org_id='northstar',kind='guardrail',name='Redaction rule',author_id='test',config={'blocked_terms':[],'detect_email':True,'detect_override':True,'mode':'redact'}))
    result=ctx['client'].post('/v1/inference',headers=h,json={**b,'query':'Synthetic email person@example.invalid'})
    assert result.json()['status']=='unknown'
    assert b'person@example.invalid' not in sent[0].content and b'[EMAIL]' in sent[0].content


def test_concurrent_same_intent_dispatches_once(ctx,monkeypatch):
    h,b,sent=setup(ctx,monkeypatch)
    cookie=ctx['client'].cookies.get('nexus_session')
    def run(index):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post('/v1/inference',headers=h,json=b)
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(run,[1,2]))
    assert all(r.status_code==200 for r in responses)
    assert responses[0].json()['id']==responses[1].json()['id'] and len(sent)==1


@pytest.mark.parametrize('change',[
    'root_null','root_list','root_string','usage_null','usage_list','choices_null',
    'choices_object','choices_empty','choice_null','choice_list','message_missing',
    'message_null','message_list','message_string','message_number','content_list',
    'usage_boolean','tool_call',
])
def test_malformed_provider_shapes_retain_budget_and_recover_without_retry(ctx,monkeypatch,change):
    private='private upstream shape sentinel'
    data={'id':'synthetic-shape','choices':[{'message':{'content':private},'finish_reason':'stop'}],
          'usage':{'prompt_tokens':12,'completion_tokens':4}}
    if change=='root_null':data=None
    elif change=='root_list':data=[private]
    elif change=='root_string':data=private
    elif change=='usage_null':data['usage']=None
    elif change=='usage_list':data['usage']=[private]
    elif change=='choices_null':data['choices']=None
    elif change=='choices_object':data['choices']={'0':private}
    elif change=='choices_empty':data['choices']=[]
    elif change=='choice_null':data['choices']=[None]
    elif change=='choice_list':data['choices']=[[private]]
    elif change=='message_missing':del data['choices'][0]['message']
    elif change=='message_null':data['choices'][0]['message']=None
    elif change=='message_list':data['choices'][0]['message']=[private]
    elif change=='message_string':data['choices'][0]['message']=private
    elif change=='message_number':data['choices'][0]['message']=12
    elif change=='content_list':data['choices'][0]['message']['content']=[private]
    elif change=='usage_boolean':data['usage']['prompt_tokens']=True
    elif change=='tool_call':data['choices'][0]['message']['tool_calls']=[{'id':private}]
    h,b,sent=setup(ctx,monkeypatch,lambda req:httpx.Response(200,json=data))
    response=ctx['client'].post('/v1/inference',headers=h,json=b)
    assert response.status_code==200,response.text
    row=response.json();assert row['status']=='unknown' and row['charged']==0
    assert private not in response.text and len(sent)==1
    runtime=ctx['client'].get('/v1/runtime').json()
    assert runtime['held_micro_usd']==row['reserved']>0 and runtime['spent_micro_usd']==0
    replay=ctx['client'].post('/v1/inference',headers=h,json=b)
    recovered=ctx['client'].post('/v1/inference/recover',headers=h,json={'key':h['Idempotency-Key']})
    assert replay.status_code==recovered.status_code==200
    assert replay.json()['id']==recovered.json()['id']==row['id'] and len(sent)==1
    assert recovered.json()['status']=='unknown' and private not in recovered.text
    settled=ctx['client'].post('/v1/inference/'+row['id']+'/reconcile',headers=h,json={
        'input_tokens':10,'output_tokens':2,'note':'Verified disposable synthetic provider usage only.'})
    assert settled.status_code==200 and settled.json()['status']=='reconciled'
    runtime=ctx['client'].get('/v1/runtime').json()
    assert runtime['held_micro_usd']==0 and runtime['spent_micro_usd']==16 and len(sent)==1


@pytest.mark.parametrize('phase',['headers','body','close','decode'])
@pytest.mark.parametrize('elapsed',[1.99,2.0,2.01])
def test_provider_deadline_fences_completion_and_preserves_recovery(ctx,monkeypatch,phase,elapsed):
    from nexus import inference
    clock=[100.0];answer='Private synthetic late provider answer'
    payload=json.dumps({'id':'deadline-synthetic','choices':[{'message':{'content':answer},'finish_reason':'stop'}],
                        'usage':{'prompt_tokens':12,'completion_tokens':4}}).encode()
    class TimedBody(httpx.SyncByteStream):
        def __iter__(self):
            if phase=='body':clock[0]=100.0+elapsed
            yield payload
        def close(self):
            if phase=='close':clock[0]=100.0+elapsed
    def handler(request):
        if phase=='headers':clock[0]=100.0+elapsed
        return httpx.Response(200,stream=TimedBody())
    def decode(data):
        result=json.loads(data)
        if phase=='decode' and isinstance(data,bytes):clock[0]=100.0+elapsed
        return result
    # Patch only this module's references; neither the OS clock nor other modules change.
    monkeypatch.setattr(inference,'time',SimpleNamespace(monotonic=lambda:clock[0],time=time.time,perf_counter=time.perf_counter))
    monkeypatch.setattr(inference,'json',SimpleNamespace(loads=decode,dumps=json.dumps))
    h,b,sent=setup(ctx,monkeypatch,handler)
    response=ctx['client'].post('/v1/inference',headers=h,json=b)
    assert response.status_code==200,response.text
    row=response.json();runtime=ctx['client'].get('/v1/runtime').json()
    if elapsed<2:
        assert row['status']=='completed' and row['result']['answer']==answer and row['charged']==24
        assert runtime['held_micro_usd']==0 and runtime['spent_micro_usd']==24
    else:
        assert row['status']=='unknown' and row['charged']==0 and answer not in response.text
        assert runtime['held_micro_usd']==row['reserved']>0 and runtime['spent_micro_usd']==0
    replay=ctx['client'].post('/v1/inference',headers=h,json=b)
    recovered=ctx['client'].post('/v1/inference/recover',headers=h,json={'key':h['Idempotency-Key']})
    assert replay.status_code==recovered.status_code==200
    assert replay.json()['id']==recovered.json()['id']==row['id'] and len(sent)==1
    assert recovered.json()['status']==row['status']
    if elapsed>=2:
        assert answer not in recovered.text
        settled=ctx['client'].post('/v1/inference/'+row['id']+'/reconcile',headers=h,json={
            'input_tokens':10,'output_tokens':2,'note':'Verified synthetic usage after simulated provider deadline.'})
        assert settled.status_code==200 and settled.json()['status']=='reconciled'
        runtime=ctx['client'].get('/v1/runtime').json()
        assert runtime['held_micro_usd']==0 and runtime['spent_micro_usd']==16 and len(sent)==1
