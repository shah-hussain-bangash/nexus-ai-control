"""Private, checksummed backups. Restore inspection never overwrites live data."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from sqlalchemy.engine import make_url


def sqlite_snapshot(source, destination):
    if not Path(source).is_file(): raise RuntimeError('Configured SQLite file is missing; backup stopped.')
    with closing(sqlite3.connect(str(source))) as src, closing(sqlite3.connect(str(destination))) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('SQLite integrity check failed.')
    os.chmod(destination, 0o600)


def backup(settings, destination, quiesced=False):
    if not quiesced: raise RuntimeError('Stop API and worker, then pass --quiesced to acknowledge cross-database consistency.')
    target=Path(destination).resolve();target.mkdir(mode=0o700,parents=True,exist_ok=False)
    url=make_url(settings.database_url)
    if url.get_backend_name()=='sqlite':
        sqlite_snapshot(url.database,target/'control.sqlite3');kind='sqlite'
        with closing(sqlite3.connect(target/'control.sqlite3')) as db: schema=db.execute('SELECT max(version) FROM schema_versions').fetchone()[0]
    elif url.get_backend_name()=='postgresql':
        env=os.environ.copy()
        env.update(PGHOST=url.host or '',PGPORT=str(url.port or 5432),PGDATABASE=url.database or '',PGUSER=url.username or '',PGPASSWORD=url.password or '')
        for key in ('sslmode','sslrootcert','sslcert','sslkey'):
            if key in url.query:env['PG'+key.upper()]=url.query[key]
        # Credentials stay out of argv and errors; pg_dump must be provisioned by the operator.
        try:subprocess.run(['pg_dump','--format=custom','--no-owner','--file',str(target/'control.dump')],env=env,check=True,capture_output=True,timeout=900)
        except (subprocess.SubprocessError,OSError):raise RuntimeError('PostgreSQL backup failed; review protected operator logs and pg_dump availability.') from None
        os.chmod(target/'control.dump',0o600);kind='postgresql'
        from sqlalchemy import create_engine, text
        engine=create_engine(settings.database_url)
        try:
            with engine.connect() as db: schema=db.scalar(text('SELECT max(version) FROM schema_versions'))
        finally: engine.dispose()
    else: raise RuntimeError('Unsupported backup database.')
    if Path(settings.mock_database).exists():sqlite_snapshot(settings.mock_database,target/'business.sqlite3')
    files=[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in target.iterdir() if p.is_file()]
    manifest={'schema':schema,'kind':kind,'files':files,'contains_sensitive_data':True,'encrypted_by_application':False,'requires_external_encryption_and_retention':True}
    p=target/'manifest.json';p.write_text(json.dumps(manifest,indent=2)+'\n');os.chmod(p,0o600)
    return {'backup_created':True,'directory':str(target),'kind':kind,'files':len(files),'restore_verified':False}


def inspect_backup(directory):
    root=Path(directory).resolve();manifest=json.loads((root/'manifest.json').read_text())
    for item in manifest['files']:
        if Path(item['name']).name!=item['name']:raise RuntimeError('Unsafe backup path.')
        path=root/item['name']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Backup checksum mismatch.')
        if path.suffix=='.sqlite3':
            with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed.')
    return {'checksums_valid':True,'sqlite_integrity_valid':True,'postgresql_restore_verified':False,'kind':manifest['kind']}
