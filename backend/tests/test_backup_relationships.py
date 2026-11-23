"""Checksummed, physically valid SQLite files can still contain invalid links."""
import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import pytest
from nexus.backup import backup,inspect_backup
from nexus.backup_drill import seal_fixture
from nexus.config import Settings
from nexus import encrypted_backup as sealed


def database_file(path,kind='orphan'):
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO schema_versions VALUES (11)')
        db.execute('CREATE TABLE private_parent_sentinel (id INTEGER PRIMARY KEY, label TEXT)')
        if kind=='mismatch':
            db.execute('CREATE TABLE private_child_sentinel (id INTEGER PRIMARY KEY, parent TEXT REFERENCES private_parent_sentinel(label))')
        elif kind=='without_rowid':
            db.execute('CREATE TABLE private_child_sentinel (id TEXT PRIMARY KEY, parent INTEGER REFERENCES private_parent_sentinel(id)) WITHOUT ROWID')
            db.execute("INSERT INTO private_child_sentinel VALUES ('fixture',99)")
        else:
            db.execute('CREATE TABLE private_child_sentinel (id INTEGER PRIMARY KEY, parent INTEGER REFERENCES private_parent_sentinel(id))')
            if kind=='valid':db.execute("INSERT INTO private_parent_sentinel VALUES (99,'fixture')")
            db.execute('INSERT INTO private_child_sentinel VALUES (1,?)',(None if kind=='nullable' else 99,))
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()==('ok',)


def snapshot(root,member,kind):
    root.mkdir()
    database_file(root/'control.sqlite3',kind if member=='control.sqlite3' else 'valid')
    if member=='business.sqlite3':database_file(root/member,kind)
    files=[{'name':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(root.iterdir())]
    (root/'manifest.json').write_text(json.dumps({'kind':'sqlite','schema':11,'files':files}),encoding='utf-8')


@pytest.mark.parametrize('member',['control.sqlite3','business.sqlite3'])
@pytest.mark.parametrize('immutable',[False,True])
@pytest.mark.parametrize('kind',['orphan','mismatch','without_rowid'])
def test_inspection_rejects_invalid_links_despite_matching_checksums(tmp_path,member,immutable,kind):
    root=tmp_path/'backup';snapshot(root,member,kind)
    before={path.name:path.read_bytes() for path in root.iterdir()}
    with pytest.raises(RuntimeError,match='foreign-key') as error:inspect_backup(root,immutable_sqlite=immutable)
    assert 'private_parent_sentinel' not in str(error.value) and 'private_child_sentinel' not in str(error.value)
    assert {path.name:path.read_bytes() for path in root.iterdir()}==before


@pytest.mark.parametrize('member',['control.sqlite3','business.sqlite3'])
@pytest.mark.parametrize('kind',['valid','nullable'])
def test_valid_and_optional_relationships_remain_readable(tmp_path,member,kind):
    root=tmp_path/'backup';snapshot(root,member,kind)
    before={path.name:path.read_bytes() for path in root.iterdir()}
    for immutable in (False,True):
        result=inspect_backup(root,immutable_sqlite=immutable)
        assert result['checksums_valid'] and result['sqlite_integrity_valid'] and not result['postgresql_restore_verified']
    assert {path.name:path.read_bytes() for path in root.iterdir()}==before


@pytest.mark.parametrize('member',['control.sqlite3','business.sqlite3'])
def test_plaintext_backup_cannot_report_invalid_source_as_success(tmp_path,member):
    source=tmp_path/'source';snapshot(source,member,'orphan')
    before={path.name:path.read_bytes() for path in source.iterdir()}
    settings=Settings(database_url='sqlite:///'+(source/'control.sqlite3').as_posix(),mock_database=str(source/'business.sqlite3'))
    destination=tmp_path/'new-backup'
    with pytest.raises(RuntimeError,match='foreign-key'):backup(settings,destination,True)
    assert not (destination/'manifest.json').exists()
    assert {path.name:path.read_bytes() for path in source.iterdir()}==before
    # As with existing snapshot failures, incomplete plaintext files may remain;
    # backup does not delete unrelated files or retry into the same directory.
    with pytest.raises(FileExistsError):backup(settings,destination,True)


@pytest.mark.parametrize('member',['control.sqlite3','business.sqlite3'])
def test_encrypted_backup_rejects_invalid_source_and_cleans_temporary_files(tmp_path,member,monkeypatch):
    source=tmp_path/'source';snapshot(source,member,'orphan')
    settings=Settings(database_url='sqlite:///'+(source/'control.sqlite3').as_posix(),mock_database=str(source/'business.sqlite3'))
    monkeypatch.setenv(sealed.KEY_ENV,base64.b64encode(b'k'*32).decode())
    before={path.name:path.read_bytes() for path in source.iterdir()};destination=tmp_path/'backup.enc'
    with pytest.raises(RuntimeError,match='foreign-key'):sealed.encrypted_backup(settings,destination,True)
    assert not destination.exists() and not list(tmp_path.glob('.nexus-private-*'))
    assert {path.name:path.read_bytes() for path in source.iterdir()}==before


@pytest.mark.parametrize('member',['control.sqlite3','business.sqlite3'])
def test_authenticated_invalid_snapshot_cannot_allocate_recovery_directory(tmp_path,member,monkeypatch):
    source=tmp_path/'source';snapshot(source,member,'orphan')
    key=b'k'*32;monkeypatch.setenv(sealed.KEY_ENV,base64.b64encode(key).decode())
    archive=tmp_path/'invalid.enc';seal_fixture(archive,key,[(path.name,path.read_bytes()) for path in source.iterdir()])
    before=archive.read_bytes();destination=tmp_path/'recovered'
    def private_temp(**options):
        options.setdefault('dir',tmp_path)
        return TemporaryDirectory(**options)
    monkeypatch.setattr(sealed,'tempfile',SimpleNamespace(TemporaryDirectory=private_temp))
    with pytest.raises(RuntimeError,match='foreign-key'):sealed.inspect_encrypted_backup(archive)
    with pytest.raises(RuntimeError,match='foreign-key'):sealed.recover_encrypted_sqlite(archive,destination)
    assert not destination.exists() and archive.read_bytes()==before
    assert not list(tmp_path.glob('nexus-restore-inspection-*'))
