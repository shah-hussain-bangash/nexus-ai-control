"""Consistent SQLite backup of local control + mock stores. Stop the worker first.
For PostgreSQL use a reviewed pg_dump/PITR procedure; this script refuses non-SQLite.
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'backend'))
from nexus.config import Settings
import os
os.chdir(root/'backend');settings=Settings.from_env()
if not settings.database_url.startswith('sqlite:///'): raise SystemExit('PostgreSQL backup requires the deployment runbook, not this local utility.')
folder=Path(sys.argv[1] if len(sys.argv)>1 else '../../backups')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
folder.mkdir(parents=True,exist_ok=False)
for label,path in [('control',settings.database_url.removeprefix('sqlite:///')),('mock_business',settings.mock_database)]:
 with sqlite3.connect(path) as source,sqlite3.connect(folder/(label+'.db')) as target:
  source.backup(target)
print('Backup created. Keep workers off during restore and reconcile external effects before dispatch.')
