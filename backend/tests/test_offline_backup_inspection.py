"""Backup inspection must not depend on, initialize or modify an active app."""
import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from nexus import cli
from nexus.backup_drill import seal_fixture
from nexus.encrypted_backup import KEY_ENV


@pytest.fixture
def offline(tmp_path,monkeypatch):
    root=tmp_path/'offline';root.mkdir();snapshot=root/'snapshot';snapshot.mkdir()
    control=snapshot/'control.sqlite3'
    with closing(sqlite3.connect(control)) as db:
        db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO schema_versions VALUES (11)');db.commit()
    data=control.read_bytes();body=json.dumps({'kind':'sqlite','schema':11,'files':[{
        'name':'control.sqlite3','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}).encode()
    (snapshot/'manifest.json').write_bytes(body)
    key=b'k'*32;archive=root/'snapshot.enc'
    seal_fixture(archive,key,[('manifest.json',body),('control.sqlite3',data)])
    (root/'.env').write_text('NEXUS_MODE=broken\nNEXUS_SECRET=private-fixture-sentinel\n'+KEY_ENV+'='+base64.b64encode(b'd'*32).decode()+'\n')
    monkeypatch.chdir(root);monkeypatch.setenv('NEXUS_MODE','broken')
    monkeypatch.setenv(KEY_ENV,base64.b64encode(key).decode())
    def forbidden(*args,**kwargs):pytest.fail('Offline inspection touched operator settings or application initialization')
    monkeypatch.setattr(cli.Settings,'from_env',forbidden)
    for name in ('database','migrate','seed'):monkeypatch.setattr(cli,name,forbidden)
    return root,snapshot,archive


def files(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('operation',['inspect-backup','inspect-encrypted-backup'])
@pytest.mark.parametrize('flag',['--source','--destination'])
def test_offline_inspection_accepts_new_and_legacy_inputs(offline,monkeypatch,capsys,operation,flag):
    root,snapshot,archive=offline;before=files(root)
    source=archive if operation=='inspect-encrypted-backup' else snapshot
    monkeypatch.setattr(sys,'argv',['nexus',operation,flag,str(source)])
    cli.main();text=capsys.readouterr().out;result=json.loads(text)
    assert result['checksums_valid'] and result['sqlite_integrity_valid'] and not result['postgresql_restore_verified']
    if operation=='inspect-encrypted-backup':assert result['authenticated'] and not result['active_data_overwritten']
    assert 'private-fixture-sentinel' not in text and files(root)==before


@pytest.mark.parametrize('operation',['inspect-backup','inspect-encrypted-backup'])
@pytest.mark.parametrize('arguments',[[],['--source','one','--destination','two']])
def test_inspection_requires_one_input_before_settings(offline,monkeypatch,capsys,operation,arguments):
    root,_,_=offline;before=files(root)
    monkeypatch.setattr(sys,'argv',['nexus',operation,*arguments])
    with pytest.raises(SystemExit) as error:cli.main()
    assert error.value.code==2 and 'Choose exactly one' in capsys.readouterr().err and files(root)==before


def test_encrypted_inspection_never_loads_a_key_from_dotenv(offline,monkeypatch,capsys):
    root,_,archive=offline;before=files(root);monkeypatch.delenv(KEY_ENV)
    monkeypatch.setattr(sys,'argv',['nexus','inspect-encrypted-backup','--source',str(archive)])
    with pytest.raises(RuntimeError,match='Provision NEXUS_BACKUP_ENCRYPTION_KEY'):cli.main()
    assert not capsys.readouterr().out and files(root)==before


def test_wrong_process_key_does_not_fall_back_to_settings(offline,monkeypatch,capsys):
    root,_,archive=offline;before=files(root);monkeypatch.setenv(KEY_ENV,base64.b64encode(b'w'*32).decode())
    monkeypatch.setattr(sys,'argv',['nexus','inspect-encrypted-backup','--source',str(archive)])
    with pytest.raises(RuntimeError,match='authentication'):cli.main()
    assert not capsys.readouterr().out and files(root)==before


@pytest.mark.parametrize('operation',['backup','backup-encrypted'])
def test_backup_creation_still_requires_operator_settings(offline,monkeypatch,operation):
    root,_,_=offline;before=files(root);calls=[]
    def invalid_settings():calls.append(True);raise ValueError('invalid fixture settings')
    monkeypatch.setattr(cli.Settings,'from_env',invalid_settings)
    monkeypatch.setattr(sys,'argv',['nexus',operation,'--destination',str(root/'new-backup'),'--quiesced'])
    with pytest.raises(ValueError,match='invalid fixture settings'):cli.main()
    assert calls==[True] and files(root)==before


@pytest.mark.parametrize('operation',['inspect-backup','inspect-encrypted-backup'])
def test_real_cli_inspects_with_broken_configuration_without_initializing(offline,operation):
    root,snapshot,archive=offline;before=files(root);environment=os.environ.copy()
    environment['PYTHONPATH']=str(Path(cli.__file__).resolve().parents[1])
    environment['NEXUS_DATABASE_URL']='unsupported-fixture://no-database'
    source=archive if operation=='inspect-encrypted-backup' else snapshot
    result=subprocess.run([sys.executable,'-m','nexus.cli',operation,'--source',str(source)],
        cwd=root,env=environment,capture_output=True,text=True,timeout=30)
    assert result.returncode==0 and json.loads(result.stdout)['checksums_valid']
    assert 'private-fixture-sentinel' not in result.stdout+result.stderr and files(root)==before
