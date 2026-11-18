import json
import sqlite3
from pathlib import Path
import pytest
from nexus.backup import backup, inspect_backup
from nexus.db import SchemaVersion


def test_backup_consistency_acknowledgement_and_integrity(ctx,tmp_path):
    destination=tmp_path/'private-backup'
    with pytest.raises(RuntimeError):backup(ctx['settings'],destination)
    report=backup(ctx['settings'],destination,quiesced=True)
    assert report['backup_created'] and not report['restore_verified']
    assert inspect_backup(destination)['checksums_valid']
    with sqlite3.connect(destination/'control.sqlite3') as restored:
        assert restored.execute('SELECT max(version) FROM schema_versions').fetchone()[0]==8
        assert restored.execute('SELECT count(*) FROM users').fetchone()[0]>=3
    with pytest.raises(FileExistsError):backup(ctx['settings'],destination,True)
    manifest=json.loads((destination/'manifest.json').read_text());assert 'secret' not in (destination/'manifest.json').read_text()
    file=destination/manifest['files'][0]['name'];file.write_bytes(file.read_bytes()+b'tampered')
    with pytest.raises(RuntimeError,match='checksum'):inspect_backup(destination)


def test_chunked_request_cap_and_trace_header(ctx):
    client=ctx['client']
    response=client.post('/auth/local/login',content=iter([b'x'*40000,b'y'*40000]),headers={'content-type':'application/json'})
    assert response.status_code==413 and len(response.headers['x-request-id'])==32
    assert client.get('/health/live').headers['x-request-id']
