"""Publication failure must not delete a path that another writer replaced."""
from contextlib import closing,contextmanager
import base64
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest
from nexus import encrypted_backup as sealed
from nexus.config import Settings


@pytest.fixture
def source(tmp_path,monkeypatch):
    path=tmp_path/'source.db'
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO schema_versions VALUES (11)');db.commit()
    monkeypatch.setenv(sealed.KEY_ENV,base64.b64encode(b'k'*32).decode())
    return Settings(database_url='sqlite:///'+path.as_posix(),mock_database=str(tmp_path/'absent-business.db'))


class LocalOS:
    def __init__(self,**overrides):self.overrides=overrides
    def __getattr__(self,name):return self.overrides.get(name,getattr(os,name))


def test_replacement_file_is_not_deleted_after_publication_failure(tmp_path,source,monkeypatch):
    destination=tmp_path/'backup.enc';retired=tmp_path/'moved-original.enc';original=os.fdopen
    @contextmanager
    def replaced(fd,*args,**kwargs):
        with original(fd,*args,**kwargs) as output:yield output
        # Close the fixture handle first so this race is portable on Windows.
        destination.replace(retired);destination.write_bytes(b'preserve replacement artifact')
        raise OSError('private publication failure sentinel')
    monkeypatch.setattr(sealed,'os',LocalOS(fdopen=replaced))
    with pytest.raises((OSError,RuntimeError)):sealed.encrypted_backup(source,destination,True)
    assert destination.read_bytes()==b'preserve replacement artifact'
    assert sealed.inspect_encrypted_backup(retired)['authenticated']
    assert not list(tmp_path.glob('.nexus-private-*'))


@pytest.mark.parametrize('fault',['copy','source_read','sync','close'])
def test_failed_publication_retains_artifact_hides_details_and_blocks_retry(tmp_path,source,monkeypatch,fault):
    destination=tmp_path/'backup.enc';before=(tmp_path/'source.db').read_bytes()
    with monkeypatch.context() as patch:
        if fault=='copy':
            def broken_copy(original,output):
                output.write(original.read(20));raise OSError('private publication failure sentinel')
            patch.setattr(sealed,'shutil',SimpleNamespace(copyfileobj=broken_copy))
        elif fault=='source_read':
            original=Path.open
            def broken_read(path,*args,**kwargs):
                if path.name=='sealed.enc' and args and args[0]=='rb':raise OSError('private publication failure sentinel')
                return original(path,*args,**kwargs)
            patch.setattr(Path,'open',broken_read)
        elif fault=='sync':
            def broken_sync(fd):raise OSError('private publication failure sentinel')
            patch.setattr(sealed,'os',LocalOS(fsync=broken_sync))
        else:
            original=os.fdopen
            @contextmanager
            def broken_close(fd,*args,**kwargs):
                with original(fd,*args,**kwargs) as output:yield output
                raise OSError('private publication failure sentinel')
            patch.setattr(sealed,'os',LocalOS(fdopen=broken_close))
        with pytest.raises(RuntimeError,match='publication failed') as error:sealed.encrypted_backup(source,destination,True)
        assert 'private publication failure sentinel' not in str(error.value)
        assert error.value.__suppress_context__
    assert destination.is_file() and not list(tmp_path.glob('.nexus-private-*'))
    retained=destination.read_bytes()
    with pytest.raises(FileExistsError):sealed.encrypted_backup(source,destination,True)
    assert destination.read_bytes()==retained and (tmp_path/'source.db').read_bytes()==before
    if fault in ('copy','source_read'):
        with pytest.raises(RuntimeError):sealed.inspect_encrypted_backup(destination)
    else:assert sealed.inspect_encrypted_backup(destination)['authenticated']
    # Only an explicitly different new path is used for a successful retry.
    fresh=tmp_path/'retry.enc';assert sealed.encrypted_backup(source,fresh,True)['backup_created']
    assert sealed.inspect_encrypted_backup(fresh)['authenticated'] and destination.read_bytes()==retained


@pytest.mark.parametrize('interruption',[KeyboardInterrupt,SystemExit])
def test_interruption_propagates_without_deleting_new_destination(tmp_path,source,monkeypatch,interruption):
    destination=tmp_path/'backup.enc';before=(tmp_path/'source.db').read_bytes()
    def interrupted(original,output):
        output.write(original.read(20));raise interruption()
    monkeypatch.setattr(sealed,'shutil',SimpleNamespace(copyfileobj=interrupted))
    with pytest.raises(interruption):sealed.encrypted_backup(source,destination,True)
    assert destination.is_file() and destination.stat().st_size==20
    assert (tmp_path/'source.db').read_bytes()==before and not list(tmp_path.glob('.nexus-private-*'))


def test_failure_before_exclusive_creation_leaves_no_destination(tmp_path,source,monkeypatch):
    destination=tmp_path/'backup.enc';original=Path.open
    def broken_staging(path,*args,**kwargs):
        if path.name=='sealed.enc' and args and args[0]=='wb':raise OSError('staging fixture failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',broken_staging)
    with pytest.raises(OSError):sealed.encrypted_backup(source,destination,True)
    assert not destination.exists() and not list(tmp_path.glob('.nexus-private-*'))
