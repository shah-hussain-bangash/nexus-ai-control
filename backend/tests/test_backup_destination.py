"""A destination's existing directory entry must not redirect a new backup."""
import base64
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import pytest
from nexus.backup import backup,inspect_backup
from nexus.config import Settings
from nexus import encrypted_backup as sealed


@pytest.fixture
def source(tmp_path,monkeypatch):
    path=tmp_path/'source.db'
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO schema_versions VALUES (11)');db.commit()
    monkeypatch.setenv(sealed.KEY_ENV,base64.b64encode(b'k'*32).decode())
    return Settings(database_url='sqlite:///'+path.as_posix(),mock_database=str(tmp_path/'absent-business.db'))


def create(settings,destination,encrypted):
    return sealed.encrypted_backup(settings,destination,True) if encrypted else backup(settings,destination,True)


@pytest.mark.parametrize('encrypted',[False,True])
@pytest.mark.parametrize('kind',['file','empty_directory','occupied_directory','dangling_link','file_link','directory_link'])
def test_existing_leaf_is_preserved_without_reading_source(tmp_path,source,encrypted,kind,monkeypatch):
    target=tmp_path/'backup';outside=tmp_path/'other-target'
    if kind=='file':target.write_bytes(b'preserve existing artifact')
    elif kind in ('empty_directory','occupied_directory'):
        target.mkdir()
        if kind=='occupied_directory':(target/'keep').write_bytes(b'preserve existing artifact')
    else:
        if kind=='file_link':outside.write_bytes(b'preserve linked file')
        if kind=='directory_link':outside.mkdir();(outside/'keep').write_bytes(b'preserve linked directory')
        try:target.symlink_to(outside,target_is_directory=kind=='directory_link' or (kind=='dangling_link' and not encrypted))
        except OSError:pytest.skip('Creating symlinks requires Windows privileges on this host.')
    before={p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*') if p.is_file() and not p.is_symlink()}
    def no_snapshot(*args,**kwargs):pytest.fail('Existing destination reached snapshot creation')
    monkeypatch.setattr('nexus.backup.sqlite_snapshot',no_snapshot)
    with pytest.raises(FileExistsError):create(source,target,encrypted)
    if kind.endswith('link'):assert target.is_symlink()
    else:assert target.exists()
    if kind=='dangling_link':assert not outside.exists()
    after={p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*') if p.is_file() and not p.is_symlink()}
    assert after==before and not list(tmp_path.glob('.nexus-private-*'))


@pytest.mark.parametrize('encrypted',[False,True])
def test_destination_is_not_resolved_before_checking_its_entry(tmp_path,source,encrypted,monkeypatch):
    target=tmp_path/'existing';target.write_bytes(b'preserve')
    original=Path.resolve
    def guarded(path,*args,**kwargs):
        if path==target:pytest.fail('Existing destination was resolved before its entry was rejected')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',guarded)
    with pytest.raises(FileExistsError):create(source,target,encrypted)
    assert target.read_bytes()==b'preserve'


@pytest.mark.parametrize('encrypted',[False,True])
def test_destination_lookup_errors_fail_closed_before_writes(tmp_path,source,encrypted,monkeypatch):
    target=tmp_path/'new-backup';original=Path.lstat
    def denied(path,*args,**kwargs):
        if path==target:raise PermissionError('fixture metadata access denied')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',denied)
    with pytest.raises(PermissionError):create(source,target,encrypted)
    assert not target.exists() and not list(tmp_path.glob('.nexus-private-*'))


@pytest.mark.parametrize('encrypted',[False,True])
def test_new_relative_destination_remains_supported(tmp_path,source,encrypted,monkeypatch):
    monkeypatch.chdir(tmp_path);target=Path('new-backup')
    result=create(source,target,encrypted)
    assert result['backup_created'] and not result['restore_verified']
    if encrypted:assert sealed.inspect_encrypted_backup(target)['authenticated']
    else:assert inspect_backup(target)['checksums_valid']


def test_plaintext_still_creates_missing_parent_directories(tmp_path,source):
    target=tmp_path/'new-parent'/'backup'
    assert backup(source,target,True)['backup_created'] and inspect_backup(target)['checksums_valid']


def test_encrypted_still_requires_existing_parent(tmp_path,source):
    target=tmp_path/'new-parent'/'backup.enc'
    with pytest.raises(RuntimeError,match='directory first'):sealed.encrypted_backup(source,target,True)
    assert not target.parent.exists()


@pytest.mark.parametrize('encrypted',[False,True])
def test_leaf_created_after_validation_is_never_overwritten(tmp_path,source,encrypted,monkeypatch):
    target=tmp_path/'backup';original=Path.mkdir if not encrypted else os.open
    if encrypted:
        def racing(path,flags,*args,**kwargs):
            if Path(path)==target:target.write_bytes(b'created by another writer')
            return original(path,flags,*args,**kwargs)
        # Patch this module's OS view only; do not change process-global os.open.
        class RacingOS:
            def __getattr__(self,name):return racing if name=='open' else getattr(os,name)
        monkeypatch.setattr(sealed,'os',RacingOS())
    else:
        def racing(path,*args,**kwargs):
            if path==target:original(path);(path/'keep').write_bytes(b'created by another writer')
            return original(path,*args,**kwargs)
        monkeypatch.setattr(Path,'mkdir',racing)
    with pytest.raises(FileExistsError):create(source,target,encrypted)
    assert (target if encrypted else target/'keep').read_bytes()==b'created by another writer'
    assert not list(tmp_path.glob('.nexus-private-*'))
