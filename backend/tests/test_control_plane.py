import pytest
import jwt
from sqlalchemy import select
from conftest import auth, identifiers, submit, approve
from nexus.db import Agent, Action, Approval, Policy, User, Export, now
from nexus.security import workload_token
from nexus.worker import run_once
from nexus.service import canonical
from nexus.config import Settings


def work(ctx): return run_once(ctx['db'], ctx['settings'], ctx['connector'])


def test_login_and_logout(ctx):
    c = ctx['client']
    assert c.get('/v1/me').status_code == 401
    r = c.post('/auth/local/login', json={'email': 'owner@nexus.local', 'password': 'Test-Only-Password-123!'})
    assert r.status_code == 200
    assert c.get('/v1/me').json()['user']['role'] == 'owner'
    assert c.post('/auth/logout', headers={'X-CSRF-Token': r.json()['csrf']}).status_code == 200
    assert c.get('/v1/me').status_code == 401


def test_bad_login_is_generic(ctx):
    for email in ['owner@nexus.local', 'absent@nexus.local']:
        r = ctx['client'].post('/auth/local/login', json={'email': email, 'password': 'wrong'})
        assert r.status_code == 401 and r.json()['error']['code'] == 'INVALID_CREDENTIALS'


def test_login_rate_limit(ctx):
    c = ctx['client']
    for _ in range(8): c.post('/auth/local/login', json={'email': 'missing@test.invalid', 'password': 'wrong'})
    assert c.post('/auth/local/login', json={'email': 'missing@test.invalid', 'password': 'wrong'}).status_code == 429


def test_local_login_rejects_foreign_origin(ctx):
    assert ctx['client'].post('/auth/local/login', json={'email': 'owner@nexus.local', 'password': 'Test-Only-Password-123!'}, headers={'Origin': 'https://evil.invalid'}).status_code == 403


def test_csrf_required(ctx):
    auth(ctx)
    assert ctx['client'].post('/v1/agents', json={'name': 'Bad CSRF'}).status_code == 403


def test_auditor_cannot_register_or_approve(ctx):
    headers, _ = auth(ctx, 'auditor')
    assert ctx['client'].post('/v1/agents', json={'name': 'Forbidden agent'}, headers=headers).status_code == 403


def test_membership_revocation_invalidates_session(ctx):
    _, user = auth(ctx)
    with ctx['db'].begin() as db: db.get(User, user).active = 0
    assert ctx['client'].get('/v1/me').status_code == 401


def test_cross_tenant_object_and_lists(ctx):
    a, _ = identifiers(ctx)
    auth(ctx, org='other')
    assert ctx['client'].get('/v1/agents/' + a).status_code == 404
    assert ctx['client'].get('/v1/agents').json() == []
    assert ctx['client'].get('/v1/actions').json() == []


def test_caller_cannot_supply_org_context(ctx):
    headers, _ = auth(ctx)
    assert ctx['client'].post('/v1/agents', json={'name': 'Spoof', 'org_id': 'other'}, headers=headers).status_code == 422


def test_registry_draft_has_no_implicit_grants(ctx):
    headers, _ = auth(ctx)
    r = ctx['client'].post('/v1/agents', json={'name': 'Fresh agent'}, headers=headers)
    assert r.status_code == 201 and r.json()['status'] == 'draft'
    row = ctx['client'].get('/v1/agents/' + r.json()['id']).json()
    assert row['grants'] == []
    assert ctx['client'].post('/v1/agents/' + row['id'] + '/lifecycle/activate', json={'reason': 'Try activation'}, headers=headers).status_code == 409


@pytest.mark.parametrize('amount,decision,status', [('5000.00','allow','queued'),('5000.01','require_approval','awaiting_approval'),('25000.00','require_approval','awaiting_approval'),('25000.01','deny','denied')])
def test_policy_boundaries(ctx, amount, decision, status):
    r = submit(ctx, amount=amount)
    assert r.status_code == 202 and r.json()['decision'] == decision and r.json()['status'] == status
    assert ctx['connector'].count() == 0


def test_read_scope_succeeds_and_is_verified(ctx):
    r = submit(ctx, kind='supplier', name='Supplier Scout'); assert r.status_code == 202
    assert work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'verified'
    assert ctx['connector'].count() == 1


def test_missing_grant_denies_without_side_effect(ctx):
    r = submit(ctx, name='Supplier Scout')
    assert r.json()['reason'] == 'TOOL_GRANT_MISSING' and r.json()['status'] == 'denied'
    assert not work(ctx); assert ctx['connector'].count() == 0


