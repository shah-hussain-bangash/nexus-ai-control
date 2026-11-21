import json
from pathlib import Path
import subprocess
import sys
import httpx
import pytest
from nexus import inference_drill as drill,inference
from nexus.config import Settings
from nexus.business_connector import HTTPBusiness


def test_full_drill_ignores_private_operator_config_and_restores_patches(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private database sentinel')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_MODE=pilot\nNEXUS_SECRET=private-config\n')
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BUSINESS_CONNECTOR','http');monkeypatch.setenv('NEXUS_LIVE_INFERENCE','1')
    monkeypatch.setenv('NEXUS_PROVIDER_DRILL_KEY','private operator credential')
    def forbidden(*args,**kwargs):pytest.fail('Operator settings or customer transport used')
    monkeypatch.setattr(Settings,'from_env',forbidden);monkeypatch.setattr(HTTPBusiness,'request',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    original=(inference.os,inference.time,inference.period,httpx.HTTPTransport.handle_request)
    report=drill.run_drill(tmp_path/'disposable')
    assert report['passed'] and len(report['steps'])==27 and all(row['passed'] for row in report['steps'])
    assert report['provider_request_count']==7 and report['spent_micro_usd']==40
    assert not report['customer_acceptance'] and not report['production_ready']
    assert (inference.os,inference.time,inference.period,httpx.HTTPTransport.handle_request)==original
    assert private.read_bytes()==b'private database sentinel' and envfile.read_text()=='NEXUS_MODE=pilot\nNEXUS_SECRET=private-config\n'
    assert inference.os.environ['NEXUS_PROVIDER_DRILL_KEY']=='private operator credential'
    assert 'private operator credential' not in json.dumps(report)


def test_existing_directory_is_not_reused(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();sentinel=existing/'control.db';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):drill.run_drill(existing)
    assert sentinel.read_bytes()==b'preserve' and list(existing.iterdir())==[sentinel]


def test_cli_unique_reports_have_only_safe_metadata_and_no_databases(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out);assert summary['passed'] and summary['steps_passed']==27
        report=json.loads(Path(summary['report']).read_text(encoding='utf-8'))
        assert set(report)=={'format','format_version','release','schema_version','created_at_utc','provider_mode','connector_mode',
            'passed','customer_acceptance','production_ready','steps','boundary','provider_request_count','spent_micro_usd'}
        assert report['format']=='nexus-synthetic-inference-drill' and report['boundary']==drill.BOUNDARY
        assert all(set(row)=={'id','passed'} for row in report['steps'])
        assert not any(text in json.dumps(report) for text in ['password','cookie','@drill.invalid','confidential phrase','request_hash','disposable-transport-only'])
    assert len(list(output.iterdir()))==2 and not list(output.rglob('*.db')) and not list(output.glob('.inference-*'))


@pytest.mark.parametrize('broken,expected',[
    ('guardrail','redaction_cannot_hide_original_block'),
    ('deadline','simulated_late_completion_stays_unknown'),
])
def test_broken_control_cannot_pass(tmp_path,monkeypatch,broken,expected):
    if broken=='guardrail':monkeypatch.setattr(inference,'check_guardrail',lambda text,config:{'verdict':'passed','output':text})
    else:monkeypatch.setattr(drill,'late_response',lambda clock,payload:httpx.Response(200,json=payload))
    original=(inference.os,inference.time,httpx.HTTPTransport.handle_request)
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']==expected and report['steps'][-1]=={'id':expected,'passed':False}
    assert (inference.os,inference.time,httpx.HTTPTransport.handle_request)==original


def test_escape_from_mock_transport_is_blocked_before_network(tmp_path,monkeypatch):
    # Deliberately route the mock request into the real transport entry point.
    # The drill's independent denial guard must intercept it before pool/network I/O.
    def escape(self,request):return httpx.HTTPTransport.handle_request(None,request)
    monkeypatch.setattr(httpx.MockTransport,'handle_request',escape)
    original=httpx.HTTPTransport.handle_request
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']=='network_dispatch_blocked'
    assert httpx.HTTPTransport.handle_request is original


def test_private_failure_details_are_hidden_and_cleanup_runs(tmp_path,capsys,monkeypatch):
    def broken(*args):raise RuntimeError('private upstream exception sentinel')
    monkeypatch.setattr(inference,'provider_response',broken)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private upstream exception sentinel' not in captured.out+captured.err
    summary=json.loads(captured.out);assert not summary['passed']
    saved=Path(summary['report']).read_text(encoding='utf-8')
    assert 'private upstream exception sentinel' not in saved and json.loads(saved)['failure']=='isolated_drill_could_not_finish'
    assert not list(output.rglob('*.db'))


def test_report_write_failure_cannot_claim_success(tmp_path,capsys,monkeypatch):
    original=Path.open
    def blocked(path,*args,**kwargs):
        if path.name.startswith('synthetic-inference-'):raise OSError('private report path')
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
    assert not json.loads(captured.out)['passed'] and not list(output.glob('synthetic-inference-*.json'))


def test_portable_entry_from_unrelated_directory(tmp_path):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_inference_drill.py'
    response=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'saved reports')],cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['steps_passed']==27 and not response.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
