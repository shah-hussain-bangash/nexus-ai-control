import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pytest
from test_check_evidence import report
from test_connector_checks import setup, submit
from nexus.worker import run_once
from nexus.evidence_verifier import InvalidEvidence, MAX_BYTES, main, parse_report, verify_report


def downloaded(ctx, verified=True):
    identifier=submit(ctx,setup(ctx)).json()['check']['id']
    if verified:assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    response=report(ctx,identifier);assert response.status_code==200,response.text
    return response.json()


def resign(value):
    value['integrity']['digest']=hashlib.sha256(json.dumps(value['payload'],sort_keys=True,
        separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    return value


@pytest.mark.parametrize('verified',[False,True])
def test_actual_export_verifies_offline_without_changing_lookup_outcome(ctx,verified):
    value=downloaded(ctx,verified);scope=value['payload']['scope']
    summary=verify_report(parse_report(json.dumps(value,ensure_ascii=False).encode()),
        workspace=scope['workspace_id'],account=scope['account_id'],environment=scope['environment'])
    assert summary['file_integrity']=='valid' and summary['authenticated_signature'] is False
    assert summary['lookup_verified'] is verified
    assert summary['connector_mode']=='synthetic' and 'does not prove authenticity' in summary['boundary']


def test_checksum_tampering_is_detected_and_recomputed_checksums_do_not_authenticate(ctx):
    value=downloaded(ctx);value['payload']['check']['reason']='Changed reason'
    with pytest.raises(InvalidEvidence,match='checksum'):verify_report(value)
    # An attacker can recompute an unsigned checksum; explicitly preserve that limitation.
    result=verify_report(resign(value))
    assert result['authenticated_signature'] is False and 'current server state' in result['boundary']


@pytest.mark.parametrize('change',[
    lambda p:p['check'].update(verified=False),
    lambda p:p['verification']['result'].update(supplier_id='ANOTHER'),
    lambda p:p['verification']['result'].update(external_ref='ANOTHER'),
    lambda p:p['verification']['result'].update(state='created'),
    lambda p:p['connector'].update(mode='http'),
    lambda p:p['route'].update(schema_version='unknown'),
    lambda p:p['route'].update(agent_generation=True),
    lambda p:p['operation'].update(action='purchase:create'),
    lambda p:p['scope'].update(environment='bad/environment'),
    lambda p:p.update(format_version=True),
    lambda p:p.update(exported_at_utc='2026-99-99T00:00:00.000000Z'),
    lambda p:p['audit_events'].append(copy.deepcopy(p['audit_events'][0])),
    lambda p:p['audit_events'][0].update(detail={'credential':'not-allowed'}),
    lambda p:p['verification']['result'].update(raw_response='not-allowed'),
    lambda p:p.update(unknown_extension='unsupported'),
])
def test_inconsistent_or_extended_formats_fail_even_with_recomputed_checksum(ctx,change):
    value=downloaded(ctx);change(value['payload'])
    with pytest.raises(InvalidEvidence):verify_report(resign(value))


def test_expected_account_workspace_and_environment_are_optional_exact_matches(ctx):
    value=downloaded(ctx)
    for expected in ({'workspace':'other'},{'account':'other'},{'environment':'production'}):
        with pytest.raises(InvalidEvidence,match='expected'):verify_report(value,**expected)


@pytest.mark.parametrize('raw',[
    b'{"payload":{},"payload":{},"integrity":{}}', b'{"x":NaN}', b'{"x":Infinity}',
    b'{"x":1.0}', b'{"x":9007199254740992}', b'{"x":-9007199254740992}',
    b'not json', b'\xff', b'['*1100+b']'*1100, b' '* (MAX_BYTES+1),
])
def test_malformed_duplicate_oversized_and_noncanonical_numeric_files_fail(raw):
    with pytest.raises(InvalidEvidence):parse_report(raw)


def test_cli_is_standard_library_only_and_does_not_load_settings_or_create_local_data(ctx,tmp_path):
    value=downloaded(ctx);file=tmp_path/'evidence with spaces.json'
    value['payload']['check']['reason']='مراجعة 😀';resign(value)
    file.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    (tmp_path/'.env').write_text('NEXUS_DATABASE_URL=invalid\nNEXUS_BUSINESS_TIMEOUT_SECONDS=not-an-integer\n')
    script=Path(__file__).resolve().parents[2]/'scripts/verify_supplier_evidence.py'
    # -S excludes project dependencies. Socket calls fail if the verifier attempts networking.
    runner="import runpy,socket,sys; socket.socket=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('network forbidden')); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
    before=sorted(p.name for p in tmp_path.iterdir())
    result=subprocess.run([sys.executable,'-I','-S','-c',runner,str(script),str(file),'--environment','staging'],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    summary=json.loads(result.stdout);assert summary['file_integrity']=='valid' and summary['lookup_verified']
    assert sorted(p.name for p in tmp_path.iterdir())==before and not result.stderr


def test_cli_errors_are_bounded_and_do_not_echo_private_paths_or_report_text(tmp_path,capsys):
    secret='private-credential-that-must-not-be-printed'
    file=tmp_path/(secret+'.json');file.write_text(secret)
    assert main([str(file)])==2
    result=capsys.readouterr();assert secret not in result.out and not result.err
    assert json.loads(result.out)['file_integrity']=='invalid'
    assert main([str(tmp_path/'missing.json')])==2
    assert main([str(tmp_path)])==2


@pytest.mark.parametrize('value',[None,True,1,'report',[],{}, {'payload':None,'integrity':{}},
    {'payload':{},'integrity':{'algorithm':'sha256','canonicalization':'sorted-ascii-json-v1','digest':'0'*64,'authenticated_signature':True}}])
def test_unsupported_roots_and_signed_formats_fail_cleanly(value):
    with pytest.raises(InvalidEvidence):verify_report(value)


def test_json_depth_scanner_ignores_brackets_and_escaped_quotes_inside_strings():
    value={'text':'['*100+'\\"'+']'*100}
    assert parse_report(json.dumps(value).encode())==value
