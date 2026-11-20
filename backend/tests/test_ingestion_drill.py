import json
from pathlib import Path
import subprocess
import sys
import httpx
import pytest
from nexus import ingestion, ingestion_drill as drill
from nexus.business_connector import HTTPBusiness
from nexus.config import Settings


def test_real_parser_drill_ignores_operator_config_and_network(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private operator database')
    config=tmp_path/'.env';config.write_text('NEXUS_MODE=pilot\nNEXUS_SECRET=private-setting\n')
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_INGESTION_OCR_ENABLED','1');monkeypatch.setenv('NEXUS_LIVE_INFERENCE','1')
    monkeypatch.setenv('NEXUS_BUSINESS_CONNECTOR','http')
    def forbidden(*args,**kwargs):pytest.fail('Operator configuration or external transport used')
    monkeypatch.setattr(Settings,'from_env',forbidden);monkeypatch.setattr(HTTPBusiness,'request',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    original=ingestion.subprocess.Popen;files=[]
    def launch(args,**kwargs):
        assert args[1:3]==['-m','nexus.extract_worker']
        assert not any(key.startswith('NEXUS_') for key in kwargs['env'])
        files.extend(Path(arg) for arg in args[-3:]);return original(args,**kwargs)
    monkeypatch.setattr(ingestion.subprocess,'Popen',launch)
    before=(private.read_bytes(),config.read_bytes())
    result=drill.run_drill(tmp_path/'disposable')
    assert result['passed'] and len(result['steps'])==25 and all(row['passed'] for row in result['steps'])
    assert len(files)==15 and all(not path.exists() for path in files)
    assert drill.docx_fixture()==drill.docx_fixture()
    assert not result['customer_acceptance'] and not result['production_ready']
    assert (private.read_bytes(),config.read_bytes())==before


def test_existing_directory_cannot_be_reused(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();sentinel=existing/'control.db';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):drill.run_drill(existing)
    assert sentinel.read_bytes()==b'preserve' and list(existing.iterdir())==[sentinel]


def test_cli_repeats_without_private_reports_or_leftover_databases(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out);assert summary['passed'] and summary['steps_passed']==25
        report=json.loads(Path(summary['report']).read_text(encoding='utf-8'))
        assert report['format']=='nexus-synthetic-ingestion-drill' and report['boundary']==drill.BOUNDARY
        assert all(set(row)=={'id','passed'} for row in report['steps'])
        assert not any(value in json.dumps(report) for value in ['@drill.invalid','content_base64','password','cookie',
            'Synthetic procurement evidence','إِدَارَة'])
    assert len(list(output.iterdir()))==2 and not list(output.rglob('*.db'))
    assert not list(output.glob('.ingestion-*'))


@pytest.mark.parametrize('broken',['parser','worker'])
def test_broken_extraction_cannot_pass_drill(tmp_path,monkeypatch,broken):
    if broken=='parser':monkeypatch.setattr(ingestion,'extract_file',lambda *args:{'text':'wrong synthetic extraction','info':{'method':'docx-text'}})
    else:monkeypatch.setattr(drill,'run_ingestion_once',lambda *args:False)
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='real_docx_extraction_requires_review'
    assert result['steps'][-1]=={'id':'real_docx_extraction_requires_review','passed':False}


def test_private_error_is_hidden_and_failed_run_is_cleaned(tmp_path,capsys,monkeypatch):
    def broken(*args):raise RuntimeError('private-extraction-credential')
    monkeypatch.setattr(drill,'run_ingestion_once',broken)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private-extraction-credential' not in captured.out+captured.err
    summary=json.loads(captured.out);assert not summary['passed']
    text=Path(summary['report']).read_text(encoding='utf-8')
    assert 'private-extraction-credential' not in text and json.loads(text)['failure']=='isolated_drill_could_not_finish'
    assert not list(output.rglob('*.db'))


def test_report_write_failure_and_existing_file_cannot_claim_success(tmp_path,capsys,monkeypatch):
    existing=tmp_path/'keep.txt';existing.write_text('preserve')
    assert drill.main(['--output-dir',str(existing)])==1
    assert not json.loads(capsys.readouterr().out)['passed'] and existing.read_text()=='preserve'
    original=Path.open
    def blocked(path,*args,**kwargs):
        if path.name.startswith('synthetic-ingestion-'):raise OSError('private path details')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',blocked)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private path details' not in captured.out+captured.err
    assert not json.loads(captured.out)['passed'] and not list(output.iterdir())


def test_cleanup_failure_cannot_claim_success(tmp_path,capsys,monkeypatch):
    class BrokenCleanup:
        def __init__(self,**kw):self.root=Path(kw['dir'])/'cleanup-fixture';self.root.mkdir()
        def __enter__(self):return str(self.root)
        def __exit__(self,*args):raise OSError('private cleanup detail')
    monkeypatch.setattr(drill,'TemporaryDirectory',BrokenCleanup)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private cleanup detail' not in captured.out+captured.err
    assert not json.loads(captured.out)['passed'] and not list(output.glob('synthetic-ingestion-*.json'))


def test_portable_entry_point_from_unrelated_directory(tmp_path):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_ingestion_drill.py'
    response=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'saved reports')],
        cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['steps_passed']==25 and not response.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
