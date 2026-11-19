"""Allowlisted, unsigned snapshots of recorded supplier checks; no connector I/O."""
import re
from datetime import datetime, timezone
from . import __version__
from .security import digest, fail
from .service import canonical, verify


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def require(condition):
    if not condition: raise ValueError("inconsistent evidence")


def evidence(row, events, actor):
    try:
        envelope = row.envelope
        destination = envelope['destination']
        require(digest(canonical(envelope)) == row.payload_hash)
        require(all(envelope[key] == value for key, value in {
            'org_id': row.org_id, 'env': row.env, 'agent_id': row.agent_id,
            'tool_id': row.tool_id, 'policy_version': row.policy_version,
            'action': 'supplier:read', 'resource': 'suppliers'}.items()))
        require(set(envelope['arguments']) == {'supplier_id'})
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}', envelope['arguments']['supplier_id']))
        require(destination == 'mock-business-v1' or re.fullmatch(r'http-business-v1:[a-f0-9]{64}', destination))
        result = row.verification.get('result') or {}
        require(isinstance(result, dict))
        require(all(isinstance(result[key], str) for key in ('external_ref', 'state', 'supplier_id') if key in result))
        verified = row.status == 'verified'
        if verified:
            require(row.verification.get('matched') is True and verify(envelope, result))
            require(row.external_ref == result['external_ref'])
        payload = {
            'format': 'nexus-supplier-check-evidence', 'format_version': 1,
            'exported_at_utc': timestamp(datetime.now(timezone.utc).timestamp()), 'source_release': __version__,
            'scope': {'workspace_id': row.org_id, 'account_id': actor.id, 'environment': row.env},
            'check': {'id': row.id, 'status': row.status, 'reason': row.reason,
                'supplier_id': envelope['arguments']['supplier_id'], 'trace_id': row.trace_id,
                'external_ref': row.external_ref, 'attempts': row.attempts, 'verified': verified,
                'created_at_utc': timestamp(row.created), 'updated_at_utc': timestamp(row.updated)},
            'route': {'agent_id': row.agent_id, 'tool_id': row.tool_id, 'tool_version': envelope['tool_version'],
                'schema_version': envelope['schema_version'], 'agent_generation': row.generation,
                'policy_version': row.policy_version, 'policy_decision': row.decision, 'destination_binding': destination},
            'operation': {'action': 'supplier:read', 'resource': 'suppliers'},
            'connector': {'mode': 'synthetic' if destination == 'mock-business-v1' else 'http',
                'binding_source': 'recorded_action'},
            'verification': {'matched': row.verification.get('matched') is True,
                'reconciled': row.verification.get('reconciled') is True,
                'result': {key: result[key] for key in ('external_ref', 'state', 'supplier_id') if key in result}},
            'audit_events': [{'id': event.id, 'event': event.event, 'actor': event.actor,
                'created_at_utc': timestamp(event.created), 'trace_id': event.trace_id} for event in events],
            'boundary': 'Unsigned local snapshot. The checksum detects accidental changes, not authenticity. '
                'Synthetic results do not establish customer acceptance. Unverified or pending results remain unresolved. '
                'Audit details, review notes, credentials and raw connector responses are excluded.'}
    except (AssertionError, KeyError, TypeError, ValueError, OverflowError, OSError, AttributeError):
        fail(409, 'EVIDENCE_INCONSISTENT', 'Recorded supplier evidence is inconsistent; investigate the execution ledger.')
    return {'payload': payload, 'integrity': {'algorithm': 'sha256', 'canonicalization': 'sorted-ascii-json-v1',
        'digest': digest(canonical(payload)), 'authenticated_signature': False}}
