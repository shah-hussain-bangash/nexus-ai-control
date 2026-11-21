"""Input rules must never be silently truncated before provider admission."""
import httpx
import pytest
from sqlalchemy import select, func
from nexus.db import WorkspaceAsset, InferenceCall, InferenceBudget
from test_inference import setup


def rules(ctx,count,*,org='northstar',environment='staging',status='draft',blocked_last=False):
    with ctx['db'].begin() as db:
        for index in range(count):
            db.add(WorkspaceAsset(id=f'capacity-{org}-{environment}-{status}-{index:03}',org_id=org,env=environment,
                kind='guardrail',name='Private synthetic rule '+str(index),author_id='test',status=status,
                config={'blocked_terms':['Synthetic question'] if blocked_last and index==count-1 else [],
                        'detect_email':False,'detect_override':False,'mode':'block'}))


@pytest.mark.parametrize('count',[99,100])
def test_every_rule_up_to_capacity_is_enforced(ctx,monkeypatch,count):
    headers,body,sent=setup(ctx,monkeypatch)
    rules(ctx,count,blocked_last=True)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==422 and response.json()['error']['code']=='GUARDRAIL_BLOCKED'
    assert not sent
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(InferenceCall))==0
        assert db.scalar(select(func.count()).select_from(InferenceBudget))==0


def test_surplus_blocking_rule_cannot_be_silently_skipped(ctx,monkeypatch):
    headers,body,sent=setup(ctx,monkeypatch)
    rules(ctx,101,blocked_last=True)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==422,response.text
    assert response.json()['error']['code']=='GUARDRAIL_LIMIT_EXCEEDED'
    assert 'Private synthetic rule' not in response.text and 'Synthetic question' not in response.text
    assert not sent
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(InferenceCall))==0
        assert db.scalar(select(func.count()).select_from(InferenceBudget))==0


def test_archiving_surplus_allows_same_intent_without_prior_reservation(ctx,monkeypatch):
    headers,body,sent=setup(ctx,monkeypatch)
    rules(ctx,101)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==422 and not sent
    # Use the supported owner operation, preserving its version check and history.
    archived=ctx['client'].post('/v1/workbench/capacity-northstar-staging-draft-100/archive',
        headers=headers,json={'expected_version':1})
    assert archived.status_code==200,archived.text
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==200 and response.json()['status']=='completed' and len(sent)==1
    assert ctx['client'].post('/v1/inference',headers=headers,json=body).json()['id']==response.json()['id']
    assert len(sent)==1
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(InferenceCall))==1
        budget=db.scalar(select(InferenceBudget));assert budget.held==0 and budget.spent==24


@pytest.mark.parametrize('scope',['archived','other_workspace','other_environment'])
def test_rules_outside_active_context_do_not_consume_capacity(ctx,monkeypatch,scope):
    headers,body,sent=setup(ctx,monkeypatch)
    rules(ctx,100)
    rules(ctx,101,org='other' if scope=='other_workspace' else 'northstar',
        environment='production' if scope=='other_environment' else 'staging',
        status='archived' if scope=='archived' else 'draft',blocked_last=True)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed' and len(sent)==1


def test_capacity_rejection_preserves_existing_unknown_accounting_and_recovery(ctx,monkeypatch):
    headers,body,sent=setup(ctx,monkeypatch,lambda request:httpx.Response(500))
    first=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert first.status_code==200 and first.json()['status']=='unknown'
    before=ctx['client'].get('/v1/runtime').json()
    rules(ctx,101)
    rejected=ctx['client'].post('/v1/inference',headers={**headers,'Idempotency-Key':'capacity-new-intent-0001'},json=body)
    assert rejected.status_code==422 and rejected.json()['error']['code']=='GUARDRAIL_LIMIT_EXCEEDED'
    replay=ctx['client'].post('/v1/inference',headers=headers,json=body)
    recovered=ctx['client'].post('/v1/inference/recover',headers=headers,json={'key':headers['Idempotency-Key']})
    assert replay.status_code==recovered.status_code==200
    assert replay.json()['id']==recovered.json()['id']==first.json()['id'] and len(sent)==1
    after=ctx['client'].get('/v1/runtime').json()
    assert after['held_micro_usd']==before['held_micro_usd']>0 and after['spent_micro_usd']==before['spent_micro_usd']==0
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(InferenceCall))==1
