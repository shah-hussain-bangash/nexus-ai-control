"""Development checks for the reference gateway; no real network or ERP."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import importlib.util
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select
from conftest import approve, auth, submit
from nexus.business_connector import HTTPBusiness, connector_identity
from nexus.business_reference import ReferenceBusinessStore, ReferenceCredential, create_reference_gateway
from nexus.config import Settings
from nexus.db import Action
from nexus.worker import run_once

TOKEN='synthetic-reference-credential-0001'
OTHER='synthetic-reference-credential-0002'


def headers(token=TOKEN,tenant='demo-tenant',org='northstar',operation='reference-operation-0001'):
    return {'Authorization':'Bearer '+token,'X-Nexus-Tenant':tenant,'X-Nexus-Organization':org,
            'X-Nexus-Contract':'nexus-business-v1','Idempotency-Key':operation}


def body(operation='reference-operation-0001',tenant='demo-tenant',org='northstar',**changes):
    return {'operation_id':operation,'tenant_id':tenant,'organization_id':org,'arguments':{
        'supplier_id':'SUP-DEMO-104','amount':'12500.00','currency':'USD','purpose':'Synthetic reference purchase',**changes}}


def counts(store):
    with store.connect() as db:
        return tuple(db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                     for table in ('operations','synthetic_purchases'))


@pytest.fixture
def reference(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('Real network used by reference development checks')
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    store=ReferenceBusinessStore.create(tmp_path/'reference')
    grants=(ReferenceCredential(TOKEN,'demo-tenant','northstar'),)
    with TestClient(create_reference_gateway(store,grants)) as client:
        yield store,client,grants


def test_atomic_purchase_replay_changed_body_and_read_only_reconciliation(reference):
    store,client,_=reference
    first=client.post('/api/v1/purchase-requests',headers=headers(),json=body())
    assert first.status_code==201 and first.json()['result']['state']=='created'
    replay=client.post('/api/v1/purchase-requests',headers=headers(),json=body())
    assert replay.status_code==200 and replay.json()==first.json() and counts(store)==(1,1)
    conflict=client.post('/api/v1/purchase-requests',headers=headers(),json=body(amount='12501.00'))
    assert conflict.status_code==409 and counts(store)==(1,1)
    lookup=client.get('/api/v1/operations/reference-operation-0001',headers=headers())
    assert lookup.json()==first.json() and counts(store)==(1,1)


def test_supplier_read_receipt_and_cross_action_key_conflict(reference):
    store,client,_=reference
    result=client.get('/api/v1/suppliers/SUP-DEMO-104',headers=headers())
    assert result.status_code==200 and result.json()['result']['state']=='found'
    assert client.get('/api/v1/suppliers/SUP-DEMO-104',headers=headers()).json()==result.json()
    assert client.post('/api/v1/purchase-requests',headers=headers(),json=body()).status_code==409
    assert client.get('/api/v1/operations/reference-operation-0001',headers=headers()).json()==result.json()
    assert counts(store)==(1,0)


@pytest.mark.parametrize('changes',[{'token':'wrong-credential-0001'},{'tenant':'different-tenant'},{'org':'other'}])
def test_request_headers_cannot_expand_credential_scope(reference,changes):
    store,client,_=reference
    response=client.post('/api/v1/purchase-requests',headers=headers(**changes),json=body())
    assert response.status_code in (401,403) and counts(store)==(0,0)
    assert TOKEN not in response.text and '12500' not in response.text


@pytest.mark.parametrize('field,value',[('tenant_id','other-tenant'),('organization_id','other'),('operation_id','different-operation')])
def test_body_scope_must_match_bound_headers(reference,field,value):
    store,client,_=reference
    response=client.post('/api/v1/purchase-requests',headers=headers(),json={**body(),field:value})
    assert response.status_code==403 and counts(store)==(0,0)


def test_missing_receipt_never_creates_an_effect(reference):
    store,client,_=reference
    assert client.get('/api/v1/operations/reference-operation-0001',headers=headers()).status_code==404
    assert client.get('/api/v1/operations/another-operation',headers=headers()).status_code==409
    assert client.get('/api/v1/suppliers/UNKNOWN',headers=headers()).status_code==404
    assert counts(store)==(0,0)


@pytest.mark.parametrize('scope',[('demo-tenant','other'),('other-tenant','northstar')])
def test_same_key_is_independent_across_authorized_scopes(reference,scope):
    store,client,grants=reference
    original=client.post('/api/v1/purchase-requests',headers=headers(),json=body()).json()
    tenant,org=scope
    with TestClient(create_reference_gateway(store,(*grants,ReferenceCredential(OTHER,tenant,org)))) as second:
        other_headers=headers(token=OTHER,tenant=tenant,org=org)
        assert second.get('/api/v1/operations/reference-operation-0001',headers=other_headers).status_code==404
        result=second.post('/api/v1/purchase-requests',headers=other_headers,json=body(tenant=tenant,org=org))
        assert result.status_code==201 and result.json()['result']['external_ref']!=original['result']['external_ref']
    assert counts(store)==(2,2)


def test_receipts_survive_store_reopen_and_app_recreation(reference):
    store,client,grants=reference
    original=client.post('/api/v1/purchase-requests',headers=headers(),json=body()).json()
    reopened=ReferenceBusinessStore.open(store.path.parent)
    with TestClient(create_reference_gateway(reopened,grants)) as restarted:
        assert restarted.post('/api/v1/purchase-requests',headers=headers(),json=body()).json()==original
        assert restarted.get('/api/v1/operations/reference-operation-0001',headers=headers()).json()==original
    assert counts(reopened)==(1,1)


def test_concurrent_duplicate_requests_create_one_synthetic_purchase(reference):
    store,client,_=reference
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:client.post('/api/v1/purchase-requests',headers=headers(),json=body()),range(12)))
    assert all(r.status_code in (200,201) for r in results)
    assert sum(r.status_code==201 for r in results)==1
    assert len({r.json()['result']['external_ref'] for r in results})==1 and counts(store)==(1,1)


def test_effect_failure_rolls_back_the_authoritative_receipt(reference):
    store,client,_=reference
    with store.connect() as db:
        db.execute("CREATE TRIGGER synthetic_failure BEFORE INSERT ON synthetic_purchases BEGIN SELECT RAISE(ABORT, 'private fixture error'); END")
    response=client.post('/api/v1/purchase-requests',headers=headers(),json=body())
    assert response.status_code==503 and 'private fixture error' not in response.text
    assert counts(store)==(0,0)
    assert client.get('/api/v1/operations/reference-operation-0001',headers=headers()).status_code==404


def test_immutable_wire_arguments_are_not_silently_normalized(reference):
    store,client,_=reference
    first=client.post('/api/v1/purchase-requests',headers=headers(),json=body(amount='00001.00'))
    assert first.status_code==201 and first.json()['result']['amount']=='00001.00'
    assert client.post('/api/v1/purchase-requests',headers=headers(),json=body(amount='1.00')).status_code==409
    assert counts(store)==(1,1)


@pytest.mark.parametrize('payload',[{'unrecognized':'private-input-sentinel'},body(amount='0.00'),body(currency='EUR')])
def test_validation_errors_do_not_echo_inputs(reference,payload):
    store,client,_=reference
    response=client.post('/api/v1/purchase-requests',headers=headers(),json=payload)
    assert response.status_code==422 and 'private-input-sentinel' not in response.text
    assert 'arguments' not in response.text and counts(store)==(0,0)


def test_request_bounds_duplicate_headers_contract_and_capacity(reference,monkeypatch):
    import nexus.business_reference as module
    store,client,_=reference
    assert client.post('/api/v1/purchase-requests',headers=headers(),content=b'x'*8193).status_code==413
    duplicate=[*headers().items(),('X-Nexus-Organization','other')]
    assert client.get('/api/v1/suppliers/SUP-DEMO-104',headers=duplicate).status_code==401
    assert client.get('/api/v1/suppliers/SUP-DEMO-104',headers={**headers(),'X-Nexus-Contract':'other'}).status_code==400
    monkeypatch.setattr(module,'MAX_OPERATIONS',1)
    assert client.post('/api/v1/purchase-requests',headers=headers(),json=body()).status_code==201
    assert client.post('/api/v1/purchase-requests',headers=headers(),json=body()).status_code==200
    assert client.post('/api/v1/purchase-requests',headers=headers(operation='new-operation'),json=body(operation='new-operation')).status_code==429
    assert counts(store)==(1,1)


def test_existing_missing_or_unrelated_workspaces_and_ambiguous_credentials_are_rejected(tmp_path):
    root=tmp_path/'new';store=ReferenceBusinessStore.create(root)
    with pytest.raises(FileExistsError):ReferenceBusinessStore.create(root)
    with pytest.raises(ValueError):ReferenceBusinessStore.open(tmp_path/'missing')
    assert not (tmp_path/'missing').exists()
    other=tmp_path/'other';other.mkdir()
    db=sqlite3.connect(other/'synthetic-business.sqlite3');db.close()
    with pytest.raises(ValueError):ReferenceBusinessStore.open(other)
    grant=ReferenceCredential(TOKEN,'demo-tenant','northstar')
    with pytest.raises(ValueError):create_reference_gateway(store,(grant,replace(grant,organization_id='other')))
    with pytest.raises(ValueError):create_reference_gateway(store,(replace(grant,tenant_id=None),))
    with pytest.raises(ValueError):create_reference_gateway(store,(replace(grant,token='short'),))
    assert TOKEN not in repr(grant)


def load_example():
    source=Path(__file__).resolve().parents[2]/'scripts/run_business_reference_example.py'
    spec=importlib.util.spec_from_file_location('reference_example',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_developer_example_ignores_operator_config_and_cleans_its_workspace(tmp_path,monkeypatch,capsys):
    private=tmp_path/'operator.db';private.write_bytes(b'private sentinel')
    monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    def forbidden(*args,**kwargs):pytest.fail('Operator config or real network used')
    monkeypatch.setattr(Settings,'from_env',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    module=load_example();output=tmp_path/'reports'
    assert module.main(['--output-dir',str(output)])==0
    summary=json.loads(capsys.readouterr().out)
    report=json.loads(Path(summary['report']).read_text())
    assert report['completed'] and report['temporary_workspace_removed'] and report['synthetic_purchase_count']==1
    assert report['receipt_survived_reopen'] and report['duplicate_returned_same_receipt']
    assert not report['customer_acceptance'] and not report['production_ready']
    assert not any(text in json.dumps(report) for text in ('Authorization','Bearer','password',TOKEN))
    assert not list(output.rglob('*.sqlite3')) and private.read_bytes()==b'private sentinel'


def test_developer_example_publication_failure_cannot_report_completion(tmp_path,monkeypatch,capsys):
    module=load_example();original=Path.open
    def denied(path,*args,**kwargs):
        if path.name.startswith('business-reference-example-'):raise OSError('private publication detail')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',denied)
    output=tmp_path/'reports'
    assert module.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr()
    assert not json.loads(captured.out)['completed'] and 'private publication detail' not in captured.out+captured.err
    assert not list(output.rglob('*.sqlite3'))


def test_existing_http_adapter_works_with_reference_api_and_recovers_committed_timeout(ctx,reference,monkeypatch):
    store,gateway,_=reference
    monkeypatch.setenv('NEXUS_REFERENCE_TEST_KEY',TOKEN)
    settings=ctx['settings']
    settings.business_connector='http';settings.business_base_url='https://reference.customer.invalid/api/v1'
    settings.business_host='reference.customer.invalid';settings.business_tenant='demo-tenant'
    settings.business_token_env='NEXUS_REFERENCE_TEST_KEY'
    calls=[]
    def transport(request):
        assert request.url.host=='reference.customer.invalid' and request.url.scheme=='https'
        calls.append((request.method,request.url.path))
        response=gateway.request(request.method,request.url.path,headers=dict(request.headers),content=request.content)
        if request.method=='POST':
            assert response.status_code==201
            raise httpx.ReadTimeout('synthetic committed timeout',request=request)
        return httpx.Response(response.status_code,headers={'Content-Type':'application/json'},content=response.content)
    adapter=HTTPBusiness(settings,transport=httpx.MockTransport(transport));ctx['app'].state.connector=adapter
    submitted=submit(ctx)
    assert submitted.status_code==202 and submitted.json()['status']=='awaiting_approval'
    assert submitted.json()['envelope']['destination']==connector_identity(settings)
    assert not run_once(ctx['db'],settings,adapter) and counts(store)==(0,0)
    assert approve(ctx).status_code==200
    assert run_once(ctx['db'],settings,adapter)
    with ctx['db']() as db:assert db.get(Action,submitted.json()['id']).status=='outcome_unknown'
    assert counts(store)==(1,1) and len(calls)==1
    assert not run_once(ctx['db'],settings,adapter) and len(calls)==1
    owner,_=auth(ctx)
    recovered=ctx['client'].post('/v1/actions/'+submitted.json()['id']+'/reconcile',headers=owner)
    assert recovered.status_code==200 and recovered.json()['status']=='verified'
    assert counts(store)==(1,1) and [method for method,_ in calls]==['POST','GET']
