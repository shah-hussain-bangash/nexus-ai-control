"""Authenticated encrypted backups and isolated restore inspection.

Source databases must be quiesced. The key is injected separately and is never
stored in the archive. Inspection authenticates the entire archive before any
member is extracted; it never overwrites application data.
"""
import base64
from contextlib import contextmanager
import io
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.exceptions import InvalidTag
from .backup import backup,inspect_backup,inspection_manifest

MAGIC=b'NEXUSENC1'
MAX_BYTES=512*1024*1024
MAX_MEMBERS=4
KEY_ENV='NEXUS_BACKUP_ENCRYPTION_KEY'
MEMBERS={'manifest.json','control.sqlite3','control.dump','business.sqlite3'}


def validated_members(tar):
    members=[];names=set();total=0
    # TarFile caches parsed members. Stop on the first invalid resolved member
    # so a long malformed archive cannot populate an unbounded member list.
    for member in tar:
        if len(members)>=MAX_MEMBERS or member.name in names or not member.isfile() or member.name not in MEMBERS or member.size<0 or total+member.size>MAX_BYTES:
            raise RuntimeError('Unsafe encrypted backup member layout.')
        members.append(member);names.add(member.name);total+=member.size
    if 'manifest.json' not in names:raise RuntimeError('Unsafe encrypted backup member layout.')
    return members


def encryption_key():
    try:key=base64.b64decode(os.environ.get(KEY_ENV,''),validate=True)
    except ValueError:raise RuntimeError('Backup encryption key must be base64-encoded 32 random bytes.') from None
    if len(key)!=32:raise RuntimeError('Provision NEXUS_BACKUP_ENCRYPTION_KEY as base64-encoded 32 random bytes through your protected secret store.')
    return key


def encrypted_backup(settings,destination,quiesced=False):
    if not quiesced:raise RuntimeError('Stop API and worker before creating a cross-database backup; pass --quiesced only after stopping them.')
    key=encryption_key();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError('Backup destination already exists; no file was overwritten.')
    if not destination.parent.is_dir():raise RuntimeError('Create the private backup destination directory first.')
    # Use the destination's protected filesystem; plaintext temporary snapshots
    # are cleaned on normal completion/failure, not guaranteed securely erased.
    with tempfile.TemporaryDirectory(prefix='.nexus-private-',dir=destination.parent) as temp:
        root=Path(temp);os.chmod(root,0o700);snapshot=root/'snapshot'
        info=backup(settings,snapshot,True);archive=root/'snapshot.tar'
        with tarfile.open(archive,'w') as tar:
            for file in sorted(snapshot.iterdir()):tar.add(file,arcname=file.name,recursive=False)
        if archive.stat().st_size>MAX_BYTES:raise RuntimeError('Encrypted backup supports archives up to 512 MiB; use your reviewed large-database backup tooling above this bound.')
        nonce=os.urandom(12);encryptor=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor();encryptor.authenticate_additional_data(MAGIC)
        encrypted=root/'sealed.enc'
        with archive.open('rb') as source,encrypted.open('wb') as output:
            output.write(MAGIC+nonce)
            while block:=source.read(65536):output.write(encryptor.update(block))
            output.write(encryptor.finalize());output.write(encryptor.tag)
        # Exclusive creation; never overwrite a previous recovery artifact.
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(fd,'wb') as output,encrypted.open('rb') as source:shutil.copyfileobj(source,output);output.flush();os.fsync(output.fileno())
        except BaseException:
            destination.unlink(missing_ok=True);raise
    return {'backup_created':True,'file':str(destination),'encrypted_by_application':True,'algorithm':'AES-256-GCM','kind':info['kind'],'key_stored_in_archive':False,'restore_verified':False,'boundary':'Quiesced bounded backup. Key custody, encrypted temporary storage, off-host retention and full PostgreSQL restore drills remain operator responsibilities.'}


