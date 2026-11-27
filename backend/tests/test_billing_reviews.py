"""Owner statement comparison with synthetic inference transport and untouched ledgers."""
import pytest
from sqlalchemy import select,func
from conftest import auth
from test_inference import setup
from nexus.db import InferenceCall,InferenceBudget,WorkbenchRun


def call(ctx,monkeypatch,unknown=False):
    import httpx
    headers,body,sent=setup(ctx,monkeypatch,handler=(lambda _:httpx.Response(503,json={})) if unknown else None)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body);assert response.status_code==200,response.text
    return response.json(),sent


def payload(row,**changes):
    return {'statement_ref':'Synthetic statement 001','period':row['period'],'currency':'USD','note':'Manually checked synthetic statement charge.',
        'lines':[{'line_ref':'line-1','call_id':row['id'],'billed_micro_usd':24,'input_tokens':12,'output_tokens':4,'provider_request_id':'provider-test'}],**changes}


def submit(ctx,body,key='billing-review-intent-001',role='owner'):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/billing-reviews',headers=headers,json=body)


def ledger(ctx):
    with ctx['db']() as db:
        return [(r.id,r.held,r.spent) for r in db.scalars(select(InferenceBudget).order_by(InferenceBudget.id))]


def test_matching_fields_snapshot_and_recovery_never_contact_provider_or_adjust_ledger(ctx,monkeypatch):
    row,sent=call(ctx,monkeypatch);before=ledger(ctx)
    response=submit(ctx,payload(row));assert response.status_code==201,response.text
    value=response.json();assert value['status']=='matched' and not value['stale'] and value['provider_calls']==0 and not value['ledger_adjusted']
    assert value['settled_amount_delta_micro_usd']==0 and value['matched_lines']==1
    assert value['items'][0]['checked_fields']==['amount','input_tokens','output_tokens','provider_request_id']
    assert 'Synthetic verified transport answer' not in str(value) and 'test-transport-only' not in str(value)
    assert submit(ctx,payload(row)).json()['id']==value['id'] and len(sent)==1 and ledger(ctx)==before
    headers,_=auth(ctx)
    assert ctx['client'].post('/v1/billing-reviews/recover',headers=headers,json={'key':'billing-review-intent-001'}).json()['id']==value['id']
    assert value['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


def test_discrepancy_sign_and_optional_coverage_are_explicit(ctx,monkeypatch):
    row,sent=call(ctx,monkeypatch);line={'line_ref':'line-1','call_id':row['id'],'billed_micro_usd':30}
    value=submit(ctx,payload(row,lines=[line])).json()
    assert value['status']=='review_required' and value['discrepancy_lines']==1 and value['settled_amount_delta_micro_usd']==6
    assert value['items'][0]['checked_fields']==['amount'] and value['items'][0]['input_token_delta'] is None
    line={**line,'billed_micro_usd':24,'input_tokens':13,'provider_request_id':'different-request'}
    value=submit(ctx,payload(row,lines=[line]),key='billing-second-review-001').json()
    assert value['items'][0]['input_token_delta']==1 and value['items'][0]['provider_request_id_match'] is False
    assert value['items'][0]['amount_delta_micro_usd']==0 and value['discrepancy_lines']==1


def test_unknown_calls_are_not_zero_cost_matches_and_reservations_stay_held(ctx,monkeypatch):
    row,sent=call(ctx,monkeypatch,unknown=True);before=ledger(ctx)
    value=submit(ctx,payload(row,lines=[{'line_ref':'unresolved-1','call_id':row['id'],'billed_micro_usd':0}])).json()
    assert value['status']=='review_required' and value['unresolved_lines']==1 and value['items'][0]['status']=='unresolved'
    assert value['items'][0]['amount_delta_micro_usd'] is None and value['items'][0]['local']['charged_micro_usd'] is None
    assert before==ledger(ctx) and before[0][1]>0 and len(sent)==1


def test_saved_report_remains_historical_when_local_usage_is_reconciled(ctx,monkeypatch):
    row,sent=call(ctx,monkeypatch,unknown=True);body=payload(row);value=submit(ctx,body).json();headers,_=auth(ctx)
    response=ctx['client'].post('/v1/inference/'+row['id']+'/reconcile',headers=headers,json={'input_tokens':12,'output_tokens':4,'note':'Reviewed synthetic provider accounting evidence.'})
    assert response.status_code==200,response.text
    auth(ctx);current=ctx['client'].get('/v1/billing-reviews/'+value['id']).json()
    assert current['stale'] and current['unresolved_lines']==1 and submit(ctx,body).json()['id']==value['id']
    fresh=submit(ctx,body,key='billing-refreshed-intent-001').json();assert not fresh['stale'] and fresh['status']=='review_required'
    # Reconciled usage has no provider request ID; the supplied ID remains unverified.
    assert fresh['items'][0]['provider_request_id_match'] is False and len(sent)==1


@pytest.mark.parametrize('changes',[{'currency':'EUR'},{'period':'2026-13'},{'lines':[]},{'note':'          '}])
def test_invalid_statement_shapes_fail_before_creating_receipt(ctx,monkeypatch,changes):
    row,sent=call(ctx,monkeypatch)
    assert submit(ctx,payload(row,**changes)).status_code==422


@pytest.mark.parametrize('amount',[-1,True,1.5,1000000000001])
def test_micro_usd_amounts_are_strict_bounded_integers(ctx,monkeypatch,amount):
    row,sent=call(ctx,monkeypatch);body=payload(row);body['lines'][0]['billed_micro_usd']=amount
    assert submit(ctx,body).status_code==422


def test_duplicates_cross_scope_month_and_permission_boundaries(ctx,monkeypatch):
    row,sent=call(ctx,monkeypatch);body=payload(row)
    assert submit(ctx,{**body,'lines':body['lines']*2}).status_code==422
    assert submit(ctx,{**body,'period':'2000-01'}).status_code==404
    assert submit(ctx,body,role='auditor').status_code==403
    value=submit(ctx,body).json()
    auth(ctx,'auditor');assert ctx['client'].get('/v1/billing-reviews/'+value['id']).status_code==200
    auth(ctx,'approver');assert ctx['client'].get('/v1/billing-reviews').status_code==403
    headers,_=auth(ctx,org='other');headers['Idempotency-Key']='cross-scope-statement-001'
    assert ctx['client'].post('/v1/billing-reviews',headers=headers,json=body).status_code==404
    assert ctx['client'].get('/v1/billing-reviews/'+value['id']).status_code==404
    assert ctx['client'].get('/v1/billing-reviews').json()['items']==[]


def test_changed_payload_conflicts_and_capacity_is_bounded(ctx,monkeypatch):
    row,sent=call(ctx,monkeypatch);body=payload(row);value=submit(ctx,body).json()
    assert submit(ctx,{**body,'statement_ref':'Changed reference'}).status_code==409
    with ctx['db'].begin() as db:
        old=db.get(WorkbenchRun,value['id'])
        for _ in range(199):db.add(WorkbenchRun(org_id=old.org_id,env=old.env,author_id=old.author_id,kind=old.kind,status=old.status,duration_ms=0,result=old.result))
    assert submit(ctx,body,key='over-capacity-statement-001').status_code==429 and len(sent)==1


def test_same_workspace_other_environment_cannot_read_or_reference_calls(ctx,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nexus.db import User
    from nexus.runtime_context import bind_runtime_context
    from nexus.billing_reviews import register_billing_reviews
    row,sent=call(ctx,monkeypatch);body=payload(row);saved=submit(ctx,body).json();_,owner=auth(ctx)
    selected={'env':'production'}
    def human(request,db,*args,**kwargs):
        user=db.get(User,owner);bind_runtime_context(db,user.org_id,selected['env']);return user
    app=FastAPI();register_billing_reviews(app,ctx['db'],human)
    before=ledger(ctx)
    with TestClient(app) as client:
        assert client.get('/v1/billing-reviews').json()['items']==[]
        assert client.get('/v1/billing-reviews/'+saved['id']).status_code==404
        assert client.post('/v1/billing-reviews',headers={'Idempotency-Key':'other-env-billing-review'},json=body).status_code==404
        selected['env']='staging'
        assert client.get('/v1/billing-reviews/'+saved['id']).json()['status']=='matched'
    assert ledger(ctx)==before and len(sent)==1
