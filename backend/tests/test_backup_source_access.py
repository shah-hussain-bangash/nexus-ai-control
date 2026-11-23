"""Backup source reads must never silently create a replacement database."""
from contextlib import closing
import base64
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest
from nexus import backup,encrypted_backup as sealed
from nexus.backup_drill import LocalKeyOS


def create_source(path):
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE marker (id INTEGER PRIMARY KEY,note TEXT)')
        db.execute("INSERT INTO marker VALUES (1,'disposable source')");db.commit()


def marker(path):
    with closing(sqlite3.connect(path)) as db:return db.execute('SELECT * FROM marker').fetchall()


def test_source_connection_is_read_only_with_escaped_absolute_uri(tmp_path,monkeypatch):
    source=tmp_path/'source # % العربية.db';create_source(source);before=source.read_bytes()
    original=sqlite3.connect;connections=[]
    def connect(name,**options):
        db=original(name,**options);connections.append((name,options))
        if len(connections)==1:
            with pytest.raises(sqlite3.OperationalError,match='readonly'):db.execute('DELETE FROM marker')
        return db
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(backup.sqlite3,'connect',connect)
    target=tmp_path/'copy.db';backup.sqlite_snapshot(Path(source.name),target)
    assert connections[0]==(source.as_uri()+'?mode=ro',{'uri':True})
    assert source.read_bytes()==before and marker(target)==[(1,'disposable source')]


def test_source_disappearing_after_preflight_is_not_recreated(tmp_path,monkeypatch):
    source=tmp_path/'source.db';create_source(source);target=tmp_path/'copy.db';original=sqlite3.connect;calls=[]
    def disappear(name,**options):
        calls.append(name);source.unlink()
        return original(name,**options)
    monkeypatch.setattr(backup.sqlite3,'connect',disappear)
    with pytest.raises(RuntimeError,match='SQLite snapshot failed') as error:backup.sqlite_snapshot(source,target)
    assert len(calls)==1 and not source.exists() and not target.exists()
    assert error.value.__suppress_context__


@pytest.mark.parametrize('missing',['absent','directory'])
def test_missing_source_never_opens_sqlite_or_creates_destination(tmp_path,monkeypatch,missing):
    source=tmp_path/'source.db';target=tmp_path/'copy.db'
    if missing=='directory':source.mkdir()
    def forbidden(*args,**kwargs):pytest.fail('Invalid source reached SQLite')
    monkeypatch.setattr(backup.sqlite3,'connect',forbidden)
    with pytest.raises(RuntimeError,match='Configured SQLite file is missing'):backup.sqlite_snapshot(source,target)
    assert not target.exists() and (source.is_dir() if missing=='directory' else not source.exists())


def test_sqlite_failure_hides_private_paths_and_details(tmp_path,monkeypatch):
    source=tmp_path/'private-source.db';create_source(source);before=source.read_bytes();target=tmp_path/'copy.db'
    def denied(*args,**kwargs):raise sqlite3.OperationalError('private-source.db private storage error')
    monkeypatch.setattr(backup.sqlite3,'connect',denied)
    with pytest.raises(RuntimeError,match='SQLite snapshot failed') as error:backup.sqlite_snapshot(source,target)
    assert 'private-source.db' not in str(error.value) and 'private storage error' not in str(error.value)
    assert error.value.__suppress_context__ and source.read_bytes()==before and not target.exists()


def test_read_only_snapshot_includes_committed_wal_rows(tmp_path):
    source=tmp_path/'source.db';target=tmp_path/'copy.db'
    with closing(sqlite3.connect(source)) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('CREATE TABLE marker (id INTEGER PRIMARY KEY,note TEXT)')
        writer.execute("INSERT INTO marker VALUES (1,'committed WAL row')");writer.commit()
        wal=Path(str(source)+'-wal');assert wal.is_file() and wal.stat().st_size>0
        before=source.read_bytes();wal_before=wal.read_bytes()
        backup.sqlite_snapshot(source,target)
        assert marker(target)==[(1,'committed WAL row')]
        assert writer.execute('SELECT * FROM marker').fetchall()==[(1,'committed WAL row')]
        assert source.read_bytes()==before and wal.read_bytes()==wal_before


@pytest.mark.parametrize('encrypted',[False,True])
@pytest.mark.parametrize('member',['control','business'])
def test_disappearing_source_cannot_publish_a_successful_backup(tmp_path,monkeypatch,encrypted,member):
    control=tmp_path/'control.db';business=tmp_path/'business.db'
    for source in (control,business):create_source(source)
    with closing(sqlite3.connect(control)) as db:
        db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO schema_versions VALUES (11)');db.commit()
    selected=control if member=='control' else business;moved=tmp_path/'retained-source.db'
    before={p:p.read_bytes() for p in (control,business)};original=sqlite3.connect
    def disappear(name,**options):
        if name==selected.as_uri()+'?mode=ro':selected.rename(moved)
        return original(name,**options)
    monkeypatch.setattr(backup.sqlite3,'connect',disappear)
    monkeypatch.setattr(sealed,'os',LocalKeyOS({sealed.KEY_ENV:base64.b64encode(b'k'*32).decode()}))
    settings=SimpleNamespace(database_url='sqlite:///'+control.as_posix(),mock_database=str(business))
    destination=tmp_path/('backup.enc' if encrypted else 'snapshot')
    with pytest.raises(RuntimeError,match='SQLite snapshot failed'):
        if encrypted:sealed.encrypted_backup(settings,destination,True)
        else:backup.backup(settings,destination,True)
    assert not selected.exists() and moved.read_bytes()==before[selected]
    assert all(p.read_bytes()==value for p,value in before.items() if p!=selected)
    assert not destination.exists() if encrypted else not (destination/'manifest.json').exists()
    assert not list(tmp_path.glob('.nexus-private-*'))
