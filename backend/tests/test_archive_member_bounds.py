"""Malformed authenticated archive layouts must be rejected with bounded parsing."""
import base64
import io
import tarfile
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from nexus.encrypted_backup import MAGIC,inspect_encrypted_backup


def sealed(tmp_path,monkeypatch,names,kind=None):
    key=b'k'*32;nonce=b'n'*12
    monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY',base64.b64encode(key).decode())
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for index,name in enumerate(names):
            item=tarfile.TarInfo(name);data=b'{}';item.size=len(data)
            if index==0 and kind is not None:
                item.type=kind;item.size=0;item.linkname='outside-fixture';data=b''
            tar.addfile(item,io.BytesIO(data))
    path=tmp_path/'fixture.enc'
    path.write_bytes(MAGIC+nonce+AESGCM(key).encrypt(nonce,archive.getvalue(),MAGIC))
    return path


def track_parser(monkeypatch):
    calls=[];original=tarfile.TarFile.next
    def tracked(tar):
        member=original(tar)
        # Ignore TarFile's cached first-member return and EOF probes; count
        # distinct resolved headers, the objects retained by its member cache.
        if member is not None and member.offset not in calls:calls.append(member.offset)
        return member
    monkeypatch.setattr(tarfile.TarFile,'next',tracked)
    def no_extract(*args):pytest.fail('An unsafe archive was extracted')
    monkeypatch.setattr(tarfile.TarFile,'extractfile',no_extract)
    return calls


@pytest.mark.parametrize('count',[5,12,100])
def test_overflow_stops_at_fifth_member_without_parsing_tail_or_extracting(tmp_path,monkeypatch,count):
    names=['manifest.json','control.sqlite3','control.dump','business.sqlite3']+['manifest.json']*(count-4)
    path=sealed(tmp_path,monkeypatch,names);before=path.read_bytes();calls=track_parser(monkeypatch)
    with pytest.raises(RuntimeError,match='Unsafe encrypted backup member layout'):inspect_encrypted_backup(path)
    assert len(calls)<=5 and path.read_bytes()==before


@pytest.mark.parametrize('unsafe',['traversal','symlink','directory','duplicate'])
def test_first_unsafe_member_stops_layout_validation(tmp_path,monkeypatch,unsafe):
    names=['manifest.json']*12;kind=None;bound=1
    if unsafe=='traversal':names[0]='../outside-fixture'
    elif unsafe=='symlink':kind=tarfile.SYMTYPE
    elif unsafe=='directory':kind=tarfile.DIRTYPE
    else:bound=2
    path=sealed(tmp_path,monkeypatch,names,kind);calls=track_parser(monkeypatch)
    with pytest.raises(RuntimeError,match='Unsafe encrypted backup member layout'):inspect_encrypted_backup(path)
    assert len(calls)<=bound


def test_failed_authentication_never_starts_tar_parsing(tmp_path,monkeypatch):
    path=sealed(tmp_path,monkeypatch,['manifest.json']*12);blob=path.read_bytes()
    path.write_bytes(blob[:-1]+bytes([blob[-1]^1]))
    def forbidden(*args):pytest.fail('Archive was parsed before authentication')
    monkeypatch.setattr(tarfile.TarFile,'next',forbidden)
    with pytest.raises(RuntimeError,match='authentication'):inspect_encrypted_backup(path)


def test_missing_manifest_rejected_before_extraction(tmp_path,monkeypatch):
    path=sealed(tmp_path,monkeypatch,['control.sqlite3']);calls=track_parser(monkeypatch)
    with pytest.raises(RuntimeError,match='Unsafe encrypted backup member layout'):inspect_encrypted_backup(path)
    assert len(calls)<=2
