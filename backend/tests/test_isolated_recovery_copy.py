import base64
from contextlib import closing,contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import pytest
from nexus import encrypted_backup as recovery,cli
from nexus.backup import inspect_backup
from nexus.backup_drill import records,seal_fixture
from nexus.config import Settings
from nexus.db import database,migrate,CURRENT_SCHEMA


@pytest.fixture
def archive(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir()
    control=source/'control.db';business=source/'business.db'
    settings=Settings(database_url='sqlite:///'+control.as_posix(),mock_database=str(business))
    engine,factory=database(settings.database_url)
    try:migrate(engine,factory);cli.seed(factory,'Disposable-Recovery-Password-123!')
    finally:engine.dispose()
    with closing(sqlite3.connect(business)) as db:
        db.execute('CREATE TABLE fixture (id INTEGER PRIMARY KEY,value TEXT)')
        db.execute("INSERT INTO fixture VALUES (1,'disposable business record')");db.commit()
    key=b'k'*32;monkeypatch.setenv(recovery.KEY_ENV,base64.b64encode(key).decode())
    path=tmp_path/'backup.enc';recovery.encrypted_backup(settings,path,True)
    return {'path':path,'control':control,'business':business,'key':key,'blob':path.read_bytes(),
        'control_records':records(control),'business_records':records(business)}


def test_authenticated_copy_preserves_all_fixture_records_without_activation(tmp_path,archive):
    target=tmp_path/'isolated'
    result=recovery.recover_encrypted_sqlite(archive['path'],target)
    assert result['isolated_copy_created'] and result['authenticated'] and result['files']==3
    assert not any(result[field] for field in ('active_data_overwritten','application_started','restore_verified','postgresql_restore_verified'))
    assert {p.name for p in target.iterdir()}=={'manifest.json','control.sqlite3','business.sqlite3'}
    assert records(target/'control.sqlite3')==archive['control_records']
    assert records(target/'business.sqlite3')==archive['business_records']
    assert records(archive['control'])==archive['control_records'] and archive['path'].read_bytes()==archive['blob']
    assert inspect_backup(target)['checksums_valid'] and not list(tmp_path.glob('nexus-restore-inspection-*'))


@pytest.mark.parametrize('existing',['empty_directory','occupied_directory','file','input_archive'])
def test_existing_destination_is_never_replaced(tmp_path,archive,existing):
    target=tmp_path/'occupied'
    if existing=='input_archive':target=archive['path']
    elif existing=='file':target.write_bytes(b'preserve private fixture')
    else:
        target.mkdir()
        if existing=='occupied_directory':(target/'keep.txt').write_bytes(b'preserve private fixture')
    before={p.name:p.read_bytes() for p in target.iterdir()} if target.is_dir() else target.read_bytes()
    with pytest.raises(FileExistsError):recovery.recover_encrypted_sqlite(archive['path'],target)
    assert ({p.name:p.read_bytes() for p in target.iterdir()} if target.is_dir() else target.read_bytes())==before


def test_dangling_destination_link_is_not_followed(tmp_path,archive):
    target=tmp_path/'link';outside=tmp_path/'not-created'
    try:target.symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('Creating symlinks requires Windows privileges on this host.')
    with pytest.raises(FileExistsError):recovery.recover_encrypted_sqlite(archive['path'],target)
    assert target.is_symlink() and not outside.exists()


@pytest.mark.parametrize('fault',['wrong_key','tampered','truncated','empty_manifest','unsafe_member'])
def test_invalid_input_never_creates_destination(tmp_path,archive,monkeypatch,fault):
    path=archive['path'];blob=archive['blob']
    if fault=='wrong_key':monkeypatch.setenv(recovery.KEY_ENV,base64.b64encode(b'w'*32).decode())
    elif fault=='tampered':path.write_bytes(blob[:-20]+bytes([blob[-20]^1])+blob[-19:])
    elif fault=='truncated':path.write_bytes(blob[:20])
    elif fault=='empty_manifest':seal_fixture(path,archive['key'],[('manifest.json',json.dumps({'kind':'sqlite','schema':CURRENT_SCHEMA,'files':[]}).encode())])
    else:seal_fixture(path,archive['key'],[('../outside-fixture',b'fixture')])
    target=tmp_path/'isolated'
    with pytest.raises(RuntimeError):recovery.recover_encrypted_sqlite(path,target)
    assert not target.exists() and not list(tmp_path.glob('nexus-restore-inspection-*'))
    assert records(archive['control'])==archive['control_records']


def test_postgresql_is_rejected_before_destination_creation(tmp_path,archive):
    data=b'PGDMP-synthetic-container-only'
    manifest={'kind':'postgresql','schema':CURRENT_SCHEMA,'files':[{'name':'control.dump','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}
    seal_fixture(archive['path'],archive['key'],[('manifest.json',json.dumps(manifest).encode()),('control.dump',data)])
    target=tmp_path/'isolated'
    with pytest.raises(RuntimeError,match='SQLite only'):recovery.recover_encrypted_sqlite(archive['path'],target)
    assert not target.exists()


def test_missing_parent_is_not_created_implicitly(tmp_path,archive):
    parent=tmp_path/'missing-parent'
    with pytest.raises(RuntimeError,match='parent'):recovery.recover_encrypted_sqlite(archive['path'],parent/'isolated')
    assert not parent.exists()


def test_destination_created_during_authentication_is_preserved(tmp_path,archive,monkeypatch):
    target=tmp_path/'raced';original=recovery.authenticated_snapshot
    @contextmanager
    def concurrent(*args,**kwargs):
        with original(*args,**kwargs) as snapshot:
            target.mkdir();(target/'keep.txt').write_bytes(b'concurrent private fixture')
            yield snapshot
    monkeypatch.setattr(recovery,'authenticated_snapshot',concurrent)
    with pytest.raises(FileExistsError):recovery.recover_encrypted_sqlite(archive['path'],target)
    assert [p.name for p in target.iterdir()]==['keep.txt'] and (target/'keep.txt').read_bytes()==b'concurrent private fixture'


@pytest.mark.parametrize('fault',['copy','fsync','verification'])
def test_failed_export_cannot_report_success_or_modify_source(tmp_path,archive,monkeypatch,fault):
    target=tmp_path/'isolated'
    if fault=='copy':
        original=recovery.shutil.copyfileobj
        def failed(*args,**kwargs):
            if target.exists():raise OSError('private copy error sentinel')
            return original(*args,**kwargs)
        monkeypatch.setattr(recovery.shutil,'copyfileobj',failed)
    elif fault=='fsync':
        def failed(*args):raise OSError('private fsync error sentinel')
        monkeypatch.setattr(recovery.os,'fsync',failed)
    else:
        original=recovery.inspect_backup
        def failed(path,**kwargs):
            if Path(path)==target:return {'checksums_valid':False,'sqlite_integrity_valid':True}
            return original(path,**kwargs)
        monkeypatch.setattr(recovery,'inspect_backup',failed)
    with pytest.raises(RuntimeError,match='partial new directory') as error:
        recovery.recover_encrypted_sqlite(archive['path'],target)
    assert 'sentinel' not in str(error.value) and target.is_dir()
    assert records(archive['control'])==archive['control_records'] and archive['path'].read_bytes()==archive['blob']
    assert not list(tmp_path.glob('nexus-restore-inspection-*'))
    if fault!='verification':assert not (target/'manifest.json').exists()


def test_cli_works_without_loading_broken_active_settings(tmp_path,archive,monkeypatch,capsys):
    cwd=tmp_path/'broken-config';cwd.mkdir();env=cwd/'.env';env.write_text('NEXUS_DATABASE_URL=invalid\nNEXUS_MODE=pilot\n')
    monkeypatch.chdir(cwd)
    def forbidden(*args):pytest.fail('Active app settings were loaded during isolated recovery')
    monkeypatch.setattr(Settings,'from_env',forbidden)
    target=tmp_path/'isolated'
    monkeypatch.setattr(sys,'argv',['nexus.cli','recover-encrypted-sqlite','--source',str(archive['path']),'--destination',str(target)])
    cli.main();result=json.loads(capsys.readouterr().out)
    assert result['isolated_copy_created'] and not result['application_started']
    assert env.read_text()=='NEXUS_DATABASE_URL=invalid\nNEXUS_MODE=pilot\n'


def test_copy_without_optional_business_snapshot(tmp_path,archive):
    source=tmp_path/'control-only.enc'
    settings=Settings(database_url='sqlite:///'+archive['control'].as_posix(),mock_database=str(tmp_path/'absent.db'))
    recovery.encrypted_backup(settings,source,True)
    target=tmp_path/'isolated'
    result=recovery.recover_encrypted_sqlite(source,target)
    assert result['files']==2 and {p.name for p in target.iterdir()}=={'manifest.json','control.sqlite3'}
    assert records(target/'control.sqlite3')==archive['control_records']


def test_unexpected_destination_file_is_preserved_and_prevents_success(tmp_path,archive,monkeypatch):
    target=tmp_path/'isolated';original=recovery.shutil.copyfileobj
    def concurrent(*args,**kwargs):
        result=original(*args,**kwargs)
        if target.is_dir():(target/'keep.txt').write_bytes(b'concurrent private fixture')
        return result
    monkeypatch.setattr(recovery.shutil,'copyfileobj',concurrent)
    with pytest.raises(RuntimeError,match='partial new directory'):recovery.recover_encrypted_sqlite(archive['path'],target)
    assert (target/'keep.txt').read_bytes()==b'concurrent private fixture'
    assert records(archive['control'])==archive['control_records']
