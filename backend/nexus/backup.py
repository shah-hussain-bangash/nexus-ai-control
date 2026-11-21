"""Private, checksummed backups. Restore inspection never overwrites live data."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
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


def inspection_manifest(root):
    try:
        source=root/'manifest.json'
        if source.is_symlink() or not source.is_file():raise ValueError()
        manifest=json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(manifest,dict) or manifest.get('kind') not in ('sqlite','postgresql') or type(manifest.get('schema')) is not int or manifest['schema']<1:raise ValueError()
        files=manifest.get('files')
        if not isinstance(files,list) or not files:raise ValueError()
        names=set()
        for item in files:
            if not isinstance(item,dict):raise ValueError()
            name=item.get('name');size=item.get('bytes');checksum=item.get('sha256')
            if not isinstance(name,str) or not name or name.rstrip(' .')!=name or Path(name).name!=name or any(char in name for char in ('/','\\',':','\0')) or name.casefold() in names:raise ValueError()
            if type(size) is not int or size<0 or not isinstance(checksum,str) or not re.fullmatch(r'[a-f0-9]{64}',checksum):raise ValueError()
            names.add(name.casefold())
        required='control.sqlite3' if manifest['kind']=='sqlite' else 'control.dump'
        opposite='control.dump' if manifest['kind']=='sqlite' else 'control.sqlite3'
        if opposite in names or not any(item['name']==required and item['bytes']>0 for item in files):raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):
        raise RuntimeError('Invalid backup manifest or missing required database snapshot.') from None
    return manifest


def inspect_backup(directory):
    root=Path(directory).resolve();manifest=inspection_manifest(root)
    for item in manifest['files']:
        path=root/item['name']
        try:
            if path.is_symlink() or not path.is_file():raise RuntimeError('Missing or unsafe backup member.')
            if path.stat().st_size!=item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Backup checksum or size mismatch.')
            if path.suffix=='.sqlite3':
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed.')
                    if item['name']=='control.sqlite3' and db.execute('SELECT max(version) FROM schema_versions').fetchone()[0]!=manifest['schema']:raise RuntimeError('Backup schema metadata mismatch.')
        except (OSError,sqlite3.Error):
            raise RuntimeError('Backup member inspection failed; no application data was overwritten.') from None
    return {'checksums_valid':True,'sqlite_integrity_valid':True,'postgresql_restore_verified':False,'kind':manifest['kind']}