def test_approval_executes_exact_payload(ctx):
    r = submit(ctx); action_id = r.json()['id']
    assert not work(ctx) and ctx['connector'].count() == 0
    assert approve(ctx).status_code == 200
    assert work(ctx)
    result = ctx['connector'].lookup(action_id)
    assert result['amount'] == '12500.00' and result['supplier_id'] == 'SUP-DEMO-104'
    assert not work(ctx) and ctx['connector'].count() == 1


def test_self_review_rejected_even_with_approver_role(ctx):
    submit(ctx)
    with ctx['db'].begin() as db: db.scalar(select(User).where(User.email == 'owner@nexus.local')).role = 'approver'
    headers, _ = auth(ctx, 'approver')
    row = ctx['client'].get('/v1/approvals').json()[0]
    r = ctx['client'].post('/v1/approvals/' + row['id'] + '/decision', headers=headers, json={
        'decision': 'approve', 'expected_version': 1, 'request_hash': row['payload_hash'], 'comment': 'Attempting self approval'})
    assert r.status_code == 403 and r.json()['error']['code'] == 'SELF_APPROVAL'


def test_payload_hash_substitution_rejected(ctx):
    submit(ctx)
    assert approve(ctx, {'request_hash': '0' * 64}).status_code == 409
    assert ctx['connector'].count() == 0


def test_changed_stored_payload_cannot_dispatch(ctx):
    r = submit(ctx); assert approve(ctx).status_code == 200
    with ctx['db'].begin() as db:
        a = db.get(Action, r.json()['id']); env = dict(a.envelope); env['arguments'] = {**env['arguments'], 'amount': '1.00'}; a.envelope = env
    work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'blocked'
    assert ctx['connector'].count() == 0


def test_expired_approval_never_dispatches(ctx):
    submit(ctx)
    with ctx['db'].begin() as db: db.scalar(select(Approval)).expires = now() - 1
    assert approve(ctx).status_code == 409
    assert ctx['connector'].count() == 0


def test_approval_expiring_after_review_blocks_worker(ctx):
    r = submit(ctx); approve(ctx)
    with ctx['db'].begin() as db: db.scalar(select(Approval)).expires = now() - 1
    work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'blocked'
    assert ctx['connector'].count() == 0


def test_double_approval_has_one_winner(ctx):
    submit(ctx); assert approve(ctx).status_code == 200
    assert approve(ctx, {'expected_version': 1}).status_code == 409
    work(ctx); assert ctx['connector'].count() == 1


def test_rejection_has_no_execution(ctx):
    submit(ctx); assert approve(ctx, {'decision': 'reject'}).status_code == 200
    assert not work(ctx) and ctx['connector'].count() == 0


def test_same_idempotency_key_deduplicates(ctx):
    a, b = submit(ctx, amount='3000.00'), submit(ctx, amount='3000.00')
    assert a.json()['id'] == b.json()['id']
    work(ctx); assert ctx['connector'].count() == 1


def test_changed_payload_with_same_key_conflicts(ctx):
    submit(ctx, amount='3000.00')
    assert submit(ctx, amount='4000.00').status_code == 409


def test_suspension_blocks_queued_work(ctx):
    r = submit(ctx, amount='3000.00'); headers, _ = auth(ctx)
    a, _ = identifiers(ctx)
    assert ctx['client'].post('/v1/agents/' + a + '/lifecycle/suspend', json={'reason': 'Security containment test'}, headers=headers).status_code == 200
    work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'blocked'
    assert ctx['connector'].count() == 0


def test_revoked_grant_blocks_queued_work(ctx):
    r = submit(ctx, amount='3000.00'); headers, _ = auth(ctx); a, t = identifiers(ctx)
    row = ctx['client'].get('/v1/agents/' + a).json()
    grant = next(g for g in row['grants'] if g['tool_id'] == t)
    assert ctx['client'].delete('/v1/agents/' + a + '/tool-grants/' + grant['id'], headers=headers).status_code == 200
    work(ctx); assert ctx['connector'].count() == 0


def test_unknown_after_commit_reconciles_without_duplicate(ctx):
    r = submit(ctx, amount='3000.00', simulation='timeout_after_commit'); work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'outcome_unknown'
    assert ctx['connector'].count() == 1 and not work(ctx)
    headers, _ = auth(ctx)
    result = ctx['client'].post('/v1/actions/' + r.json()['id'] + '/reconcile', headers=headers)
    assert result.status_code == 200 and result.json()['status'] == 'verified'
    assert ctx['connector'].count() == 1


