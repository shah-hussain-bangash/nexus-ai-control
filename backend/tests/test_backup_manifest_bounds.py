"""Malformed metadata must fail privately before exposing recovery files."""
import base64
import hashlib
import json
import tarfile
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import pytest
from nexus import backup,encrypted_backup as sealed
from nexus.backup_drill import LocalKeyOS,seal_fixture


BAD_MANIFESTS=[b'[]',b'null',b'42',b'"private fixture value"',b'{',b'\xff',
    *[json.dumps({'kind':'postgresql','schema':11,'files':value}).encode()
      for value in (None,{},[None],[42],[{'name':[]}])],
    b'['*2000+b'0'+b']'*2000]


@pytest.fixture
def private_inspection(tmp_path,monkeypatch):
    key=b'k'*32
    monkeypatch.setattr(sealed,'os',LocalKeyOS({sealed.KEY_ENV:base64.b64encode(key).decode()}))
    def private_temp(**options):
        options.setdefault('dir',tmp_path)
        return TemporaryDirectory(**options)
    monkeypatch.setattr(sealed,'tempfile',SimpleNamespace(TemporaryDirectory=private_temp))
    return key


@pytest.mark.parametrize('body',BAD_MANIFESTS)
@pytest.mark.parametrize('encrypted',[False,True])
def test_bad_manifest_is_rejected_without_exposing_or_copying_files(tmp_path,private_inspection,body,encrypted):
    if encrypted:
        source=tmp_path/'bad.enc';seal_fixture(source,private_inspection,[('manifest.json',body)])
        before=source.read_bytes();target=tmp_path/'recovered';yielded=[]
        with pytest.raises(RuntimeError,match='Invalid backup manifest') as error:
            with sealed.authenticated_snapshot(source,temporary_parent=tmp_path) as result:yielded.append(result)
        with pytest.raises(RuntimeError,match='Invalid backup manifest'):
            sealed.recover_encrypted_sqlite(source,target)
        assert not yielded and not target.exists() and source.read_bytes()==before
        assert not list(tmp_path.glob('nexus-restore-inspection-*'))
    else:
        source=tmp_path/'manifest.json';source.write_bytes(body)
        with pytest.raises(RuntimeError,match='Invalid backup manifest') as error:backup.inspect_backup(tmp_path)
        assert source.read_bytes()==body
    assert 'private fixture value' not in str(error.value) and error.value.__suppress_context__


def pg_manifest():
    dump=b'PGDMP-metadata-only-fixture'
    body=json.dumps({'kind':'postgresql','schema':11,'files':[{
        'name':'control.dump','bytes':len(dump),'sha256':hashlib.sha256(dump).hexdigest()}]}).encode()
    return body,dump


@pytest.mark.parametrize('encrypted',[False,True])
def test_manifest_at_byte_limit_still_passes_metadata_inspection(tmp_path,private_inspection,encrypted):
    body,dump=pg_manifest();body+=b' '*(backup.MAX_MANIFEST_BYTES-len(body))
    if encrypted:
        source=tmp_path/'valid.enc';seal_fixture(source,private_inspection,[('manifest.json',body),('control.dump',dump)])
        checked=sealed.inspect_encrypted_backup(source)
        assert checked['authenticated'] and not list(tmp_path.glob('nexus-restore-inspection-*'))
    else:
        (tmp_path/'manifest.json').write_bytes(body);(tmp_path/'control.dump').write_bytes(dump)
        checked=backup.inspect_backup(tmp_path)
    assert checked['checksums_valid'] and not checked['postgresql_restore_verified']


@pytest.mark.parametrize('encrypted',[False,True])
def test_oversized_manifest_rejected_before_json_parsing_or_tar_extraction(tmp_path,private_inspection,monkeypatch,encrypted):
    body,dump=pg_manifest();body+=b' '*(backup.MAX_MANIFEST_BYTES+1-len(body))
    if encrypted:
        source=tmp_path/'large.enc';seal_fixture(source,private_inspection,[('manifest.json',body),('control.dump',dump)])
        before=source.read_bytes()
        def no_extract(*args,**kwargs):pytest.fail('Oversized manifest reached tar extraction')
        monkeypatch.setattr(tarfile.TarFile,'extractfile',no_extract)
    else:
        source=tmp_path/'manifest.json';source.write_bytes(body);before=source.read_bytes()
    def no_parse(*args,**kwargs):pytest.fail('Oversized manifest reached JSON parser')
    monkeypatch.setattr(backup.json,'loads',no_parse)
    with pytest.raises(RuntimeError,match='manifest'):
        if encrypted:sealed.inspect_encrypted_backup(source)
        else:backup.inspect_backup(tmp_path)
    assert source.read_bytes()==before and not list(tmp_path.glob('nexus-restore-inspection-*'))
