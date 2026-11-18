"""Deterministic local reference engine, with a fail-closed OPA integration."""
from decimal import Decimal
import httpx
from .security import fail


def reference_policy(action, amount, threshold, maximum):
    if action == 'supplier:read': return {'decision': 'allow', 'reason': 'SCOPED_READ'}
    if action != 'purchase:create': return {'decision': 'deny', 'reason': 'UNKNOWN_ACTION'}
    amount, threshold, maximum = Decimal(amount), Decimal(threshold), Decimal(maximum)
    if amount > maximum: return {'decision': 'deny', 'reason': 'AMOUNT_EXCEEDS_MAXIMUM'}
    if amount > threshold: return {'decision': 'require_approval', 'reason': 'AMOUNT_REQUIRES_APPROVAL'}
    return {'decision': 'allow', 'reason': 'WITHIN_GRANTED_LIMIT'}


def evaluate(settings, action, arguments, policy):
    if settings.policy_mode == 'reference':
        return reference_policy(action, arguments.get('amount', '0'), policy.threshold, policy.maximum)
    try:
        with httpx.Client(timeout=3) as client:
            response = client.post(settings.opa_url, json={'input': {'action': action,
                'amount_cents': int(Decimal(arguments.get('amount', '0')) * 100),
                'threshold_cents': int(Decimal(policy.threshold) * 100),
                'maximum_cents': int(Decimal(policy.maximum) * 100), 'policy_version': policy.version}})
            response.raise_for_status(); result = response.json()['result']
        if result['decision'] not in ('allow', 'deny', 'require_approval') or not isinstance(result['reason'], str):
            raise ValueError('Invalid decision')
        return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ImportError):
        fail(503, 'CONTROL_UNAVAILABLE', 'Policy evaluation unavailable. No tool was called.')