@contextmanager
def authenticated_snapshot(source,temporary_parent=None):
    key=encryption_key();source=Path(source).resolve();size=source.stat().st_size
    if not len(MAGIC)+12+16<size<=MAX_BYTES+len(MAGIC)+28:raise RuntimeError('Invalid or unsupported encrypted backup size.')
    with source.open('rb') as encrypted:
        if encrypted.read(len(MAGIC))!=MAGIC:raise RuntimeError('Unsupported encrypted backup format.')
        nonce=encrypted.read(12);encrypted.seek(-16,2);tag=encrypted.read(16)
        decryptor=Cipher(algorithms.AES(key),modes.GCM(nonce,tag)).decryptor();decryptor.authenticate_additional_data(MAGIC)
        options={'prefix':'nexus-restore-inspection-'}
        if temporary_parent is not None:options['dir']=temporary_parent
        with tempfile.TemporaryDirectory(**options) as temp:
            root=Path(temp);os.chmod(root,0o700);archive=root/'authenticated.tar'
            try:
                with archive.open('wb') as plain:
                    encrypted.seek(len(MAGIC)+12);remaining=size-len(MAGIC)-28
                    while remaining:
                        block=encrypted.read(min(remaining,65536))
                        if not block:raise RuntimeError('Truncated encrypted backup.')
                        plain.write(decryptor.update(block));remaining-=len(block)
                    plain.write(decryptor.finalize())
            except InvalidTag:raise RuntimeError('Backup authentication failed. The key is wrong or the archive was modified; nothing was restored.') from None
            target=root/'inspection';target.mkdir(mode=0o700)
            try:
                with tarfile.open(archive,'r:') as tar:
                    members=validated_members(tar);names=[m.name for m in members]
                    for member in members:
                        file=tar.extractfile(member)
                        if file is None:raise RuntimeError('Missing encrypted backup member.')
                        with file,(target/member.name).open('xb') as output:shutil.copyfileobj(file,output)
                manifest=__import__('json').loads((target/'manifest.json').read_text())
                declared=[item['name'] for item in manifest['files']]
                if set(declared)!=(set(names)-{'manifest.json'}) or len(set(declared))!=len(declared):raise RuntimeError('Encrypted backup manifest does not match archive members.')
                result=inspect_backup(target)
            except (tarfile.TarError,ValueError,KeyError,TypeError,OSError):raise RuntimeError('Encrypted backup inspection failed; no application data was overwritten.') from None
            yield target,result


def inspect_encrypted_backup(source):
    with authenticated_snapshot(source) as (_,result):
        return {**result,'authenticated':True,'algorithm':'AES-256-GCM','active_data_overwritten':False,'boundary':'Checksums and SQLite integrity were inspected in a temporary directory. This is not a live restore, PostgreSQL restore drill or measured RPO/RTO.'}


def recover_encrypted_sqlite(source,destination):
    """Copy authenticated SQLite files into an exclusively created directory.

    Never activates a database, loads runtime settings or overwrites a path.
    Failed copies retain their partial new directory for protected local review.
    """
    requested=Path(destination).absolute()
    if requested.exists() or requested.is_symlink():raise FileExistsError('Recovery destination already exists; no file was overwritten.')
    parent=requested.parent.resolve()
    if not parent.is_dir():raise RuntimeError('Create a protected recovery parent directory first.')
    target=parent/requested.name
    with authenticated_snapshot(source,temporary_parent=parent) as (snapshot,result):
        if result['kind']!='sqlite':raise RuntimeError('Isolated recovery copy supports SQLite only; PostgreSQL requires a separate reviewed restore workflow.')
        manifest=inspection_manifest(snapshot)
        # mkdir is exclusive on both Windows and POSIX. Do not rename over an
        # empty preexisting directory or remove any destination on failure.
        target.mkdir(mode=0o700,exist_ok=False)
        # Read-only SQLite inspection may create WAL/SHM companions. Export
        # only authenticated declarations, never incidental directory contents.
        files=sorted([snapshot/'manifest.json']+[snapshot/item['name'] for item in manifest['files']],key=lambda file:(file.name=='manifest.json',file.name))
        try:
            for file in files:
                fd=os.open(target/file.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as output,file.open('rb') as original:
                    shutil.copyfileobj(original,output);output.flush();os.fsync(output.fileno())
            if {file.name for file in target.iterdir()}!={file.name for file in files}:raise RuntimeError('Unexpected recovery directory contents.')
            # These are quiesced, authenticated copies with no live writer.
            # Immutable reads avoid creating unauthenticated WAL/SHM files.
            checked=inspect_backup(target,immutable_sqlite=True)
            if not checked['checksums_valid'] or not checked['sqlite_integrity_valid']:raise RuntimeError('Recovery copy verification failed.')
        except (OSError,RuntimeError):
            raise RuntimeError('Isolated recovery copy failed. A partial new directory may remain; no existing file was overwritten.') from None
    return {'isolated_copy_created':True,'directory':str(target),'authenticated':True,'kind':'sqlite','files':len(files),
        'active_data_overwritten':False,'application_started':False,'restore_verified':False,'postgresql_restore_verified':False,
        'boundary':'Authenticated SQLite files copied into a new plaintext directory. No active database was replaced, runtime settings changed, schema migrated or application started. Full application restore acceptance and measured RPO/RTO remain separate work.'}
