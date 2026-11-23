"""Checksum database payloads without reading entire files into memory."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest
from nexus import backup


class ObservedReader:
    def __init__(self,stream,requests,after_first=None):
        self.stream=stream;self.requests=requests;self.after_first=after_first;self.first=True
    def __enter__(self):return self
    def __exit__(self,*args):self.stream.close()
    def fileno(self):return self.stream.fileno()
    def read(self,size=-1):
        assert 0<size<=backup.CHECKSUM_CHUNK_BYTES
        self.requests.append(size);block=self.stream.read(size)
        if self.first and self.after_first is not None:self.after_first()
        self.first=False
        return block


def observe(monkeypatch,selected,after_first=None):
    original=Path.open;requests=[]
    def opened(path,mode='r',*args,**kwargs):
        stream=original(path,mode,*args,**kwargs)
        return ObservedReader(stream,requests,after_first) if mode=='rb' and selected(path) else stream
    monkeypatch.setattr(Path,'open',opened)
    return requests


@pytest.mark.parametrize('size',[0,1,65535,65536,65537,3*65536+17])
def test_metadata_retains_exact_sha256_and_size_using_bounded_reads(tmp_path,monkeypatch,size):
    path=tmp_path/'payload.dump';data=(b'bounded-fixture-'*((size//16)+1))[:size];path.write_bytes(data)
    requests=observe(monkeypatch,lambda p:p==path)
    def no_whole_file(*args,**kwargs):pytest.fail('Whole-file read was used for checksum')
    monkeypatch.setattr(Path,'read_bytes',no_whole_file)
    assert backup.file_metadata(path)=={'name':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    assert requests and max(requests)<=65536


@pytest.mark.parametrize('change',['grow','shrink'])
def test_length_change_during_checksum_is_rejected_with_a_bounded_read(tmp_path,monkeypatch,change):
    path=tmp_path/'payload.dump';data=b'x'*(2*65536+17);path.write_bytes(data)
    def changed():
        if change=='grow':
            with path.open('ab') as stream:stream.write(b'y'*(3*65536))
        else:
            with path.open('r+b') as stream:stream.truncate(17)
    requests=observe(monkeypatch,lambda p:p==path,changed)
    with pytest.raises(RuntimeError,match='length changed'):backup.file_metadata(path)
    assert max(requests)<=65536 and sum(requests)<=len(data)+1


def test_storage_error_hides_private_member_details(tmp_path,monkeypatch):
    path=tmp_path/'private-fixture.dump'
    def denied(*args,**kwargs):raise OSError('private-fixture.dump private storage detail')
    monkeypatch.setattr(Path,'open',denied)
    with pytest.raises(RuntimeError,match='checksum failed') as error:backup.file_metadata(path)
    assert 'private-fixture.dump' not in str(error.value) and 'private storage detail' not in str(error.value)
    assert error.value.__suppress_context__


def test_backup_creation_and_inspection_stream_the_snapshot_payload(tmp_path,monkeypatch):
    source=tmp_path/'source.db'
    with closing(sqlite3.connect(source)) as db:
        db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO schema_versions VALUES (11)')
        db.execute('CREATE TABLE payload (data BLOB)')
        db.execute('INSERT INTO payload VALUES (?)',(b'x'*(2*1024*1024),));db.commit()
    target=tmp_path/'snapshot';settings=SimpleNamespace(database_url='sqlite:///'+source.as_posix(),mock_database=str(tmp_path/'absent.db'))
    original=Path.read_bytes;requests=observe(monkeypatch,lambda p:p.name=='control.sqlite3')
    def no_payload_read(path):
        if path.name=='control.sqlite3':pytest.fail('Snapshot payload was read into memory at once')
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',no_payload_read)
    assert backup.backup(settings,target,True)['backup_created']
    creation_reads=len(requests);assert creation_reads>32
    manifest=json.loads((target/'manifest.json').read_text())
    with open(target/'control.sqlite3','rb') as reference:data=reference.read()
    assert manifest['files']==[{'name':'control.sqlite3','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]
    assert backup.inspect_backup(target)['checksums_valid'] and len(requests)>creation_reads
    assert max(requests)<=65536


@pytest.mark.parametrize('change',['checksum','size'])
def test_streamed_inspection_still_rejects_wrong_manifest_metadata(tmp_path,change):
    path=tmp_path/'control.dump';data=b'PGDMP-metadata-only-fixture';path.write_bytes(data)
    manifest={'kind':'postgresql','schema':11,'files':[{'name':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}
    if change=='checksum':manifest['files'][0]['sha256']='0'*64
    else:manifest['files'][0]['bytes']+=1
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError,match='checksum or size mismatch'):backup.inspect_backup(tmp_path)
