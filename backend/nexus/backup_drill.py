"""Disposable SQLite snapshots and encrypted inspection; never restores active data."""
import argparse
import base64
from contextlib import closing,contextmanager
from dataclasses import replace
from datetime import datetime,timezone
import gc
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import uuid
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from . import __version__,encrypted_backup as sealed
from .backup import backup,inspect_backup
from .cli import seed
from .config import Settings
from .db import CURRENT_SCHEMA,database,migrate

BOUNDARY='Disposable synthetic SQLite backup and encrypted-inspection exercise only. No model provider or customer system was contacted. No active application database was restored or overwritten. This is not an encrypted restore, PostgreSQL restore, measured RPO/RTO, authenticated drill evidence or production readiness.'


class DrillFailure(Exception):pass


class LocalKeyOS:
    """Replace only the encryption module's environment view, never os.environ."""
    def __init__(self,environment):self.environ=environment
    def __getattr__(self,name):return getattr(os,name)


def records(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise DrillFailure('fixture_database_integrity_failed')
        result={}
        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted='"'+name.replace('"','""')+'"'
            rows=[json.dumps(row,separators=(',',':'),default=lambda value:base64.b64encode(value).decode()) for row in db.execute('SELECT * FROM '+quoted)]
            result[name]=(len(rows),hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest())
        return result


def seal_fixture(path,key,members):
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name,content in members:
            item=tarfile.TarInfo(name);item.size=len(content);tar.addfile(item,io.BytesIO(content))
    nonce=os.urandom(12);path.write_bytes(sealed.MAGIC+nonce+AESGCM(key).encrypt(nonce,archive.getvalue(),sealed.MAGIC))


def run_drill(directory):
    root=Path(directory).resolve();root.mkdir(exist_ok=False)
    control=root/'control.db';business=root/'business.db'
    settings=Settings(database_url='sqlite:///'+control.as_posix(),mock_database=str(business),
        secret=secrets.token_urlsafe(48),agent_secret=secrets.token_urlsafe(48),frontend_dir=str(root/'no-frontend'),
        mode='local',policy_mode='reference',business_connector='synthetic',live_inference=0)
    report={'format':'nexus-synthetic-backup-drill','format_version':1,'release':__version__,'schema_version':CURRENT_SCHEMA,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'connector_mode':'synthetic','key_mode':'ephemeral_disposable',
        'passed':False,'customer_acceptance':False,'production_ready':False,'live_restore_performed':False,
        'postgresql_restore_verified':False,'steps':[],'boundary':BOUNDARY}
    engine=None;environment={};key=os.urandom(32)
    def check(name,condition):
        report['steps'].append({'id':name,'passed':bool(condition)})
        if not condition:raise DrillFailure(name)
    def rejected(operation,error=RuntimeError):
        try:operation()
        except error:return True
        return False
    def private_temp(**kwargs):
        kwargs.setdefault('dir',root)
        return TemporaryDirectory(**kwargs)
    def no_extract(*args):raise DrillFailure('unsafe_layout_was_extracted')
    try:
        engine,factory=database(settings.database_url);migrate(engine,factory);seed(factory,secrets.token_urlsafe(32))
        engine.dispose();engine=None
        with closing(sqlite3.connect(business)) as db:
            db.execute('CREATE TABLE calls (id INTEGER PRIMARY KEY, intent TEXT NOT NULL)');db.commit()
        original_control=records(control);original_business=records(business)
        check('isolated_current_schema_and_disposable_accounts',original_control['users'][0]==3 and settings.business_connector=='synthetic' and settings.live_inference==0)
        # There is no running API/worker, and every fixture writer is closed.
        plain=root/'plain'
        check('plaintext_requires_quiescence',rejected(lambda:backup(settings,plain)) and not plain.exists())
        created=backup(settings,plain,True)
        check('plaintext_snapshot_created',created['backup_created'] and created['kind']=='sqlite' and not created['restore_verified'])
        inspected=inspect_backup(plain)
        check('plaintext_inspection_passes',inspected['checksums_valid'] and inspected['sqlite_integrity_valid'] and not inspected['postgresql_restore_verified'])
        check('control_snapshot_matches_all_source_records',records(plain/'control.sqlite3')==original_control)
        check('business_snapshot_matches_source_records',records(plain/'business.sqlite3')==original_business)
        manifest=plain/'manifest.json';manifest_bytes=manifest.read_bytes();snapshot=plain/'control.sqlite3';snapshot_bytes=snapshot.read_bytes()
        check('plaintext_destination_never_overwritten',rejected(lambda:backup(settings,plain,True),FileExistsError) and snapshot.read_bytes()==snapshot_bytes and manifest.read_bytes()==manifest_bytes)
        snapshot.write_bytes(snapshot_bytes+b'tampered')
        check('plaintext_tampering_rejected',rejected(lambda:inspect_backup(plain)));snapshot.write_bytes(snapshot_bytes)
        changed=json.loads(manifest_bytes);changed['schema']=CURRENT_SCHEMA+1;manifest.write_text(json.dumps(changed),encoding='utf-8')
        check('schema_mismatch_rejected',rejected(lambda:inspect_backup(plain)))
        changed['schema']=CURRENT_SCHEMA;changed['files']=[];manifest.write_text(json.dumps(changed),encoding='utf-8')
        check('empty_manifest_rejected',rejected(lambda:inspect_backup(plain)));manifest.write_bytes(manifest_bytes)
        saved=root/'saved-snapshot';snapshot.rename(saved)
        try:check('missing_control_snapshot_rejected',rejected(lambda:inspect_backup(plain)))
        finally:saved.rename(snapshot)
        with patch.object(sealed,'os',LocalKeyOS(environment)),patch.object(sealed,'tempfile',SimpleNamespace(TemporaryDirectory=private_temp)):
            destination=root/'backup.enc'
            check('encrypted_backup_requires_quiescence',rejected(lambda:sealed.encrypted_backup(settings,destination)) and not destination.exists())
            check('missing_encryption_key_rejected',rejected(lambda:sealed.encrypted_backup(settings,destination,True)) and not destination.exists())
            environment[sealed.KEY_ENV]='invalid-base64'
            check('invalid_encryption_key_rejected',rejected(lambda:sealed.encrypted_backup(settings,destination,True)) and not destination.exists())
            environment[sealed.KEY_ENV]=base64.b64encode(key).decode()
            created=sealed.encrypted_backup(settings,destination,True);blob=destination.read_bytes()
            check('encrypted_snapshot_created_without_storing_key',created['encrypted_by_application'] and not created['key_stored_in_archive'] and not created['restore_verified'] and
                key not in blob and environment[sealed.KEY_ENV].encode() not in blob and b'SQLite format' not in blob)
            inspected=sealed.inspect_encrypted_backup(destination)
            check('authenticated_encrypted_inspection_passes',inspected['authenticated'] and inspected['checksums_valid'] and inspected['sqlite_integrity_valid'] and
                not inspected['active_data_overwritten'] and not inspected['postgresql_restore_verified'])
            check('encrypted_destination_never_overwritten',rejected(lambda:sealed.encrypted_backup(settings,destination,True),FileExistsError) and destination.read_bytes()==blob)
            environment[sealed.KEY_ENV]=base64.b64encode(os.urandom(32)).decode()
            check('wrong_encryption_key_rejected',rejected(lambda:sealed.inspect_encrypted_backup(destination)))
            environment[sealed.KEY_ENV]=base64.b64encode(key).decode()
            damaged=root/'damaged.enc';offset=len(sealed.MAGIC)+12
            damaged.write_bytes(blob[:offset]+bytes([blob[offset]^1])+blob[offset+1:])
            check('ciphertext_tampering_rejected',rejected(lambda:sealed.inspect_encrypted_backup(damaged)))
            damaged.write_bytes(blob[:-20])
            check('truncated_archive_rejected',rejected(lambda:sealed.inspect_encrypted_backup(damaged)))
            damaged.write_bytes(b'X'+blob[1:])
            check('unsupported_archive_header_rejected',rejected(lambda:sealed.inspect_encrypted_backup(damaged)))
            malformed=root/'malformed.enc'
            empty=json.dumps({'kind':'sqlite','schema':CURRENT_SCHEMA,'files':[]}).encode()
            seal_fixture(malformed,key,[('manifest.json',empty)])
            check('authenticated_empty_manifest_rejected',rejected(lambda:sealed.inspect_encrypted_backup(malformed)))
            names=['manifest.json','control.sqlite3','control.dump','business.sqlite3']+['manifest.json']*8
            seal_fixture(malformed,key,[(name,b'{}') for name in names])
            with patch.object(tarfile.TarFile,'extractfile',no_extract):
                check('excess_members_rejected_before_extraction',rejected(lambda:sealed.inspect_encrypted_backup(malformed)))
            seal_fixture(malformed,key,[('../outside-fixture',b'{}')])
            with patch.object(tarfile.TarFile,'extractfile',no_extract):
                check('unsafe_member_path_rejected_before_extraction',rejected(lambda:sealed.inspect_encrypted_backup(malformed)))
            broken_business=root/'broken-business.db'
            with closing(sqlite3.connect(broken_business)) as db:
                db.execute('PRAGMA foreign_keys=OFF')
                db.execute('CREATE TABLE fixture_parent (id INTEGER PRIMARY KEY)')
                db.execute('CREATE TABLE fixture_child (id INTEGER PRIMARY KEY,parent INTEGER REFERENCES fixture_parent(id))')
                db.execute('INSERT INTO fixture_child VALUES (1,99)');db.commit()
            broken_settings=replace(settings,mock_database=str(broken_business))
            broken_plain=root/'broken-plain';broken_archive=root/'broken.enc'
            check('plaintext_rejects_broken_declared_relationships',rejected(lambda:backup(broken_settings,broken_plain,True)) and not (broken_plain/'manifest.json').exists())
            check('encrypted_rejects_broken_relationships_before_publication',rejected(lambda:sealed.encrypted_backup(broken_settings,broken_archive,True)) and not broken_archive.exists())
            failed=root/'publication-failed.enc'
            def interrupted_copy(source,output):
                output.write(source.read(20));raise OSError('Disposable publication fault')
            with patch.object(sealed,'shutil',SimpleNamespace(copyfileobj=interrupted_copy)):
                check('failed_publication_retains_incomplete_archive',rejected(lambda:sealed.encrypted_backup(settings,failed,True)) and failed.is_file() and failed.stat().st_size==20)
            retained=failed.read_bytes()
            check('incomplete_publication_cannot_pass_inspection',rejected(lambda:sealed.inspect_encrypted_backup(failed)))
            check('failed_publication_destination_never_overwritten',rejected(lambda:sealed.encrypted_backup(settings,failed,True),FileExistsError) and failed.read_bytes()==retained)
            retry=root/'publication-retry.enc';retried=sealed.encrypted_backup(settings,retry,True)
            check('fresh_destination_after_failed_publication_succeeds',retried['backup_created'] and sealed.inspect_encrypted_backup(retry)['authenticated'] and failed.read_bytes()==retained)
            replacement=root/'publication-replacement.enc';retired=root/'publication-retired.enc';sentinel=b'Disposable replacement artifact'
            @contextmanager
            def replaced_output(fd,*args,**kwargs):
                with os.fdopen(fd,*args,**kwargs) as output:yield output
                # Closing the fixture handle first makes this race portable.
                replacement.replace(retired);replacement.write_bytes(sentinel)
                raise OSError('Disposable replacement fault')
            replacement_os=LocalKeyOS(environment);replacement_os.fdopen=replaced_output
            with patch.object(sealed,'os',replacement_os):
                check('replacement_artifact_survives_publication_failure',rejected(lambda:sealed.encrypted_backup(settings,replacement,True)) and
                    replacement.is_file() and replacement.read_bytes()==sentinel and sealed.inspect_encrypted_backup(retired)['authenticated'])
            check('private_plaintext_temporary_directories_removed',not list(root.glob('.nexus-private-*')) and not list(root.glob('nexus-restore-inspection-*')))
        check('source_records_unchanged_after_all_checks',records(control)==original_control and records(business)==original_business)
        check('original_snapshots_remain_valid',inspect_backup(plain)['checksums_valid'] and manifest.read_bytes()==manifest_bytes and
            snapshot.read_bytes()==snapshot_bytes and records(plain/'business.sqlite3')==original_business and destination.read_bytes()==blob)
        report['successful_backup_count']=3;report['source_account_count']=3;report['passed']=True
    except DrillFailure as exc:report['failure']=str(exc)
    except Exception:report['failure']='isolated_drill_could_not_finish'
    finally:
        if engine is not None:engine.dispose()
        gc.collect()
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Exercise disposable backup safeguards without operator settings or keys.')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/drills')
    args=parser.parse_args(argv)
    try:
        destination=args.output_dir.resolve();destination.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.backup-',dir=destination) as scratch:
            if Path(scratch).resolve().parent!=destination:raise ValueError('Invalid temporary directory')
            result=run_drill(Path(scratch)/'workspace')
        report=destination/('synthetic-backup-'+uuid.uuid4().hex+'.json')
        with report.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2)
        print(json.dumps({'passed':result['passed'],'steps_passed':sum(row['passed'] for row in result['steps']),'report':str(report),'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError,ValueError):
        print(json.dumps({'passed':False,'failure':'Could not create or clean up the disposable drill report.','boundary':BOUNDARY}));return 1


if __name__=='__main__':raise SystemExit(main())
