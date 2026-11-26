import json
from pathlib import Path
import subprocess
import sys
import pytest
from conftest import auth, approve
from test_durable import create, advance, body
from test_durable_conditions import create as conditioned
from test_evidence_verifier import resign
from nexus.db import now
from nexus.evidence_verifier import verify_report, parse_report, InvalidEvidence, main


def exported(ctx,run):
    auth(ctx);response=ctx['client'].get('/v1/agent-runs/'+run['id']+'/evidence')
    assert response.status_code==200,response.text
    return response.json()


def finished(ctx):
    run=create(ctx,review=False,purchase=False)
    return exported(ctx,advance(ctx,run['id']))


@pytest.mark.parametrize('state',['queued','completed','review','purchase_approval','unknown','scheduled','condition_match','condition_skip'])
def test_actual_run_exports_verify_without_claiming_authenticity(ctx,state):
    if state.startswith('condition'):
        run=conditioned(ctx,['SUP-DEMO-104'] if state=='condition_match' else ['OTHER'])
    elif state=='scheduled':
        h,_=auth(ctx);h['Idempotency-Key']='offline-scheduled-report'
        request=body(ctx);request['start_at']=int(now())+3600
        response=ctx['client'].post('/v1/agent-runs',headers=h,json=request);assert response.status_code==201
        run=response.json()
    else:run=create(ctx,review=state=='review',purchase=state in ('purchase_approval','unknown'),simulation='timeout_after_commit' if state=='unknown' else 'normal')
    if state not in ('queued','scheduled'):run=advance(ctx,run['id'])
    if state=='unknown':
        assert approve(ctx).status_code==200;run=advance(ctx,run['id'])
    value=exported(ctx,run);scope=value['payload']['scope']
    summary=verify_report(parse_report(json.dumps(value).encode()),workspace=scope['workspace_id'],account=scope['account_id'],environment=scope['environment'])
    assert summary['file_integrity']=='valid' and summary['file_format']=='nexus-durable-run-evidence'
    assert summary['authenticated_signature'] is False and summary['audit_history_included'] is False
    assert summary['status']==run['status'] and summary['step_count']==len(run['steps'])
    assert 'does not prove authenticity' in summary['boundary']
    assert 'lookup_verified' not in summary and 'production_ready' not in summary
    if state=='unknown':assert summary['recorded_unverified_actions']==1 and summary['status']=='outcome_unknown'
    if state=='condition_skip':assert summary['skipped_step_count']==2 and summary['recorded_condition_outcome_count']==1


def test_changed_checksum_is_detected_but_recomputed_file_is_still_unsigned(ctx):
    value=finished(ctx);value['payload']['run']['recoveries']+=1
    with pytest.raises(InvalidEvidence,match='checksum'):verify_report(value)
    result=verify_report(resign(value))
    assert result['file_integrity']=='valid' and result['authenticated_signature'] is False


@pytest.mark.parametrize('change',[
    lambda p:p.update(schema_version=True),
    lambda p:p.update(private_note='not supported'),
    lambda p:p['run'].update(cursor=99),
    lambda p:p['run'].update(version=True),
    lambda p:p['run'].update(status='unsupported'),
    lambda p:p['run'].update(scheduled_start_at_utc='not a timestamp'),
    lambda p:p['run'].update(secret='not supported'),
    lambda p:p['steps'][1].update(position=0),
    lambda p:p['steps'][0].update(kind='output'),
    lambda p:p['steps'][-1].update(kind='checkpoint'),
    lambda p:p['steps'].__imul__(5),
    lambda p:p['steps'][1]['action'].update(raw_response='not supported'),
    lambda p:p['steps'][1]['action'].update(verified=False),
    lambda p:p['steps'][1]['action'].update(approval={'status':'pending','version':1}),
    lambda p:p['steps'][1].update(review={'decision':'approve','independent_reviewer_recorded':True}),
    lambda p:p['steps'][1].update(condition={'kind':'supplier_allowlist','source_step':0,'matched':True,'next_step':2}),
    lambda p:p['steps'][1].update(skipped_by=0),
])
def test_invalid_or_extended_run_formats_fail_even_with_recomputed_checksum(ctx,change):
    value=finished(ctx);change(value['payload'])
    with pytest.raises(InvalidEvidence):verify_report(resign(value))


@pytest.mark.parametrize('change',[
    lambda p:p['steps'][2]['condition'].update(source_step=4),
    lambda p:p['steps'][2]['condition'].update(matched='false'),
    lambda p:p['steps'][2]['condition'].update(next_step=0),
    lambda p:p['steps'][2]['condition'].update(supplier_ids=['not exported']),
    lambda p:p['steps'][4].update(skipped_by=1),
    lambda p:p['steps'][4].update(skipped_by=True),
    lambda p:p['steps'][4].update(status='pending'),
])
def test_condition_and_skip_inconsistencies_are_rejected(ctx,change):
    run=conditioned(ctx,['OTHER']);value=exported(ctx,advance(ctx,run['id']))
    change(value['payload'])
    with pytest.raises(InvalidEvidence):verify_report(resign(value))


def test_optional_scope_checks_match_the_report_exporter(ctx):
    value=finished(ctx)
    for expected in ({'workspace':'other'},{'account':'other'},{'environment':'production'}):
        with pytest.raises(InvalidEvidence,match='expected'):verify_report(value,**expected)


def test_cli_stays_standard_library_only_without_database_settings_network_or_writes(ctx,tmp_path):
    value=finished(ctx);value['payload']['boundary']='مراجعة 😀';resign(value)
    file=tmp_path/'run report with spaces.json';file.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    (tmp_path/'.env').write_text('NEXUS_DATABASE_URL=invalid\nNEXUS_BUSINESS_TIMEOUT_SECONDS=not-an-integer\n')
    script=Path(__file__).resolve().parents[2]/'scripts/verify_supplier_evidence.py'
    runner="import runpy,socket,sys; socket.socket=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('network forbidden')); sys.modules.update({name:None for name in ('sqlite3','sqlalchemy','nexus.config','nexus.db')}); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
    before=sorted(p.name for p in tmp_path.iterdir())
    result=subprocess.run([sys.executable,'-I','-S','-c',runner,str(script),str(file),'--environment','staging'],cwd=tmp_path,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
    summary=json.loads(result.stdout);assert summary['file_integrity']=='valid' and summary['run_id']==value['payload']['run']['id']
    assert not result.stderr and sorted(p.name for p in tmp_path.iterdir())==before
    assert not any(word in result.stdout for word in ('Bearer','password','مراجعة'))


def test_invalid_run_cli_does_not_echo_report_text_or_private_path(ctx,tmp_path,capsys):
    value=finished(ctx);secret='private-value-must-not-be-printed'
    value['payload']['run']['private_field']=secret;resign(value)
    file=tmp_path/(secret+'.json');file.write_text(json.dumps(value),encoding='utf-8')
    assert main([str(file)])==2
    output=capsys.readouterr();assert secret not in output.out+output.err
    assert json.loads(output.out)['file_integrity']=='invalid'
