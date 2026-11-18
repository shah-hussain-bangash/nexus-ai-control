import base64
from pathlib import Path
import pytest
from nexus.encrypted_backup import encrypted_backup,inspect_encrypted_backup

@pytest.fixture
def key(monkeypatch):monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY',base64.b64encode(b'k'*32).decode())

def test_encrypted_backup_authentication_inspection_and_no_overwrite(ctx,tmp_path,key):
    target=tmp_path/'safe.enc'
    with pytest.raises(RuntimeError):encrypted_backup(ctx['settings'],target)
    result=encrypted_backup(ctx['settings'],target,True)
    assert result['encrypted_by_application'] and not result['restore_verified']
    blob=target.read_bytes();assert b'owner@nexus.local' not in blob and b'SQLite format' not in blob
    checked=inspect_encrypted_backup(target);assert checked['authenticated'] and checked['checksums_valid'] and not checked['active_data_overwritten']
    with pytest.raises(FileExistsError):encrypted_backup(ctx['settings'],target,True)
    assert target.read_bytes()==blob and not list(tmp_path.glob('.nexus-private-*'))

def test_wrong_key_tampering_and_truncation_rejected_before_restore(ctx,tmp_path,key,monkeypatch):
    target=tmp_path/'safe.enc';encrypted_backup(ctx['settings'],target,True);blob=target.read_bytes()
    target.write_bytes(blob[:-20]+bytes([blob[-20]^1])+blob[-19:])
    with pytest.raises(RuntimeError,match='authentication'):inspect_encrypted_backup(target)
    target.write_bytes(blob);monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY',base64.b64encode(b'w'*32).decode())
    with pytest.raises(RuntimeError,match='authentication'):inspect_encrypted_backup(target)
    target.write_bytes(blob[:20])
    with pytest.raises(RuntimeError):inspect_encrypted_backup(target)

def test_missing_key_does_not_leave_plaintext_snapshot(ctx,tmp_path,monkeypatch):
    monkeypatch.delenv('NEXUS_BACKUP_ENCRYPTION_KEY',raising=False)
    with pytest.raises(RuntimeError):encrypted_backup(ctx['settings'],tmp_path/'none.enc',True)
    assert list(tmp_path.iterdir()) and not (tmp_path/'none.enc').exists() and not list(tmp_path.glob('.nexus-private-*'))
