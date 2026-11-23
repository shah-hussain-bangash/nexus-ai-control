"""Exercise a recovered, disposable SQLite application through its in-process API."""
import argparse
import base64
from dataclasses import replace
from datetime import datetime,timezone
import gc
import json
import logging
import os
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import uuid
from fastapi.testclient import TestClient
from . import __version__,encrypted_backup as sealed
from .app import create_app
from .backup_drill import DrillFailure,LocalKeyOS,records
from .cli import seed
from .config import Settings
from .db import CURRENT_SCHEMA,migrate
from .mock_connector import MockBusiness

BOUNDARY=('Disposable synthetic encrypted SQLite recovery and in-process API exercise only. '
    'No active application database was restored or overwritten. No customer system or model provider was contacted. '
    'This is not deployment cutover, PostgreSQL recovery, measured RPO/RTO, authenticated drill evidence or production readiness.')


def run_drill(directory):
    root=Path(directory).resolve();root.mkdir(exist_ok=False)
    source=root/'source';source.mkdir()
    control=source/'control.db';business=source/'business.db'
    settings=Settings(database_url='sqlite:///'+control.as_posix(),mock_database=str(business),
        secret=secrets.token_urlsafe(48),agent_secret=secrets.token_urlsafe(48),frontend_dir=str(root/'no-frontend'),
        mode='local',policy_mode='reference',business_connector='synthetic',live_inference=0)
    result={'format':'nexus-synthetic-recovery-drill','format_version':1,'release':__version__,'schema_version':CURRENT_SCHEMA,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'connector_mode':'synthetic','key_mode':'ephemeral_disposable',
        'passed':False,'synthetic_api_exercised':False,'active_database_restored':False,
        'postgresql_restore_verified':False,'customer_acceptance':False,'production_ready':False,'steps':[],'boundary':BOUNDARY}
    apps=[];logger=logging.getLogger('nexus.http');previously_disabled=logger.disabled;logger.disabled=True
    password=secrets.token_urlsafe(32);environment={};key=os.urandom(32)
    payload={'kind':'prompt','name':'Disposable recovery marker','description':'Synthetic recovery exercise',
        'config':{'template':'Evidence: {{question}} / {{context}}','required_terms':['Evidence'],'forbidden_terms':['invent']}}
    def check(name,condition):
        result['steps'].append({'id':name,'passed':bool(condition)})
        if not condition:raise DrillFailure(name)
    def expect(response,status):
        if response.status_code!=status:raise DrillFailure('unexpected_api_response')
        return response.json()
    def login(client,email='owner@nexus.local'):
        expect(client.post('/auth/local/login',json={'email':email,'password':password}),200)
    def headers(client):
        me=expect(client.get('/v1/me'),200);context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'],'X-Nexus-Context-Revision':str(context['revision'])}
    def rejected(operation,error=RuntimeError):
        try:operation()
        except error:return True
        return False
    def private_temp(**kwargs):
        kwargs.setdefault('dir',root)
        return TemporaryDirectory(**kwargs)
    try:
        original=create_app(settings);apps.append(original)
        check('source_runtime_is_disposable_and_synthetic',type(original.state.connector) is MockBusiness and settings.live_inference==0)
        migrate(original.state.engine,original.state.factory);seed(original.state.factory,password)
        with TestClient(original) as client:
            login(client);owner=expect(client.get('/v1/me'),200)
            marker=expect(client.post('/v1/workbench',json=payload,headers=headers(client)),201)
            token=client.cookies.get('nexus_session')
            check('source_login_and_marker_saved',bool(token) and owner['user']['role']=='owner' and marker['version']==1)
        # This is fixture data, not governed dispatch or customer acceptance.
        receipt=original.state.connector.invoke('synthetic-recovery-receipt',{'action':'supplier:read','arguments':{'supplier_id':'SUP-DEMO-104'}})
        check('source_synthetic_receipt_saved',original.state.connector.count()==1 and bool(receipt))
        original.state.engine.dispose();gc.collect()
        before_control=records(control);before_business=records(business)
        check('source_has_three_disposable_accounts',before_control['users'][0]==3)
        archive=root/'backup.enc';target=root/'recovered'
        with patch.object(sealed,'os',LocalKeyOS(environment)),patch.object(sealed,'tempfile',SimpleNamespace(TemporaryDirectory=private_temp)):
            environment[sealed.KEY_ENV]=base64.b64encode(key).decode()
            saved=sealed.encrypted_backup(settings,archive,True);blob=archive.read_bytes()
            check('quiesced_encrypted_fixture_created',saved['encrypted_by_application'] and not saved['restore_verified'])
            environment[sealed.KEY_ENV]=base64.b64encode(os.urandom(32)).decode()
            check('wrong_key_creates_no_recovery_directory',rejected(lambda:sealed.recover_encrypted_sqlite(archive,target)) and not target.exists())
            environment[sealed.KEY_ENV]=base64.b64encode(key).decode()
            check('existing_source_directory_rejected',rejected(lambda:sealed.recover_encrypted_sqlite(archive,source),FileExistsError))
            copied=sealed.recover_encrypted_sqlite(archive,target)
            check('authenticated_copy_never_activates_application',copied['isolated_copy_created'] and copied['authenticated'] and
                not any(copied[field] for field in ('active_data_overwritten','application_started','restore_verified','postgresql_restore_verified')))
            check('all_control_records_recovered',records(target/'control.sqlite3')==before_control)
            check('all_business_records_recovered',records(target/'business.sqlite3')==before_business)
            check('inspection_plaintext_temporaries_removed',not list(root.glob('nexus-restore-inspection-*')) and not list(root.glob('.nexus-private-*')))
        recovered_settings=replace(settings,database_url='sqlite:///'+(target/'control.sqlite3').as_posix(),mock_database=str(target/'business.sqlite3'))
        recovered=create_app(recovered_settings);apps.append(recovered)
        check('recovered_runtime_remains_synthetic',type(recovered.state.connector) is MockBusiness and recovered_settings.live_inference==0)
        # Deliberately do not migrate or seed the recovered database.
        with TestClient(recovered) as client:
            ready=expect(client.get('/health/ready'),200)
            check('recovered_schema_ready_without_migration',ready['status']=='ready' and ready['schema_version']==CURRENT_SCHEMA)
            check('anonymous_recovered_access_blocked',client.get('/v1/me').status_code==401)
            # Sessions are opaque database records: a copied session remains valid
            # until expiry or explicit revocation. Secrets do not sign this cookie.
            client.cookies.set('nexus_session',token,domain='testserver.local',path='/')
            copied_owner=expect(client.get('/v1/me'),200)
            check('copied_session_preserves_owner_and_staging_context',copied_owner['user']['id']==owner['user']['id'] and copied_owner['environment']=='staging')
            response=client.post('/auth/logout',headers=headers(client))
            check('copied_session_can_be_revoked',response.status_code==200)
            client.cookies.clear();client.cookies.set('nexus_session',token,domain='testserver.local',path='/')
            check('revoked_copied_session_cannot_authenticate',client.get('/v1/me').status_code==401)
            client.cookies.clear();login(client)
            fresh=expect(client.get('/v1/me'),200)
            check('recovered_credentials_allow_fresh_login',fresh['user']['id']==owner['user']['id'] and fresh['environment']=='staging')
            runtime=expect(client.get('/v1/runtime'),200)
            check('live_inference_disabled',runtime['enabled'] is False)
            listing=expect(client.get('/v1/workbench'),200)
            check('recovered_marker_is_readable',len(listing['assets'])==1 and listing['assets'][0]['id']==marker['id'] and listing['assets'][0]['config']==payload['config'])
            endpoint='/v1/workbench/'+marker['id']
            run_body={'query':'Synthetic question','variables':{'context':'Grounded example'}}
            check('recovered_write_requires_csrf',client.post(endpoint+'/run',json=run_body).status_code==403)
            preview=expect(client.post(endpoint+'/run',json=run_body,headers=headers(client)),200)
            check('recovered_local_prompt_preview_works',preview['status']=='completed' and preview['result']['rendered']=='Evidence: Synthetic question / Grounded example' and
                all(row['passed'] for row in preview['result']['checks']))
            client.cookies.clear();login(client,'auditor@nexus.local')
            check('recovered_auditor_can_read',expect(client.get('/v1/workbench'),200)['assets'][0]['id']==marker['id'])
            check('recovered_auditor_cannot_write',client.post('/v1/workbench',json=payload,headers=headers(client)).status_code==403)
            client.cookies.clear();login(client)
            added=expect(client.post('/v1/workbench',json={**payload,'name':'Recovered copy only'},headers=headers(client)),201)
            check('new_records_can_be_written_to_recovered_copy',added['id']!=marker['id'] and len(expect(client.get('/v1/workbench'),200)['assets'])==2)
            edit={**payload,'name':'Revised recovered marker','expected_version':1}
            updated=expect(client.put(endpoint,json=edit,headers=headers(client)),200)
            check('recovered_revision_can_advance',updated['version']==2)
            check('stale_recovered_revision_rejected',client.put(endpoint,json=edit,headers=headers(client)).status_code==409)
            history=expect(client.get(endpoint+'/history'),200)
            check('recovered_original_revision_retained',[row['version'] for row in history]==[2,1] and history[1]['snapshot']['name']==payload['name'])
            check('synthetic_receipt_preserved_without_redispatch',recovered.state.connector.lookup('synthetic-recovery-receipt')==receipt and recovered.state.connector.count()==1)
        recovered.state.engine.dispose();gc.collect()
        check('source_records_and_sessions_unchanged',records(control)==before_control and records(business)==before_business)
        check('encrypted_input_unchanged',archive.read_bytes()==blob)
        result['source_account_count']=3;result['synthetic_api_exercised']=True;result['passed']=True
    except DrillFailure as exc:result['failure']=str(exc)
    except Exception:result['failure']='isolated_recovery_drill_could_not_finish'
    finally:
        for app in apps:app.state.engine.dispose()
        logger.disabled=previously_disabled;gc.collect()
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Exercise encrypted recovery using disposable SQLite data and an in-process API.')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/drills')
    args=parser.parse_args(argv)
    try:
        destination=args.output_dir.resolve();destination.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.recovery-',dir=destination) as scratch:
            if Path(scratch).resolve().parent!=destination:raise ValueError('Invalid temporary directory')
            result=run_drill(Path(scratch)/'workspace')
        report=destination/('synthetic-recovery-'+uuid.uuid4().hex+'.json')
        with report.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2)
        print(json.dumps({'passed':result['passed'],'steps_passed':sum(row['passed'] for row in result['steps']),'report':str(report),'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError,ValueError):
        print(json.dumps({'passed':False,'failure':'Could not create or clean up the disposable recovery report.','boundary':BOUNDARY}));return 1


if __name__=='__main__':raise SystemExit(main())