def test_confirmed_no_commit_failure(ctx):
    r = submit(ctx, amount='3000.00', simulation='fail_before_commit'); work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'failed'
    assert ctx['connector'].count() == 0


def test_mismatched_result_is_not_verified(ctx):
    r = submit(ctx, amount='3000.00', simulation='mismatch'); work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'failed'


def test_worker_crash_lease_is_not_replayed(ctx):
    r = submit(ctx, amount='3000.00')
    with ctx['db'].begin() as db:
        a = db.get(Action, r.json()['id']); a.status='executing'; a.lease_until=now()-1
    assert not work(ctx)
    with ctx['db']() as db: assert db.get(Action, r.json()['id']).status == 'outcome_unknown'
    assert ctx['connector'].count() == 0


def test_policy_change_invalidates_old_request(ctx):
    r = submit(ctx); headers, _ = auth(ctx)
    response=ctx['client'].post('/v1/policies/activate', json={'expected_version': 1, 'threshold': '6000.00', 'maximum': '30000.00', 'reason': 'New policy boundary test'}, headers=headers)
    assert response.status_code == 200 and response.json()['version'] == 2
    assert approve(ctx).status_code == 409
    assert ctx['connector'].count() == 0


def test_opa_outage_fails_closed(ctx):
    ctx['settings'].policy_mode = 'opa'; ctx['settings'].opa_url='http://127.0.0.1:9/v1/data/nexus/decision'
    assert submit(ctx).status_code == 503
    assert ctx['connector'].count() == 0


@pytest.mark.parametrize('changed', [{'aud': 'wrong-audience'}, {'iss': 'wrong-issuer'}, {'exp': 1}, {'org': 'other'}, {'env': 'production'}])
def test_invalid_agent_claims_denied(ctx, changed):
    a, t = identifiers(ctx)
    with ctx['db']() as db: agent = db.get(Agent, a); token = workload_token(agent, ctx['settings'])
    claims = jwt.decode(token, ctx['settings'].agent_secret, algorithms=['HS256'], options={'verify_aud': False}); claims.update(changed)
    token = jwt.encode(claims, ctx['settings'].agent_secret, algorithm='HS256')
    r=ctx['client'].post('/v1/gateway/tools/'+t+':execute', headers={'Authorization':'Bearer '+token,'Idempotency-Key':'workload-test-0001'}, json={'action':'purchase:create','resource':'purchase_requests','arguments':{'supplier_id':'SUP-DEMO-104','amount':'3000.00','currency':'USD','purpose':'Claim test'}})
    assert r.status_code in (401,403) and ctx['connector'].count()==0


def test_workload_exchange_and_gateway(ctx):
    a, t = identifiers(ctx); headers, _ = auth(ctx)
    rotated=ctx['client'].post('/v1/agents/'+a+'/lifecycle/rotate', headers=headers,json={'reason':'Issue SDK credential'}).json()
    r=ctx['client'].post('/v1/workload/token/'+a,headers={'Authorization':'Bearer '+rotated['credential']})
    assert r.status_code==200
    r=ctx['client'].post('/v1/gateway/tools/'+t+':execute',headers={'Authorization':'Bearer '+r.json()['access_token'],'Idempotency-Key':'sdk-action-test-0001'},json={'action':'purchase:create','resource':'purchase_requests','arguments':{'supplier_id':'SUP-DEMO-104','amount':'3000.00','currency':'USD','purpose':'SDK request'}})
    assert r.status_code==202;work(ctx);assert ctx['connector'].count()==1
    assert 'credential_hash' not in ctx['client'].get('/v1/agents/'+a).json()


def test_export_scope_permissions_and_expiry(ctx):
    submit(ctx); headers, _ = auth(ctx,'auditor'); r=ctx['client'].post('/v1/audit-exports',headers=headers)
    assert r.status_code==201
    url=r.json()['url']; assert ctx['client'].get(url).status_code==200
    auth(ctx,org='other'); assert ctx['client'].get(url).status_code==404
    auth(ctx,'auditor')
    with ctx['db'].begin() as db: db.get(Export,r.json()['id']).expires=now()-1
    assert ctx['client'].get(url).status_code==404


def test_runtime_evaluation_has_actual_observations(ctx):
    headers,_=auth(ctx);r=ctx['client'].post('/v1/evaluations',headers=headers)
    assert r.status_code==201 and r.json()['passed']==5 and all(c['actual']==c['expected'] for c in r.json()['cases'])


