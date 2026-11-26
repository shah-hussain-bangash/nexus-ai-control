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


def require(condition, message='Unsupported or inconsistent evidence format.'):
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


def verify_scope(scope, workspace, account, environment):
    fields(scope, 'workspace_id account_id environment')
    for item in scope.values(): text(item, 100)
    require(bool(re.fullmatch('[a-z][a-z0-9-]{1,31}', scope['environment'])))
    require(all(expected is None or expected == scope[key] for key, expected in (
        ('workspace_id', workspace), ('account_id', account), ('environment', environment))),
        'Evidence does not match the expected workspace, account or environment.')


def checksum(payload, integrity):
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    result = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    require(hmac.compare_digest(result, integrity['digest']), 'Evidence checksum does not match the payload.')
    return result


def sha256(value):
    require(type(value) is str and bool(re.fullmatch('[a-f0-9]{64}', value)))


def verify_run_report(p, integrity, workspace, account, environment):
    fields(p, 'format format_version exported_at_utc source_release schema_version scope run connector steps boundary')
    require(p['format']=='nexus-durable-run-evidence' and type(p['format_version']) is int and p['format_version']==1)
    utc(p['exported_at_utc']); text(p['source_release'],64); integer(p['schema_version'],1); text(p['boundary'],2000)
    verify_scope(p['scope'],workspace,account,environment)
    fields(p['connector'],'mode binding_source')
    require(p['connector']['mode'] in ('synthetic','http') and p['connector']['binding_source']=='recorded_workflow')
    run=p['run'];require(type(run) is dict)
    names='id status version cursor definition_sha256 recoveries cancel_requested created_at_utc updated_at_utc'
    if 'scheduled_start_at_utc' in run:
        names+=' scheduled_start_at_utc';utc(run['scheduled_start_at_utc'])
    fields(run,names)
    text(run['id'],100);integer(run['version'],1);integer(run['cursor']);sha256(run['definition_sha256'])
    integer(run['recoveries']);require(type(run['cancel_requested']) is bool)
    require(run['status'] in ('queued','processing','waiting_action','waiting_review','paused','cancelling',
        'outcome_unknown','succeeded','cancelled','failed','rejected','expired'))
    utc(run['created_at_utc']);utc(run['updated_at_utc'])
    steps=p['steps'];require(type(steps) is list and 2<=len(steps)<=12 and run['cursor']<=len(steps))
    actions=set();verified=0;skipped=0;conditions=0
    for position,step in enumerate(steps):
        require(type(step) is dict)
        names='position kind status updated_at_utc action review'
        if 'condition' in step:names+=' condition'
        if 'skipped_by' in step:names+=' skipped_by'
        fields(step,names);integer(step['position']);require(step['position']==position)
        utc(step['updated_at_utc'])
        require(step['kind'] in ('checkpoint','approval','governed_action','condition','output'))
        require(step['status'] in ('pending','waiting_action','waiting_review','outcome_unknown','completed',
            'cancelled','failed','rejected','expired','denied','verification_failed','blocked','changes_requested','skipped'))
        action=step['action']
        if action is not None:
            require(step['kind']=='governed_action')
            fields(action,'id status verified attempts policy_version payload_sha256 approval')
            text(action['id'],100);require(action['id'] not in actions);actions.add(action['id'])
            integer(action['attempts']);integer(action['policy_version'],1);sha256(action['payload_sha256'])
            require(action['status'] in ('queued','awaiting_approval','executing','outcome_unknown','verified',
                'cancelled','denied','rejected','expired','failed','verification_failed','blocked','changes_requested'))
            require(type(action['verified']) is bool and action['verified']==(action['status']=='verified'))
            verified+=int(action['verified'])
            if action['approval'] is not None:
                fields(action['approval'],'status version');integer(action['approval']['version'],1)
                require(action['approval']['status'] in ('pending','approved','rejected','expired','cancelled','changes_requested'))
                require(not action['verified'] or action['approval']['status']=='approved')
            require(step['status']!='completed' or action['verified'])
        else:
            require(step['kind']!='governed_action' or step['status']!='completed')
        if step['kind']=='approval' and step['status'] in ('completed','rejected'):
            fields(step['review'],'decision independent_reviewer_recorded')
            require(step['review']['independent_reviewer_recorded'] is True)
            require(step['review']['decision']==('approve' if step['status']=='completed' else 'reject'))
        else:require(step['review'] is None)
        if step['kind']=='condition' and step['status']=='completed':
            require('condition' in step);condition=step['condition']
            fields(condition,'kind source_step matched next_step')
            require(condition['kind']=='supplier_allowlist' and type(condition['matched']) is bool)
            integer(condition['source_step']);integer(condition['next_step'],1)
            require(condition['source_step']<position)
            source=steps[condition['source_step']]
            require(source['kind']=='governed_action' and source['status']=='completed' and
                source['action'] is not None and source['action']['verified'] is True)
            require(condition['next_step']==(position+1 if condition['matched'] else len(steps)-1))
            conditions+=1
        else:require('condition' not in step)
        if step['status']=='skipped':
            require('skipped_by' in step and action is None);integer(step['skipped_by'])
            require(step['skipped_by']<position)
            origin=steps[step['skipped_by']]
            require(origin['kind']=='condition' and origin['status']=='completed' and
                origin['condition']['matched'] is False and origin['condition']['next_step']>position)
            skipped+=1
        else:require('skipped_by' not in step)
    require(steps[0]['kind']=='checkpoint' and steps[-1]['kind']=='output')
    for position,step in enumerate(steps):
        if step.get('condition',{}).get('matched') is False:
            for later in steps[position+1:step['condition']['next_step']]:
                require(later['status']=='skipped' and later['skipped_by']==position)
    if run['status']=='succeeded':
        require(run['cursor']==len(steps) and all(step['status'] in ('completed','skipped') for step in steps))
    result=checksum(p,integrity)
    return {'file_integrity':'valid','file_format':'nexus-durable-run-evidence','authenticated_signature':False,
        'run_id':run['id'],'scope':p['scope'],'connector_mode':p['connector']['mode'],'status':run['status'],
        'step_count':len(steps),'recorded_action_count':len(actions),'recorded_verified_actions':verified,
        'recorded_unverified_actions':len(actions)-verified,'recorded_condition_outcome_count':conditions,
        'skipped_step_count':skipped,'audit_history_included':False,'checksum':result,'boundary':BOUNDARY}


