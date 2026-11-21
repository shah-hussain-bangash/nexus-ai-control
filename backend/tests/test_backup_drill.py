from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import httpx
import pytest
from nexus import backup_drill as drill,backup as backup_module
from nexus.config import Settings


def test_full_drill_ignores_operator_data_and_key_and_restores_module_views(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private operator database')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY','private operator key sentinel')
    def forbidden(*args,**kwargs):pytest.fail('Operator settings, PostgreSQL subprocess or network used')
    monkeypatch.setattr(Settings,'from_env',forbidden);monkeypatch.setattr(backup_module.subprocess,'run',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    original=(drill.sealed.os,drill.sealed.tempfile)
    report=drill.run_drill(tmp_path/'disposable')
    assert report['passed'] and len(report['steps'])==27 and all(row['passed'] for row in report['steps'])
    assert report['successful_backup_count']==2 and report['source_account_count']==3
    assert not any(report[field] for field in ('customer_acceptance','production_ready','live_restore_performed','postgresql_restore_verified'))
    assert (drill.sealed.os,drill.sealed.tempfile)==original
    assert os.environ['NEXUS_BACKUP_ENCRYPTION_KEY']=='private operator key sentinel'
    assert private.read_bytes()==b'private operator database' and envfile.read_text()=='NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n'
    assert 'private operator key sentinel' not in json.dumps(report)


def test_existing_directory_is_not_reused(tmp_path):
    existing=tmp_path/'existing';existing.mkdir();sentinel=existing/'control.db';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):drill.run_drill(existing)
    assert sentinel.read_bytes()==b'preserve' and list(existing.iterdir())==[sentinel]


def test_cli_unique_reports_contain_only_safe_metadata_after_artifact_cleanup(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out);assert summary['passed'] and summary['steps_passed']==27
        report=json.loads(Path(summary['report']).read_text(encoding='utf-8'))
        assert set(report)=={'format','format_version','release','schema_version','created_at_utc','connector_mode','key_mode',
            'passed','customer_acceptance','production_ready','live_restore_performed','postgresql_restore_verified','steps','boundary',
            'successful_backup_count','source_account_count'}
        assert report['format']=='nexus-synthetic-backup-drill' and report['boundary']==drill.BOUNDARY
        assert all(set(row)=={'id','passed'} for row in report['steps'])
        assert not any(text in json.dumps(report) for text in ['password','@nexus.local','sha256','control.sqlite3','NEXUS_BACKUP_ENCRYPTION_KEY'])
    assert len(list(output.iterdir()))==2
    assert not any(list(output.rglob(pattern)) for pattern in ('*.db','*.sqlite3','*.enc','.backup-*'))


@pytest.mark.parametrize('broken,expected',[
    ('checksum','plaintext_tampering_rejected'),('authentication','wrong_encryption_key_rejected'),
])
def test_broken_inspection_cannot_pass(tmp_path,monkeypatch,broken,expected):
    if broken=='checksum':monkeypatch.setattr(drill,'inspect_backup',lambda *args:{'checksums_valid':True,'sqlite_integrity_valid':True,'postgresql_restore_verified':False})
    else:monkeypatch.setattr(drill.sealed,'inspect_encrypted_backup',lambda *args:{'authenticated':True,'checksums_valid':True,'sqlite_integrity_valid':True,'active_data_overwritten':False,'postgresql_restore_verified':False})
    original=(drill.sealed.os,drill.sealed.tempfile)
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']==expected and report['steps'][-1]=={'id':expected,'passed':False}
    assert (drill.sealed.os,drill.sealed.tempfile)==original


def test_source_record_mutation_is_detected(tmp_path,monkeypatch):
    original=drill.sealed.encrypted_backup
    def changed(settings,*args,**kwargs):
        result=original(settings,*args,**kwargs)
        with closing(sqlite3.connect(Path(settings.database_url.removeprefix('sqlite:///')))) as db:
            db.execute("UPDATE users SET name='Changed disposable fixture' WHERE role='owner'");db.commit()
        return result
    monkeypatch.setattr(drill.sealed,'encrypted_backup',changed)
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']=='source_records_unchanged_after_all_checks'


def test_unsafe_extraction_is_not_hidden_as_an_expected_rejection(tmp_path,monkeypatch):
    monkeypatch.setattr(drill.sealed,'validated_members',lambda tar:tar.getmembers())
    original=(drill.sealed.os,drill.sealed.tempfile)
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']=='unsafe_layout_was_extracted'
    assert (drill.sealed.os,drill.sealed.tempfile)==original


def test_private_failure_details_are_hidden_and_cleanup_runs(tmp_path,capsys,monkeypatch):
    def broken(*args):raise ValueError('private backup exception sentinel')
    monkeypatch.setattr(drill,'backup',broken)
    output=tmp_path/'reports';assert drill.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private backup exception sentinel' not in captured.out+captured.err
    summary=json.loads(captured.out);assert not summary['passed']
    report=Path(summary['report']).read_text(encoding='utf-8')
    assert 'private backup exception sentinel' not in report and json.loads(report)['failure']=='isolated_drill_could_not_finish'
    assert not list(output.rglob('*.db'))


def test_report_write_failure_cannot_claim_success(tmp_path,capsys,monkeypatch):
    original=Path.open
    def blocked(path,*args,**kwargs):
        if path.name.startswith('synthetic-backup-'):raise OSError('private report path')
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
    assert not json.loads(captured.out)['passed'] and not list(output.glob('synthetic-backup-*.json'))


def test_portable_entry_from_unrelated_directory(tmp_path,monkeypatch):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY','invalid private operator key')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_backup_drill.py'
    response=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'saved reports')],cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['steps_passed']==27 and not response.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
