import json
from pathlib import Path
import subprocess
import sys
import httpx
import pytest
from nexus.config import Settings
from nexus.business_connector import HTTPBusiness
from nexus.mock_connector import MockBusiness
from nexus import retrieval_drill as drill


def test_complete_drill_ignores_operator_settings_and_external_transports(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private database sentinel')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_SECRET=private-runtime-secret\nNEXUS_BUSINESS_CONNECTOR=http\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BUSINESS_CONNECTOR','http')
    monkeypatch.setenv('NEXUS_BUSINESS_BASE_URL','https://customer.invalid/api/v1')
    monkeypatch.setenv('NEXUS_MODE','pilot');monkeypatch.setenv('NEXUS_LIVE_INFERENCE','1')
    def forbidden(*args,**kwargs):pytest.fail('Operator settings or external transport were used')
    monkeypatch.setattr(Settings,'from_env',forbidden)
    monkeypatch.setattr(HTTPBusiness,'request',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    before=(private.read_bytes(),envfile.read_bytes())
    result=drill.run_drill(tmp_path/'disposable')
    assert result['passed'] and len(result['steps'])==18 and all(row['passed'] for row in result['steps'])
    assert not result['customer_acceptance'] and not result['production_ready']
    assert (private.read_bytes(),envfile.read_bytes())==before


def test_existing_directory_is_never_reused(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();sentinel=existing/'control.db';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):drill.run_drill(existing)
    assert sentinel.read_bytes()==b'preserve' and list(existing.iterdir())==[sentinel]


def test_cli_repeatability_unique_reports_and_database_cleanup(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out)
        assert summary['passed'] and summary['steps_passed']==18
        report=json.loads(Path(summary['report']).read_text(encoding='utf-8'))
        assert report['format']=='nexus-synthetic-retrieval-drill' and report['boundary']==drill.BOUNDARY
        assert set(report)=={'format','format_version','release','schema_version','created_at_utc','connector_mode',
            'passed','customer_acceptance','production_ready','steps','boundary'}
        assert all(set(row)=={'id','passed'} for row in report['steps'])
        assert not any(text in json.dumps(report) for text in ['Procurement','إِدَارَة','@drill.invalid','password','cookie','content_base64'])
    files=list(output.iterdir());assert len(files)==2 and all(path.suffix=='.json' for path in files)
    assert not list(output.rglob('*.db')) and not list(output.glob('.retrieval-*'))


@pytest.mark.parametrize('broken',['arabic','comparison','access'])
def test_broken_retrieval_control_cannot_produce_passing_drill(tmp_path,monkeypatch,broken):
    if broken=='arabic':
        from nexus.documents import search_documents
        def search(db,user,query,top_k):
            return [] if query=='ادارة المشتريات' else search_documents(db,user,query,top_k)
        monkeypatch.setattr('nexus.retrieval_checks.search_documents',search)
        expected='baseline_and_no_result_case_pass'
    elif broken=='comparison':
        monkeypatch.setattr('nexus.retrieval_comparison.classify',lambda values:'unchanged')
        expected='saved_comparison_detects_regression'
    else:
        monkeypatch.setattr('nexus.retrieval_checks.can_read',lambda *args:True)
        expected='revoked_unlisted_source_blocks_saved_results'
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']==expected
    assert report['steps'][-1]=={'id':expected,'passed':False}


def test_failed_cli_keeps_safe_failure_report_and_cleans_databases(tmp_path,capsys,monkeypatch):
    secret='private-error-credential'
    def broken(*args):raise RuntimeError(secret)
    monkeypatch.setattr('nexus.retrieval_checks.search_documents',broken)
    output=tmp_path/'reports'
    assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert secret not in captured.out+captured.err
    summary=json.loads(captured.out);assert not summary['passed']
    text=Path(summary['report']).read_text(encoding='utf-8')
    assert secret not in text and json.loads(text)['failure']=='isolated_drill_could_not_finish'
    assert not list(output.rglob('*.db'))


def test_unexpected_adapter_is_rejected_before_its_use(tmp_path,monkeypatch):
    class UnexpectedAdapter:
        def count(self):pytest.fail('Unexpected adapter used')
    monkeypatch.setattr('nexus.app.business_connector',lambda settings:UnexpectedAdapter())
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='synthetic_runtime_only'


def test_report_write_and_cleanup_failures_cannot_return_success(tmp_path,capsys,monkeypatch):
    original=Path.open
    def blocked(path,*args,**kwargs):
        if path.name.startswith('synthetic-retrieval-'):raise OSError('private path detail')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',blocked)
    output=tmp_path/'reports'
    assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private path detail' not in captured.out+captured.err
    assert not json.loads(captured.out)['passed'] and not list(output.iterdir())


def test_cleanup_failure_cannot_return_success(tmp_path,capsys,monkeypatch):
    class BrokenCleanup:
        def __init__(self,**kw):self.root=Path(kw['dir'])/'cleanup-fixture';self.root.mkdir()
        def __enter__(self):return str(self.root)
        def __exit__(self,*args):raise OSError('private cleanup detail')
    monkeypatch.setattr(drill,'TemporaryDirectory',BrokenCleanup)
    assert drill.main(['--output-dir',str(tmp_path/'reports')])==1
    captured=capsys.readouterr();assert 'private cleanup detail' not in captured.out+captured.err
    assert not json.loads(captured.out)['passed']
    assert not list((tmp_path/'reports').glob('synthetic-retrieval-*.json'))


def test_output_file_is_preserved_when_directory_is_required(tmp_path,capsys):
    existing=tmp_path/'keep.txt';existing.write_text('preserve')
    assert drill.main(['--output-dir',str(existing)])==1
    assert existing.read_text()=='preserve' and not json.loads(capsys.readouterr().out)['passed']


def test_portable_script_runs_from_unrelated_directory_without_configuration(tmp_path):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_retrieval_drill.py'
    response=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'saved reports')],
        cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['steps_passed']==18 and not response.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