def verify_report(value, *, workspace=None, account=None, environment=None):
    fields(value, 'payload integrity')
    p, integrity = value['payload'], value['integrity']
    fields(integrity, 'algorithm canonicalization digest authenticated_signature')
    require(integrity['algorithm'] == 'sha256' and integrity['canonicalization'] == 'sorted-ascii-json-v1')
    require(integrity['authenticated_signature'] is False, 'Signed or unknown evidence formats are unsupported.')
    require(type(integrity['digest']) is str and bool(re.fullmatch('[a-f0-9]{64}', integrity['digest'])))
    if type(p) is dict and p.get('format')=='nexus-durable-run-evidence':
        return verify_run_report(p,integrity,workspace,account,environment)
    fields(p, 'format format_version exported_at_utc source_release scope check route operation connector verification audit_events boundary')
    require(p['format'] == 'nexus-supplier-check-evidence' and type(p['format_version']) is int and p['format_version'] == 1)
    utc(p['exported_at_utc']); text(p['source_release'], 64); text(p['boundary'], 2000)
    scope = p['scope']; verify_scope(scope,workspace,account,environment)
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
    actual_checksum=checksum(p,integrity)
    return {'file_integrity': 'valid', 'authenticated_signature': False, 'check_id': check['id'],
            'scope': scope, 'connector_mode': p['connector']['mode'], 'status': check['status'],
            'lookup_verified': check['verified'], 'audit_event_count': len(events), 'checksum': actual_checksum,
            'boundary': BOUNDARY}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verify a saved supplier-check or durable-run evidence report offline; no database or network access.')
    parser.add_argument('file', help='Path to the downloaded JSON report')
    parser.add_argument('--workspace', help='Expected workspace ID (optional)')
    parser.add_argument('--account', help='Expected report account ID (optional)')
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
