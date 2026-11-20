import json
from pathlib import Path
import subprocess
import sys
import httpx
import pytest
from nexus.config import Settings
from nexus.business_connector import HTTPBusiness
from nexus.mock_connector import MockBusiness
from nexus import synthetic_drill as drill


def test_full_synthetic_drill_ignores_operator_config_and_never_uses_http(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private database sentinel')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_SECRET=private-runtime-secret\nNEXUS_BUSINESS_CONNECTOR=http\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BUSINESS_CONNECTOR','http')
    monkeypatch.setenv('NEXUS_BUSINESS_BASE_URL','https://customer.invalid/api/v1')
    monkeypatch.setenv('NEXUS_MODE','pilot')
    def forbidden(*args,**kwargs):pytest.fail('Operator configuration or external transport must not be used')
    monkeypatch.setattr(Settings,'from_env',forbidden)
    monkeypatch.setattr(HTTPBusiness,'request',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    before=(private.read_bytes(),envfile.read_bytes())
    result=drill.run_drill(tmp_path/'disposable')
    assert result['passed'] and len(result['steps'])==15 and all(s['passed'] for s in result['steps'])
    assert result['connector_mode']=='synthetic' and result['synthetic_effect_count']==2
    assert not result['customer_acceptance'] and not result['production_ready']
    assert (private.read_bytes(),envfile.read_bytes())==before


def test_existing_directory_is_refused_without_touching_files(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();sentinel=existing/'control.db';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):drill.run_drill(existing)
    assert sentinel.read_bytes()==b'preserve' and list(existing.iterdir())==[sentinel]


def test_cli_can_repeat_without_overwriting_reports_and_cleans_temporary_databases(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out)
        assert summary['passed'] and summary['steps_passed']==15
        saved=json.loads(Path(summary['report']).read_text())
        assert saved['passed'] and saved['boundary']==drill.BOUNDARY
        assert 'password' not in json.dumps(saved) and 'csrf' not in json.dumps(saved)
    files=list(output.iterdir())
    assert len(files)==2 and all(p.suffix=='.json' for p in files)
    assert not list(output.rglob('*.db'))


def test_missing_worker_dispatch_fails_command_and_saves_failed_step(tmp_path,capsys,monkeypatch):
    monkeypatch.setattr(drill,'run_once',lambda *args:False)
    assert drill.main(['--output-dir',str(tmp_path/'reports')])==1
    summary=json.loads(capsys.readouterr().out);assert not summary['passed']
    report=json.loads(Path(summary['report']).read_text())
    assert report['failure']=='supplier_worker_dispatch' and report['steps'][-1]=={'id':'supplier_worker_dispatch','passed':False}
    assert not list((tmp_path/'reports').rglob('*.db'))


def test_unexpected_error_details_never_become_report_or_console_output(tmp_path,capsys,monkeypatch):
    secret='private-error-credential'
    def broken(*args):raise RuntimeError(secret)
    monkeypatch.setattr(drill,'run_once',broken)
    assert drill.main(['--output-dir',str(tmp_path/'reports')])==1
    output=capsys.readouterr();assert secret not in output.out+output.err
    report=Path(json.loads(output.out)['report']).read_text()
    assert secret not in report and json.loads(report)['failure']=='isolated_drill_could_not_finish'


def test_wrong_authoritative_result_cannot_pass_recovery_drill(tmp_path,monkeypatch):
    original=MockBusiness.lookup
    def wrong(connector,*args,**kwargs):
        result=original(connector,*args,**kwargs)
        return {**result,'supplier_id':'WRONG-SUPPLIER'} if result else None
    monkeypatch.setattr(MockBusiness,'lookup',wrong)
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='authoritative_reconciliation_without_retry'
    assert result['steps'][-1]['passed'] is False


def test_different_adapter_is_rejected_before_any_execution(tmp_path,monkeypatch):
    class UnexpectedAdapter:
        def invoke(self,*args):pytest.fail('Unexpected adapter was dispatched')
    monkeypatch.setattr('nexus.app.business_connector',lambda settings:UnexpectedAdapter())
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='synthetic_adapter_only'


def test_output_file_is_not_overwritten_when_directory_was_expected(tmp_path,capsys):
    file=tmp_path/'keep.txt';file.write_text('preserve')
    assert drill.main(['--output-dir',str(file)])==1
    assert file.read_text()=='preserve' and not json.loads(capsys.readouterr().out)['passed']


def test_portable_entry_point_from_an_unrelated_directory_needs_no_configuration(tmp_path):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_connector_drill.py'
    result=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'saved reports')],
        cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    summary=json.loads(result.stdout);assert summary['passed'] and summary['steps_passed']==15
    assert not result.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
