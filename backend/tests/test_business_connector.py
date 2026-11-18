import copy
import json
import httpx
import pytest
from dataclasses import replace
from sqlalchemy import select,update
from nexus.business_connector import HTTPBusiness,connector_identity,connector_profile,validate_business
from nexus.config import Settings
from nexus.mock_connector import UncertainOutcome
from nexus.service import verify
from nexus.worker import run_once
from nexus.db import Action
from conftest import auth,submit,approve

@pytest.fixture
def business(monkeypatch):
    monkeypatch.setenv('NEXUS_BUSINESS_API_KEY','unit-test-business-key-'+'x'*32)
    return Settings(business_connector='http',business_base_url='https://sandbox.customer.invalid/api/v1',business_host='sandbox.customer.invalid',business_tenant='test-tenant')

def envelope(settings,action='purchase:create'):
    return {'org_id':'northstar','destination':connector_identity(settings),'action':action,'arguments':{'supplier_id':'VENDOR-105','amount':'12500.00','currency':'USD','purpose':'Contract test'}}

def authoritative(request,settings,*,payload=None,code=201):
    id=request.headers['Idempotency-Key'];return httpx.Response(code,json={'operation_id':id,'organization_id':'northstar','tenant_id':settings.business_tenant,'result':payload or {'external_ref':'CUSTOMER-123','state':'created','supplier_id':'VENDOR-105','amount':'12500.00','currency':'USD','purpose':'Contract test'}})

def test_http_contract_headers_tls_scoped_payload_and_minimized_result(business):
    seen=[]
    def handler(request):
        seen.append(request);assert request.url==business.business_base_url+'/purchase-requests'
        assert request.headers['X-Nexus-Organization']=='northstar' and request.headers['X-Nexus-Tenant']=='test-tenant'
        assert json.loads(request.content)['arguments']['supplier_id']=='VENDOR-105'
        return authoritative(request,business,payload={**envelope(business)['arguments'],'state':'created','external_ref':'CUSTOMER-123','debug':'private upstream diagnostics'})
    adapter=HTTPBusiness(business,transport=httpx.MockTransport(handler));result=adapter.invoke('operation-001',envelope(business))
    assert verify(envelope(business),result) and 'debug' not in result and len(seen)==1
    assert 'key' not in json.dumps(connector_profile(business)).lower()

def test_uncertain_http_responses_never_retry(business):
    for response in [httpx.Response(503),httpx.Response(302,headers={'Location':'https://other.invalid/'}),httpx.Response(200,text='bad'),httpx.Response(200,json=[]),httpx.Response(201,json={'operation_id':'wrong','result':{}})]:
        calls=[]
        def handler(request):calls.append(request);return response
        with pytest.raises(UncertainOutcome):HTTPBusiness(business,transport=httpx.MockTransport(handler)).invoke('operation-001',envelope(business))
        assert len(calls)==1
    def timeout(request):raise httpx.ReadTimeout('private error',request=request)
    with pytest.raises(UncertainOutcome):HTTPBusiness(business,transport=httpx.MockTransport(timeout)).invoke('operation-001',envelope(business))

def test_contract_scope_bounds_and_reconciliation(business):
    def handler(request):
        if request.url.path.endswith('/missing'):return httpx.Response(404)
        return authoritative(request,business)
    adapter=HTTPBusiness(business,transport=httpx.MockTransport(handler))
    assert adapter.lookup('operation-001',envelope(business))['external_ref']=='CUSTOMER-123'
    assert adapter.lookup('missing',envelope(business)) is None
    with pytest.raises(ValueError):adapter.invoke('operation-001',envelope(replace(business,business_tenant='another-tenant')))
    with pytest.raises(ValueError):adapter.invoke('operation-001',envelope(business),simulation='mismatch')
    huge=HTTPBusiness(replace(business,business_response_bytes=4096),transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*4097)))
    with pytest.raises(UncertainOutcome):huge.invoke('operation-001',envelope(business))

