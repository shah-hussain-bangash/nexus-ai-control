import json
from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from .db import Agent, Tool, Grant, Policy, Action, Approval, Audit, now, uid
from .schemas import PurchaseArguments, SupplierArguments
from .security import fail, digest
from .policy import evaluate
from .business_connector import connector_identity


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def audit(db, org, actor, event, action=None, detail=None, env='staging'):
    db.add(Audit(org_id=org, env=action.env if action else env, actor=actor, event=event, action_id=action.id if action else None,
                 trace_id=action.trace_id if action else None, detail=detail or {}))


def scoped(db, model, id, org):
    query = select(model).where(model.id == id, model.org_id == org, model.env == 'staging')
    if model is Agent: query = query.with_for_update()
    value = db.scalar(query)
    if not value: fail(404, 'NOT_FOUND', 'Record not found in this workspace.')
    return value


def active_policy(db, org):
    policy = db.scalar(select(Policy).where(Policy.org_id == org, Policy.env == 'staging', Policy.active == 1).with_for_update())
    if not policy: fail(503, 'CONTROL_UNAVAILABLE', 'No active policy. No tool was called.')
    return policy


def submit_action(db, settings, agent, tool, body, key, principal, requester):
    agent = db.scalar(select(Agent).where(Agent.id == agent.id).with_for_update().execution_options(populate_existing=True))
    if len(key) < 8 or len(key) > 128: fail(422, 'INVALID_KEY', 'Use an 8-128 character idempotency key.')
    request_digest = digest(canonical({'agent': agent.id, 'tool': tool.id, **body.model_dump()}))
    previous = db.scalar(select(Action).where(Action.org_id == agent.org_id, Action.env == agent.env,
                                            Action.principal == principal, Action.idem_key == key))
    if previous:
        if previous.request_digest != request_digest: fail(409, 'IDEMPOTENCY_CONFLICT', 'This key belongs to a different immutable request.')
        return previous
    if agent.status != 'active': fail(403, 'AGENT_INACTIVE', 'Activate the agent before requesting an action.')
    if tool.status != 'validated' or tool.org_id != agent.org_id or tool.env != agent.env or body.tool_version != tool.version:
        fail(422, 'INVALID_TOOL', 'Tool is unavailable or its version does not match.')
    expected = 'supplier:read' if tool.kind == 'supplier' else 'purchase:create'
    expected_resource = 'suppliers' if tool.kind == 'supplier' else 'purchase_requests'
    if body.action != expected or body.resource != expected_resource:
        fail(422, 'INVALID_ACTION', 'Action/resource does not match the registered tool.')
    try:
        args = (SupplierArguments if tool.kind == 'supplier' else PurchaseArguments).model_validate(body.arguments).model_dump()
    except ValidationError: fail(422, 'INVALID_ARGUMENTS', 'Tool arguments do not match the registered schema.')
    if (settings.mode != 'local' or settings.business_connector=='http') and body.simulation != 'normal': fail(403, 'SIMULATION_DISABLED', 'Fault injection is local-only.')
    policy = active_policy(db, agent.org_id)
    grant = db.scalar(select(Grant).where(Grant.org_id == agent.org_id, Grant.env == agent.env,
                     Grant.agent_id == agent.id, Grant.tool_id == tool.id, Grant.scope == body.action))
    result = evaluate(settings, body.action, args, policy) if grant else {'decision': 'deny', 'reason': 'TOOL_GRANT_MISSING'}
    envelope = {'org_id': agent.org_id, 'env': agent.env, 'agent_id': agent.id, 'tool_id': tool.id,
                'tool_version': tool.version, 'schema_version': body.schema_version, 'destination': connector_identity(settings),
                'action': body.action, 'resource': body.resource, 'arguments': args,
                'policy_version': policy.version, 'simulation': body.simulation}
    status = {'allow': 'queued', 'deny': 'denied', 'require_approval': 'awaiting_approval'}[result['decision']]
    action = Action(id=uid(), org_id=agent.org_id, env=agent.env, agent_id=agent.id, tool_id=tool.id,
                    requester_id=requester, principal=principal, idem_key=key, request_digest=request_digest,
                    envelope=envelope, payload_hash=digest(canonical(envelope)), policy_version=policy.version,
                    generation=agent.generation, decision=result['decision'], reason=result['reason'], status=status,
                    trace_id=uid())
    db.add(action); db.flush()
    audit(db, agent.org_id, principal, 'policy.' + result['decision'], action, {'reason': action.reason, 'policy_version': policy.version})
    if status == 'awaiting_approval':
        db.add(Approval(org_id=agent.org_id, env=agent.env, action_id=action.id, payload_hash=action.payload_hash,
                        requester_id=requester, policy_version=policy.version, expires=now() + 1800))
        audit(db, agent.org_id, principal, 'approval.required', action)
    # Queued action rows form the persisted transactional outbox (not an in-memory queue).
    return action


def decide(db, user, approval, decision):
    action = scoped(db, Action, approval.action_id, user.org_id)
    if approval.requester_id == user.id: fail(403, 'SELF_APPROVAL', 'A different authorized reviewer must decide this action.')
    if approval.expires <= now(): fail(409, 'APPROVAL_EXPIRED', 'Approval expired. Submit a new action.')
    policy = active_policy(db, user.org_id)
    if policy.version != approval.policy_version: fail(409, 'POLICY_CHANGED', 'Policy changed. Submit a new action for review.')
    if decision.request_hash != approval.payload_hash or digest(canonical(action.envelope)) != approval.payload_hash:
        fail(409, 'PAYLOAD_CHANGED', 'Action fingerprint does not match the reviewed request.')
    status = {'approve': 'approved', 'reject': 'rejected', 'request_changes': 'changes_requested'}[decision.decision]
    changed = db.execute(update(Approval).where(Approval.id == approval.id, Approval.org_id == user.org_id,
                  Approval.status == 'pending', Approval.version == decision.expected_version).values(
                  status=status, version=Approval.version + 1, approver_id=user.id, comment=decision.comment))
    if changed.rowcount != 1: fail(409, 'STALE_VERSION', 'This request was already decided or changed. Refresh to review.')
    action.status = 'queued' if status == 'approved' else status; action.updated = now()
    audit(db, user.org_id, user.id, 'approval.' + status, action, {'comment': decision.comment})
    return action


def verify(envelope, result):
    if not result or not result.get('external_ref'): return False
    args = envelope['arguments']
    return result.get('state') == ('created' if envelope['action']=='purchase:create' else 'found') and all(result.get(k) == args[k] for k in ('supplier_id', 'amount', 'currency', 'purpose') if k in args)
