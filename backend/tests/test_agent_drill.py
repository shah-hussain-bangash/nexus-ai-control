import json
from pathlib import Path
import subprocess
import sys
import httpx
import pytest
from nexus import agent_drill as drill,durable
from nexus.config import Settings
from nexus.business_connector import HTTPBusiness


def test_full_agent_drill_ignores_operator_settings_and_external_transports(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private database sentinel')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_SECRET=private-config\nNEXUS_MODE=pilot\n')
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BUSINESS_CONNECTOR','http');monkeypatch.setenv('NEXUS_LIVE_INFERENCE','1')
    def forbidden(*args,**kwargs):pytest.fail('Operator settings or external transport used')
    monkeypatch.setattr(Settings,'from_env',forbidden);monkeypatch.setattr(HTTPBusiness,'request',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    before=(private.read_bytes(),envfile.read_bytes());original_clock=durable.now
    result=drill.run_drill(tmp_path/'disposable')
    assert result['passed'] and len(result['steps'])==24 and all(row['passed'] for row in result['steps'])
    assert result['synthetic_effect_count']==2 and result['run_count']==3
    assert not result['customer_acceptance'] and not result['production_ready'] and durable.now is original_clock
    assert (private.read_bytes(),envfile.read_bytes())==before


def test_existing_directory_is_not_reused(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();sentinel=existing/'control.db';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):drill.run_drill(existing)
    assert sentinel.read_bytes()==b'preserve' and list(existing.iterdir())==[sentinel]


def test_cli_reports_repeat_safely_without_private_payloads_or_databases(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out);assert summary['passed'] and summary['steps_passed']==24
        report=json.loads(Path(summary['report']).read_text(encoding='utf-8'))
        assert report['format']=='nexus-synthetic-agent-drill' and report['boundary']==drill.BOUNDARY
        assert set(report)=={'format','format_version','release','schema_version','created_at_utc','connector_mode',
            'passed','customer_acceptance','production_ready','steps','boundary','synthetic_effect_count','run_count'}
        assert all(set(row)=={'id','passed'} for row in report['steps'])
        assert not any(text in json.dumps(report) for text in ['password','cookie','@drill.invalid','SUP-DEMO','12500','request_hash'])
    assert len(list(output.iterdir()))==2 and not list(output.rglob('*.db')) and not list(output.glob('.agents-*'))


@pytest.mark.parametrize('broken,expected',[
    ('business','verified_supplier_reaches_independent_review'),('workflow','resume_advances_only_checkpoint'),
    ('recovery','simulated_late_claim_recovers_before_step'),
])
def test_broken_worker_control_cannot_pass_the_drill(tmp_path,monkeypatch,broken,expected):
    if broken=='business':monkeypatch.setattr(drill,'run_once',lambda *args:False)
    elif broken=='workflow':monkeypatch.setattr(durable,'run_flow_once',lambda *args:False)
    else:monkeypatch.setattr(durable,'recover_expired_claim',lambda *args:None)
    original_clock=durable.now
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']==expected and report['steps'][-1]=={'id':expected,'passed':False}
    assert durable.now is original_clock


def test_private_failure_details_are_hidden_and_cleanup_still_runs(tmp_path,capsys,monkeypatch):
    def broken(*args):raise RuntimeError('private-agent-error-credential')
    monkeypatch.setattr(drill,'run_once',broken)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private-agent-error-credential' not in captured.out+captured.err
    summary=json.loads(captured.out);assert not summary['passed']
    report=Path(summary['report']).read_text(encoding='utf-8')
    assert 'private-agent-error-credential' not in report and json.loads(report)['failure']=='isolated_drill_could_not_finish'
    assert not list(output.rglob('*.db'))


def test_report_write_failure_cannot_claim_success(tmp_path,capsys,monkeypatch):
    original=Path.open
    def blocked(path,*args,**kwargs):
        if path.name.startswith('synthetic-agents-'):raise OSError('private report path')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',blocked)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private report path' not in captured.out+captured.err
    assert not json.loads(captured.out)['passed'] and not list(output.iterdir())


def test_cleanup_failure_cannot_claim_success(tmp_path,capsys,monkeypatch):
    class BrokenCleanup:
        def __init__(self,**kw):self.root=Path(kw['dir'])/'cleanup-fixture';self.root.mkdir()
        def __enter__(self):return str(self.root)
        def __exit__(self,*args):raise OSError('private cleanup path')
    monkeypatch.setattr(drill,'TemporaryDirectory',BrokenCleanup)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private cleanup path' not in captured.out+captured.err
    assert not json.loads(captured.out)['passed'] and not list(output.glob('synthetic-agents-*.json'))


def test_portable_agent_entry_from_unrelated_directory(tmp_path):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_agent_drill.py'
    response=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'saved reports')],cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['steps_passed']==24 and not response.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
