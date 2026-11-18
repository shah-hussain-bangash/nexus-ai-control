import pytest
from conftest import auth,submit

def test_runtime_signals_are_tenant_scoped_and_do_not_return_credentials(ctx):
    submit(ctx);h,_=auth(ctx);r=ctx['client'].get('/v1/runtime-operations');assert r.status_code==200
    body=r.json();assert body['actions']['awaiting_approval']==1 and body['connector']['mode']=='synthetic'
    assert body['pending_unexpired_approvals']==1 and body['schema_version']==8
    auth(ctx,org='other');assert ctx['client'].get('/v1/runtime-operations').json()['actions']=={}

def test_metrics_disabled_by_default_and_header_token_required(ctx):
    assert ctx['client'].get('/metrics').status_code==404
    ctx['settings'].metrics_token='metrics-only-unit-test-'+'x'*40
    assert ctx['client'].get('/metrics?token='+ctx['settings'].metrics_token).status_code==403
    r=ctx['client'].get('/metrics',headers={'X-Nexus-Metrics-Token':ctx['settings'].metrics_token})
    assert r.status_code==200 and 'nexus_schema_version 8' in r.text and 'nexus_actions{status="outcome_unknown"}' in r.text
    assert 'northstar' not in r.text and ctx['settings'].metrics_token not in r.text