def test_containment_revokes_credentials_and_grants(ctx):
    headers,_=auth(ctx);a,_=identifiers(ctx)
    r=ctx['client'].post('/v1/agents/'+a+'/contain',json={'reason':'Synthetic incident containment'},headers=headers)
    assert r.status_code==201
    detail=ctx['client'].get('/v1/agents/'+a).json()
    assert detail['status']=='suspended' and detail['grants']==[]


def test_audit_correlates_decision_approval_and_execution(ctx):
    r=submit(ctx);approve(ctx);work(ctx);auth(ctx)
    detail=ctx['client'].get('/v1/actions/'+r.json()['id']).json()
    events={e['event'] for e in detail['events']}
    assert {'policy.require_approval','approval.required','approval.approved','execution.started','execution.verified'}<=events
    assert all(e['trace_id']==detail['trace_id'] for e in detail['events'])


def test_invalid_decimals_and_unknown_fields_rejected(ctx):
    assert submit(ctx,amount='12.345').status_code==422
    assert submit(ctx,amount='-2.00').status_code==422


def test_canonical_key_order_is_stable():
    assert canonical({'a':1,'b':2})==canonical({'b':2,'a':1})


def test_insecure_pilot_config_refuses_start():
    with pytest.raises(RuntimeError): Settings(secret='x'*48,agent_secret='y'*48,mode='pilot').validate()


def test_parallel_approval_compare_and_set(ctx):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from nexus.security import issue_session
    submit(ctx)
    with ctx['db'].begin() as db:
        reviewer=db.scalar(select(User).where(User.role=='approver'))
        token,csrf=issue_session(db,reviewer,ctx['settings'])
        row=db.scalar(select(Approval))
        target=row.id; fingerprint=row.payload_hash
    def decide_once(_):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',token)
            return client.post('/v1/approvals/'+target+'/decision',headers={'X-CSRF-Token':csrf},json={
                'decision':'approve','expected_version':1,'request_hash':fingerprint,'comment':'Independent parallel approval test'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: statuses=list(pool.map(decide_once,range(2)))
    assert sorted(statuses)==[200,409]
    work(ctx);assert ctx['connector'].count()==1


def test_workload_signature_tampering_denied(ctx):
    a,t=identifiers(ctx)
    with ctx['db']() as db:token=workload_token(db.get(Agent,a),ctx['settings'])
    parts=token.split('.');parts[2]=('a' if parts[2][0]!='a' else 'b')+parts[2][1:]
    r=ctx['client'].post('/v1/gateway/tools/'+t+':execute',headers={'Authorization':'Bearer '+'.'.join(parts),'Idempotency-Key':'tampered-token-0001'},json={'action':'purchase:create','resource':'purchase_requests','arguments':{'supplier_id':'SUP-DEMO-104','amount':'3000.00','currency':'USD','purpose':'Signature test'}})
    assert r.status_code==401 and ctx['connector'].count()==0


def test_workload_can_only_poll_its_own_intents(ctx):
    r=submit(ctx,amount='3000.00');a,_=identifiers(ctx)
    with ctx['db']() as db:
        owner_token=workload_token(db.get(Agent,a),ctx['settings'])
        scout=db.scalar(select(Agent).where(Agent.name=='Supplier Scout'))
        other_token=workload_token(scout,ctx['settings'])
    url='/v1/gateway/actions/'+r.json()['id']
    assert ctx['client'].get(url,headers={'Authorization':'Bearer '+owner_token}).status_code==200
    assert ctx['client'].get(url,headers={'Authorization':'Bearer '+other_token}).status_code==404


def test_oidc_invalid_callback_rejected(ctx):
    assert ctx['client'].get('/auth/oidc/callback?state=invalid&code=invalid').status_code==401


def test_policy_activation_outage_keeps_previous_active(ctx):
    headers,_=auth(ctx)
    ctx['settings'].policy_mode='opa';ctx['settings'].opa_url='http://127.0.0.1:9/v1/data/nexus/decision'
    r=ctx['client'].post('/v1/policies/activate',headers=headers,json={'expected_version':1,'threshold':'6000.00','maximum':'30000.00','reason':'Outage activation guard'})
    assert r.status_code==503
    with ctx['db']() as db:
        assert db.scalar(select(Policy).where(Policy.org_id=='northstar',Policy.active==1)).version==1
