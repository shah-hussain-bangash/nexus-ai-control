"""Inspection must not certify a missing or misdeclared recovery snapshot."""
import base64
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from nexus.backup import inspect_backup
from nexus.encrypted_backup import MAGIC,inspect_encrypted_backup


def snapshot(root):
    root.mkdir()
    path=root/'control.sqlite3'
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO schema_versions VALUES (11)')
        db.commit()
    manifest={'kind':'sqlite','schema':11,'files':[{
        'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}]}
    return manifest


def save(root,manifest):
    (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')


@pytest.mark.parametrize('kind',['sqlite','postgresql'])
def test_empty_manifest_cannot_pass_without_control_snapshot(tmp_path,kind):
    save(tmp_path,{'kind':kind,'schema':11,'files':[]})
    with pytest.raises(RuntimeError):inspect_backup(tmp_path)


@pytest.mark.parametrize('change',[
    'unknown_kind','wrong_kind','missing_schema','boolean_schema','mismatched_schema',
    'files_not_list','missing_control','duplicate_member','missing_size','wrong_size','negative_size',
    'boolean_size','invalid_hash','item_not_object','manifest_not_object','duplicate_case_member','unsafe_trailing_dot',
])
def test_invalid_manifest_metadata_is_rejected(tmp_path,change):
    root=tmp_path/'backup';manifest=snapshot(root)
    if change=='unknown_kind':manifest['kind']='unknown'
    elif change=='wrong_kind':manifest['kind']='postgresql'
    elif change=='missing_schema':del manifest['schema']
    elif change=='boolean_schema':manifest['schema']=True
    elif change=='mismatched_schema':manifest['schema']=10
    elif change=='files_not_list':manifest['files']={}
    elif change=='missing_control':manifest['files'][0]['name']='business.sqlite3';(root/'control.sqlite3').rename(root/'business.sqlite3')
    elif change=='duplicate_member':manifest['files'].append(dict(manifest['files'][0]))
    elif change=='missing_size':del manifest['files'][0]['bytes']
    elif change=='wrong_size':manifest['files'][0]['bytes']+=1
    elif change=='negative_size':manifest['files'][0]['bytes']=-1
    elif change=='boolean_size':manifest['files'][0]['bytes']=True
    elif change=='invalid_hash':manifest['files'][0]['sha256']='invalid'
    elif change=='item_not_object':manifest['files']=[42]
    elif change=='manifest_not_object':manifest=[]
    elif change=='duplicate_case_member':manifest['files'].append({**manifest['files'][0],'name':'CONTROL.SQLITE3'})
    elif change=='unsafe_trailing_dot':manifest['files'].append({'name':'runtime.env.','bytes':1,'sha256':'0'*64})
    save(root,manifest)
    with pytest.raises(RuntimeError):inspect_backup(root)


def test_valid_snapshot_with_operator_configuration_artifact_is_read_only(tmp_path):
    root=tmp_path/'backup';manifest=snapshot(root)
    extra=root/'runtime.env';extra.write_bytes(b'SYNTHETIC_CONFIG=fixture\n')
    manifest['files'].append({'name':extra.name,'sha256':hashlib.sha256(extra.read_bytes()).hexdigest(),'bytes':extra.stat().st_size})
    save(root,manifest);before={p.name:p.read_bytes() for p in root.iterdir()}
    checked=inspect_backup(root)
    assert checked['checksums_valid'] and checked['sqlite_integrity_valid'] and not checked['postgresql_restore_verified']
    assert {p.name:p.read_bytes() for p in root.iterdir()}==before


def test_authenticated_encryption_does_not_make_empty_manifest_valid(tmp_path,monkeypatch):
    key=b'k'*32;monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY',base64.b64encode(key).decode())
    body=json.dumps({'kind':'sqlite','schema':11,'files':[]}).encode()
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w') as tar:
        item=tarfile.TarInfo('manifest.json');item.size=len(body);tar.addfile(item,io.BytesIO(body))
    nonce=b'n'*12;path=tmp_path/'empty.enc';path.write_bytes(MAGIC+nonce+AESGCM(key).encrypt(nonce,archive.getvalue(),MAGIC))
    before=path.read_bytes()
    with pytest.raises(RuntimeError):inspect_encrypted_backup(path)
    assert path.read_bytes()==before


def test_postgresql_manifest_requires_nonempty_dump(tmp_path):
    path=tmp_path/'control.dump';path.write_bytes(b'')
    save(tmp_path,{'kind':'postgresql','schema':11,'files':[{'name':path.name,'sha256':hashlib.sha256(b'').hexdigest(),'bytes':0}]})
    with pytest.raises(RuntimeError):inspect_backup(tmp_path)


def test_dump_checksums_do_not_claim_postgresql_restore(tmp_path):
    # Only container metadata is exercised; this is not a PostgreSQL dump/restore drill.
    path=tmp_path/'control.dump';path.write_bytes(b'PGDMP-synthetic-container-fixture')
    save(tmp_path,{'kind':'postgresql','schema':11,'files':[{'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}]})
    checked=inspect_backup(tmp_path)
    assert checked['checksums_valid'] and not checked['postgresql_restore_verified']


@pytest.mark.parametrize('missing',['deleted','directory'])
def test_required_member_must_be_a_regular_file(tmp_path,missing):
    root=tmp_path/'backup';manifest=snapshot(root);save(root,manifest)
    path=root/'control.sqlite3';path.unlink()
    if missing=='directory':path.mkdir()
    with pytest.raises(RuntimeError):inspect_backup(root)


def test_symlink_member_is_not_followed(tmp_path):
    root=tmp_path/'backup';manifest=snapshot(root);save(root,manifest)
    path=root/'control.sqlite3';external=tmp_path/'external.db';path.rename(external)
    try:path.symlink_to(external)
    except OSError:pytest.skip('Creating symlinks requires Windows privileges on this host.')
    before=external.read_bytes()
    with pytest.raises(RuntimeError):inspect_backup(root)
    assert external.read_bytes()==before


def test_invalid_sqlite_is_rejected_even_when_its_checksum_matches(tmp_path):
    root=tmp_path/'backup';manifest=snapshot(root)
    path=root/'control.sqlite3';path.write_bytes(b'not a SQLite snapshot')
    manifest['files'][0].update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
    save(root,manifest)
    with pytest.raises(RuntimeError):inspect_backup(root)


def test_path_traversal_is_rejected_before_external_file_is_read(tmp_path,monkeypatch):
    root=tmp_path/'backup';manifest=snapshot(root)
    manifest['files'].append({'name':'../private.env','bytes':1,'sha256':'0'*64});save(root,manifest)
    original=Path.read_bytes
    def guarded(path):
        if path.name=='private.env':pytest.fail('External member path was read')
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    with pytest.raises(RuntimeError):inspect_backup(root)
