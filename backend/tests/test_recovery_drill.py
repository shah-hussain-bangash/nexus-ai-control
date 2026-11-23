from contextlib import closing
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import httpx
import pytest
from nexus import recovery_drill as drill,backup as backup_module
from nexus.config import Settings


def test_recovered_api_preserves_operator_data_key_and_module_views(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private operator database')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY','private operator key sentinel')
    def forbidden(*args,**kwargs):pytest.fail('Operator configuration, PostgreSQL subprocess or external HTTP used')
    monkeypatch.setattr(Settings,'from_env',forbidden);monkeypatch.setattr(backup_module.subprocess,'run',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    original=(drill.sealed.os,drill.sealed.tempfile,logging.getLogger('nexus.http').disabled)
    result=drill.run_drill(tmp_path/'disposable')
    assert result['passed'] and len(result['steps'])==31 and all(row['passed'] for row in result['steps'])
    assert result['synthetic_api_exercised'] and result['source_account_count']==3
    assert not any(result[field] for field in ('active_database_restored','postgresql_restore_verified','customer_acceptance','production_ready'))
    assert (drill.sealed.os,drill.sealed.tempfile,logging.getLogger('nexus.http').disabled)==original
    assert os.environ['NEXUS_BACKUP_ENCRYPTION_KEY']=='private operator key sentinel'
    assert private.read_bytes()==b'private operator database' and envfile.read_text()=='NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n'
    assert 'private operator key sentinel' not in json.dumps(result)


def test_existing_workspace_not_reused(tmp_path):
    root=tmp_path/'existing';root.mkdir();sentinel=root/'control.db';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):drill.run_drill(root)
    assert sentinel.read_bytes()==b'preserve' and list(root.iterdir())==[sentinel]


def test_unique_safe_reports_only_after_plaintext_and_key_cleanup(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out);assert summary['passed'] and summary['steps_passed']==31
        result=json.loads(Path(summary['report']).read_text(encoding='utf-8'))
        assert set(result)=={'format','format_version','release','schema_version','created_at_utc','connector_mode','key_mode',
            'passed','synthetic_api_exercised','active_database_restored','postgresql_restore_verified','customer_acceptance',
            'production_ready','steps','boundary','source_account_count'}
        assert result['format']=='nexus-synthetic-recovery-drill' and result['boundary']==drill.BOUNDARY
        assert all(set(row)=={'id','passed'} for row in result['steps'])
        assert not any(text in json.dumps(result) for text in ('password','@nexus.local','sha256','control.sqlite3','nexus_session','NEXUS_BACKUP_ENCRYPTION_KEY'))
    assert len(list(output.iterdir()))==2 and all(path.suffix=='.json' for path in output.iterdir())


def test_bypassed_authentication_rejection_cannot_pass(tmp_path,monkeypatch):
    monkeypatch.setattr(drill.sealed,'recover_encrypted_sqlite',lambda *args:{'isolated_copy_created':True})
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='wrong_key_creates_no_recovery_directory'


def test_changed_recovery_records_cannot_pass(tmp_path,monkeypatch):
    original=drill.sealed.recover_encrypted_sqlite
    def changed(archive,target):
        result=original(archive,target)
        with closing(sqlite3.connect(target/'control.sqlite3')) as db:
            db.execute("UPDATE users SET name='Altered fixture'");db.commit()
        return result
    monkeypatch.setattr(drill.sealed,'recover_encrypted_sqlite',changed)
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='all_control_records_recovered'


def test_accidentally_reopening_source_instead_of_copy_is_detected(tmp_path,monkeypatch):
    original=drill.create_app;settings=[]
    def wrong_binding(config):
        settings.append(config)
        return original(settings[0])
    monkeypatch.setattr(drill,'create_app',wrong_binding)
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='source_records_and_sessions_unchanged'


def test_recovered_api_permission_failure_is_detected(tmp_path,monkeypatch):
    original=drill.TestClient.post
    def broken(client,url,*args,**kwargs):
        response=original(client,url,*args,**kwargs)
        if url=='/v1/workbench' and response.status_code==403:return httpx.Response(201,json={})
        return response
    monkeypatch.setattr(drill.TestClient,'post',broken)
    result=drill.run_drill(tmp_path/'disposable')
    assert not result['passed'] and result['failure']=='recovered_auditor_cannot_write'


def test_private_failure_hidden_and_module_views_restored(tmp_path,capsys,monkeypatch):
    def broken(*args):raise ValueError('private recovery exception sentinel')
    monkeypatch.setattr(drill.sealed,'recover_encrypted_sqlite',broken)
    original=(drill.sealed.os,drill.sealed.tempfile,logging.getLogger('nexus.http').disabled)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private recovery exception sentinel' not in captured.out+captured.err
    summary=json.loads(captured.out);assert not summary['passed']
    saved=Path(summary['report']).read_text(encoding='utf-8')
    assert 'private recovery exception sentinel' not in saved and json.loads(saved)['failure']=='isolated_recovery_drill_could_not_finish'
    assert list(output.iterdir())==[Path(summary['report'])]
    assert (drill.sealed.os,drill.sealed.tempfile,logging.getLogger('nexus.http').disabled)==original


def test_report_write_failure_cannot_claim_success(tmp_path,capsys,monkeypatch):
    original=Path.open
    def blocked(path,*args,**kwargs):
        if path.name.startswith('synthetic-recovery-'):raise OSError('private report path')
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
    assert not json.loads(captured.out)['passed'] and not list(output.glob('synthetic-recovery-*.json'))


def test_portable_entry_ignores_unrelated_configuration(tmp_path,monkeypatch):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY','invalid private operator key')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_recovery_drill.py'
    response=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'saved reports')],cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['steps_passed']==31 and not response.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