def test_operator_http_configuration_rejects_unsafe_urls_or_missing_secret(business,monkeypatch):
    for url in ['http://sandbox.customer.invalid','https://user:pass@sandbox.customer.invalid','https://sandbox.customer.invalid/?secret=1','https://other.invalid','https://sandbox.customer.invalid:8443','https://sandbox.customer.invalid/%2e%2e/']:
        with pytest.raises(RuntimeError):validate_business(replace(business,business_base_url=url))
    monkeypatch.delenv('NEXUS_BUSINESS_API_KEY')
    with pytest.raises(RuntimeError):validate_business(business)

def test_destination_change_blocks_before_network_and_old_mock_approval_does_not_move(ctx,business):
    response=submit(ctx);assert approve(ctx).status_code==200
    calls=[];adapter=HTTPBusiness(business,transport=httpx.MockTransport(lambda r:calls.append(r) or authoritative(r,business)))
    run_once(ctx['db'],business,adapter)
    with ctx['db']() as db:assert db.get(Action,response.json()['id']).status=='blocked'
    assert calls==[]

def test_http_submission_pins_binding_and_outcome_unknown_reconciles(ctx,business):
    ctx['settings'].business_connector=business.business_connector
    for field in ['business_base_url','business_host','business_tenant']:setattr(ctx['settings'],field,getattr(business,field))
    response=submit(ctx);assert response.status_code==202,response.text;row=response.json();assert row['envelope']['destination']==connector_identity(business)
    assert approve(ctx).status_code==200
    seen=[]
    def handler(request):
        seen.append(request)
        if request.method=='POST':raise httpx.ReadTimeout('ambiguous transport outcome',request=request)
        args=row['envelope']['arguments']
        return authoritative(request,business,payload={**args,'external_ref':'EXT-VERIFIED','state':'created'})
    adapter=HTTPBusiness(ctx['settings'],transport=httpx.MockTransport(handler));ctx['app'].state.connector=adapter
    run_once(ctx['db'],ctx['settings'],adapter)
    with ctx['db']() as db:assert db.get(Action,row['id']).status=='outcome_unknown'
    run_once(ctx['db'],ctx['settings'],adapter);assert len(seen)==1
    h,_=auth(ctx);r=ctx['client'].post('/v1/actions/'+row['id']+'/reconcile',headers=h)
    assert r.status_code==200 and r.json()['status']=='verified',r.text
    assert len(seen)==2 and seen[1].method=='GET'

def test_verification_requires_state_and_original_purchase_purpose(business):
    e=envelope(business);payload={**e['arguments'],'external_ref':'EXT','state':'created'}
    assert verify(e,payload)
    assert not verify(e,{**payload,'purpose':'Another purchase'})
    assert not verify(e,{**payload,'state':'pending'})

def test_workflow_destination_is_pinned_before_independent_review(ctx,business):
    from test_durable import create,advance
    run=create(ctx,review=False,purchase=False)
    assert run['definition']['destination']=='mock-business-v1'
    ctx['settings'].business_connector='http'
    for field in ['business_base_url','business_host','business_tenant']:setattr(ctx['settings'],field,getattr(business,field))
    stopped=advance(ctx,run['id'])
    assert stopped['status']=='failed' and stopped['error']=='DESTINATION_CHANGED'
    with ctx['db']() as db:assert db.scalar(select(__import__('sqlalchemy').func.count()).select_from(Action))==0


def test_advertised_tool_schema_matches_current_supplier_contract(ctx):
    import re
    auth(ctx)
    for tool in ctx['client'].get('/v1/tools').json():
        pattern=tool['schema_json']['properties']['supplier_id']['pattern']
        assert re.fullmatch(pattern,'VENDOR-105') and not re.fullmatch(pattern,'../unsafe')
        assert tool['schema_origin']=='current fixed server contract'


def test_mismatched_customer_result_remains_uncertain_for_reconciliation(business):
    for change in [{'amount':'1.00'},{'purpose':'Another operation'},{'state':'pending'},{'supplier_id':'WRONG-105'}]:
        result={**envelope(business)['arguments'],'external_ref':'EXT','state':'created',**change}
        adapter=HTTPBusiness(business,transport=httpx.MockTransport(lambda request:authoritative(request,business,payload=result)))
        with pytest.raises(UncertainOutcome):adapter.invoke('operation-001',envelope(business))
