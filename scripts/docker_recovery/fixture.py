"""Prepare only new synthetic SQLite recovery files; never start Docker."""
import base64
from dataclasses import replace
from datetime import datetime, timezone
import gc
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import patch



def forbidden(*args,**kwargs):raise RuntimeError('Forbidden fixture operation.')


def prepare(repo,destination,password,revision):
    if not __debug__:raise RuntimeError('Optimized Python is unsupported for this drill.')
    repo=Path(repo).resolve()
    assert not destination.exists() and destination.resolve().parent.is_dir()
    destination.mkdir(exist_ok=False)
    sys.path.insert(0,str(repo/'backend'))
    import httpx
    from fastapi.testclient import TestClient
    from nexus.app import create_app
    from nexus.config import Settings
    from nexus.cli import seed
    from nexus.db import migrate,CURRENT_SCHEMA
    from nexus import encrypted_backup as sealed,backup as backup_module
    from nexus.backup_drill import records,LocalKeyOS
    clock=time.perf_counter();started=datetime.now(timezone.utc).isoformat()
    source=destination/'source';source.mkdir()
    recovered=destination/'recovered'
    settings=Settings(database_url='sqlite:///'+(source/'control.db').as_posix(),mock_database=str(source/'business.db'),
        secret=secrets.token_urlsafe(48),agent_secret=secrets.token_urlsafe(48),frontend_dir=str(destination/'no-frontend'),
        mode='local',policy_mode='reference',business_connector='synthetic',live_inference=0)
    payload={'kind':'prompt','name':'Disposable Docker recovery marker','description':'Synthetic Docker recovery fixture',
        'config':{'template':'Evidence: {{question}} / {{context}}','required_terms':['Evidence'],'forbidden_terms':['invent']}}
    checks=[];apps=[];statuses={}
    def check(name,value):
        checks.append({'id':name,'passed':bool(value)})
        if not value:raise RuntimeError('Synthetic fixture check failed: '+name)
    def headers(client):
        response=client.get('/v1/me');assert response.status_code==200
        me=response.json();context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'],'X-Nexus-Context-Revision':str(context['revision'])}
    logger=logging.getLogger('nexus.http');prior_disabled=logger.disabled;logger.disabled=True
    try:
        with patch.object(Settings,'from_env',forbidden),patch.object(backup_module.subprocess,'run',forbidden),\
             patch.object(httpx.HTTPTransport,'handle_request',forbidden),patch.object(socket,'create_connection',forbidden):
            app=create_app(settings);apps.append(app)
            migrate(app.state.engine,app.state.factory);seed(app.state.factory,password)
            with TestClient(app) as client:
                response=client.post('/auth/local/login',json={'email':'owner@nexus.local','password':password})
                check('synthetic_source_login',response.status_code==200)
                response=client.post('/v1/workbench',json=payload,headers=headers(client))
                check('synthetic_source_marker_created',response.status_code==201)
                marker=response.json()
                check('source_session_logged_out',client.post('/auth/logout',headers=headers(client)).status_code==200)
            app.state.connector.invoke('docker-recovery-fixture',{'action':'supplier:read','arguments':{'supplier_id':'SUP-DEMO-104'}})
            app.state.engine.dispose();gc.collect()
            before_control=records(source/'control.db');before_business=records(source/'business.db')
            check('three_disposable_accounts',before_control['users'][0]==3)
            archive=destination/'synthetic-backup.enc'
            environment={sealed.KEY_ENV:base64.b64encode(os.urandom(32)).decode()}
            def private_temp(**kwargs):
                kwargs.setdefault('dir',destination);return TemporaryDirectory(**kwargs)
            with patch.object(sealed,'os',LocalKeyOS(environment)),patch.object(sealed,'tempfile',SimpleNamespace(TemporaryDirectory=private_temp)):
                saved=sealed.encrypted_backup(settings,archive,True)
                check('encrypted_quiesced_fixture_created',saved['encrypted_by_application'] and not saved['restore_verified'])
                inspection=sealed.inspect_encrypted_backup(archive)
                file_validity={key:inspection[key] for key in ('authenticated','checksums_valid','sqlite_integrity_valid')}
                check('authenticated_backup_and_integrity_pass',all(file_validity.values()))
                archive_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
                copied=sealed.recover_encrypted_sqlite(archive,recovered)
                check('separate_copy_created',copied['isolated_copy_created'] and not copied['active_data_overwritten'])
                check('copy_alone_does_not_claim_running_app',not copied['application_started'] and not copied['restore_verified'])
            environment.clear()
            check('all_control_rows_match_before_probe',records(recovered/'control.sqlite3')==before_control)
            check('all_business_rows_match_before_probe',records(recovered/'business.sqlite3')==before_business)
            probe=create_app(replace(settings,database_url='sqlite:///'+(recovered/'control.sqlite3').as_posix(),mock_database=str(recovered/'business.sqlite3')))
            apps.append(probe)
            # No migration or seed is performed against the recovered copy.
            with TestClient(probe) as client:
                response=client.get('/health/ready');statuses['ready']=response.status_code
                check('recovered_schema_ready_without_migrate_or_seed',response.status_code==200 and response.json()['schema_version']==CURRENT_SCHEMA)
                check('anonymous_probe_rejected',client.get('/v1/me').status_code==401)
                check('recovered_owner_login',client.post('/auth/local/login',json={'email':'owner@nexus.local','password':password}).status_code==200)
                response=client.get('/v1/workbench');statuses['known_record_read']=response.status_code
                check('known_record_and_config_recovered',response.status_code==200 and len(response.json()['assets'])==1 and response.json()['assets'][0]['id']==marker['id'] and response.json()['assets'][0]['config']==payload['config'])
                check('owner_probe_session_logged_out',client.post('/auth/logout',headers=headers(client)).status_code==200)
                client.cookies.clear()
                check('recovered_auditor_login',client.post('/auth/local/login',json={'email':'auditor@nexus.local','password':password}).status_code==200)
                check('auditor_probe_read_allowed',client.get('/v1/workbench').status_code==200)
                response=client.post('/v1/workbench',json=payload,headers=headers(client));statuses['auditor_write']=response.status_code
                check('auditor_write_rejected_with_valid_context',response.status_code==403)
                check('auditor_probe_session_logged_out',client.post('/auth/logout',headers=headers(client)).status_code==200)
            probe.state.engine.dispose();gc.collect()
            check('source_rows_and_business_unchanged',records(source/'control.db')==before_control and records(source/'business.db')==before_business)
            check('encrypted_input_unchanged',hashlib.sha256(archive.read_bytes()).hexdigest()==archive_hash)
            check('inspection_temporaries_removed',not list(destination.glob('nexus-restore-inspection-*')) and not list(destination.glob('.nexus-private-*')))
            check('probe_added_no_business_dispatch',records(recovered/'business.sqlite3')==before_business)
    finally:
        for app in apps:app.state.engine.dispose()
        logger.disabled=prior_disabled;gc.collect()
    check('fixture_paths_owned',all(path.resolve().is_relative_to(destination.resolve()) for path in (source,recovered,archive)))
    receipt={'format':'nexus-disposable-docker-fixture-preparation','format_version':1,'passed':True,
        'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds':round(time.perf_counter()-clock,6),'revision':revision,'schema_version':CURRENT_SCHEMA,
        'checks':checks,'checks_passed':len(checks),'file_validity':file_validity,'probe_api_statuses':statuses,
        'probe_mode':'in_process_only','recovered_migration_or_seed':False,
        'encrypted_archive_sha256':archive_hash,'fixture_account_count':3,
        'password_or_key_written_in_plaintext':False,'archive_key_persisted':False,
        'fixture_files_retained_for_container_review':True,'application_containers_started':False,
        'operator_configuration_loaded':False,'live_app_changed':False,'external_system_contacted':False,'merged':False,'deployed':False,
        'preparation_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'boundary':'Disposable source and recovered fixture files only. Password is stored only as account hashes; archive key is ephemeral and not retained for later reinspection. Probe login/logout changes recovered session/audit rows after the initial copy comparison. Docker mount/image compatibility and runtime acceptance remain untested.'}
    (destination/'fixture-preparation-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    (recovered/'.nexus-disposable-fixture.json').write_text(json.dumps({'format':'nexus-disposable-docker-recovery-fixture',
        'revision':revision,'schema_version':CURRENT_SCHEMA,'synthetic':True,'prepared_for':'nexus-disposable-docker-recovery'}),encoding='utf-8')
    return receipt
