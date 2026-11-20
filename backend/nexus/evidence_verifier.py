"""Offline format/checksum verification. No settings, database or network imports."""
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys

MAX_BYTES = 524288
MAX_INTEGER = 9007199254740991
BOUNDARY = ('Checksum and format only. This unsigned file does not prove authenticity, '
            'current server state, customer acceptance or production readiness.')


class InvalidEvidence(ValueError):
    pass


def require(condition, message='Unsupported or inconsistent supplier evidence format.'):
    if not condition:
        raise InvalidEvidence(message)


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()))


def text(value, maximum=256, nullable=False):
    if nullable and value is None:
        return
    require(type(value) is str and 0 < len(value) <= maximum)
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value))


def integer(value, minimum=0):
    require(type(value) is int and minimum <= value <= MAX_INTEGER)


def utc(value):
    text(value, 27)
    require(bool(re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z', value)))
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    except ValueError:
        raise InvalidEvidence('Invalid evidence timestamp.') from None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON keys are not supported.')
        result[key] = value
    return result


def reject_number(value):
    raise InvalidEvidence('Only finite safe integer JSON numbers are supported.')


def safe_integer(value):
    parsed = int(value)
    require(abs(parsed) <= MAX_INTEGER, 'JSON integer exceeds the supported range.')
    return parsed


def parse_report(raw):
    require(type(raw) is bytes and len(raw) <= MAX_BYTES, 'Evidence file exceeds the 512 KiB limit.')
    try:
        decoded = raw.decode('utf-8-sig')
        depth = 0; quoted = False; escaped = False
        for char in decoded:
            if quoted:
                if escaped: escaped = False
                elif char == '\\': escaped = True
                elif char == '"': quoted = False
            elif char == '"': quoted = True
            elif char in '[{':
                depth += 1
                require(depth <= 32, 'Evidence JSON exceeds the supported nesting depth.')
            elif char in ']}': depth -= 1
        return json.loads(decoded, object_pairs_hook=unique_object,
                          parse_int=safe_integer, parse_float=reject_number, parse_constant=reject_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InvalidEvidence):
            raise
        raise InvalidEvidence('Evidence must be a supported UTF-8 JSON report.') from None


def verify_report(value, *, workspace=None, account=None, environment=None):
    fields(value, 'payload integrity')
    p, integrity = value['payload'], value['integrity']
    fields(integrity, 'algorithm canonicalization digest authenticated_signature')
    require(integrity['algorithm'] == 'sha256' and integrity['canonicalization'] == 'sorted-ascii-json-v1')
    require(integrity['authenticated_signature'] is False, 'Signed or unknown evidence formats are unsupported.')
    require(type(integrity['digest']) is str and bool(re.fullmatch('[a-f0-9]{64}', integrity['digest'])))
    fields(p, 'format format_version exported_at_utc source_release scope check route operation connector verification audit_events boundary')
    require(p['format'] == 'nexus-supplier-check-evidence' and type(p['format_version']) is int and p['format_version'] == 1)
    utc(p['exported_at_utc']); text(p['source_release'], 64); text(p['boundary'], 2000)
    scope = p['scope']; fields(scope, 'workspace_id account_id environment')
    for item in scope.values(): text(item, 100)
    require(bool(re.fullmatch('[a-z][a-z0-9-]{1,31}', scope['environment'])))
    require(all(expected is None or expected == scope[key] for key, expected in (
        ('workspace_id', workspace), ('account_id', account), ('environment', environment))),
        'Evidence does not match the expected workspace, account or environment.')
    check = p['check']
    fields(check, 'id status reason supplier_id trace_id external_ref attempts verified created_at_utc updated_at_utc')
    for key in ('id', 'status', 'reason', 'trace_id'): text(check[key], 2000 if key == 'reason' else 256)
    text(check['supplier_id'], 64)
    require(bool(re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,63}', check['supplier_id'])))
    text(check['external_ref'], 2048, nullable=True); integer(check['attempts'])
    require(type(check['verified']) is bool and check['verified'] == (check['status'] == 'verified'))
    # Wall-clock timestamps and separately evaluated database defaults need not be monotonic.
    utc(check['created_at_utc']); utc(check['updated_at_utc'])
    route = p['route']
    fields(route, 'agent_id tool_id tool_version schema_version agent_generation policy_version policy_decision destination_binding')
    for key in ('agent_id', 'tool_id'): text(route[key], 100)
    require(route['tool_version'] == '1.0' and route['schema_version'] == '1')
    integer(route['agent_generation'], 1); integer(route['policy_version'], 1)
    require(route['policy_decision'] in ('allow', 'deny', 'require_approval'))
    destination = route['destination_binding']; text(destination, 128)
    require(destination == 'mock-business-v1' or bool(re.fullmatch('http-business-v1:[a-f0-9]{64}', destination)))
    fields(p['operation'], 'action resource')
    require(p['operation'] == {'action': 'supplier:read', 'resource': 'suppliers'})
    fields(p['connector'], 'mode binding_source')
    require(p['connector'] == {'mode': 'synthetic' if destination == 'mock-business-v1' else 'http', 'binding_source': 'recorded_action'})
    verification = p['verification']; fields(verification, 'matched reconciled result')
    require(type(verification['matched']) is bool and type(verification['reconciled']) is bool)
    result = verification['result']
    require(type(result) is dict and set(result) <= {'external_ref', 'state', 'supplier_id'})
    for item in result.values(): text(item, 2048)
    require(verification['matched'] == check['verified'])
    require(not verification['reconciled'] or check['verified'])
    if check['verified']:
        require(result.get('state') == 'found' and result.get('supplier_id') == check['supplier_id'] and
                result.get('external_ref') == check['external_ref'] and bool(check['external_ref']))
    events = p['audit_events']; require(type(events) is list and len(events) <= 200)
    seen = set()
    for event in events:
        fields(event, 'id event actor created_at_utc trace_id')
        for key in ('id', 'event', 'actor'): text(event[key], 256)
        text(event['trace_id'], 256, nullable=True)
        utc(event['created_at_utc'])
        require(event['id'] not in seen)
        seen.add(event['id'])
    canonical = json.dumps(p, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    checksum = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    require(hmac.compare_digest(checksum, integrity['digest']), 'Evidence checksum does not match the payload.')
    return {'file_integrity': 'valid', 'authenticated_signature': False, 'check_id': check['id'],
            'scope': scope, 'connector_mode': p['connector']['mode'], 'status': check['status'],
            'lookup_verified': check['verified'], 'audit_event_count': len(events), 'checksum': checksum,
            'boundary': BOUNDARY}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verify a saved supplier evidence report offline; no database or network access.')
    parser.add_argument('file', help='Path to the downloaded JSON report')
    parser.add_argument('--workspace', help='Expected workspace ID (optional)')
    parser.add_argument('--account', help='Expected submitting account ID (optional)')
    parser.add_argument('--environment', help='Expected environment key (optional)')
    args = parser.parse_args(argv)
    try:
        path = Path(args.file)
        require(path.is_file(), 'Choose an existing regular evidence JSON file.')
        with path.open('rb') as source:
            value = parse_report(source.read(MAX_BYTES + 1))
        result = verify_report(value, workspace=args.workspace, account=args.account, environment=args.environment)
    except (InvalidEvidence, OSError, RecursionError) as exc:
        message = str(exc) if isinstance(exc, InvalidEvidence) else 'The evidence file could not be read.'
        print(json.dumps({'file_integrity': 'invalid', 'message': message, 'boundary': BOUNDARY}))
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
