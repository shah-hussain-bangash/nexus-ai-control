"""Offline checker policy fixtures are invented metadata, not restore evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import warnings
import zipfile
import pytest

SCRIPT=Path(__file__).resolve().parents[2]/'scripts/verify_recovery_evidence.py'
spec=importlib.util.spec_from_file_location('reviewed_offline_checker',SCRIPT)
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
REVISION='a'*40
TREE='c'*40
HISTORICAL='b'*40
TOTALS={'tests':1,'failures':0,'errors':0,'skipped':0}
XML=b'<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="policy_fixture"/></testsuite></testsuites>'
API={'ready':200,'known_record_listing':200,'authorized_new_write':201,'auditor_write':403}
HIST_API={'ready':200,'known_marker_read':200,'historical_document_read':200,'authorized_new_write':201,'auditor_write':403,'auditor_restricted_document':404}
VALID={'authenticated':True,'checksums_valid':True,'sqlite_integrity_valid':True}
STAGES=(
 ('restored-application','run_restore_verification.py','restore-receipt.json'),
 ('interrupted-copy-retry','run_retry_verification.py','retry-receipt.json'),
 ('schema-markers','run_schema_verification.py','schema-receipt.json'),
 ('snapshot-isolation','run_snapshot_verification.py','snapshot-receipt.json'),
 ('historical-upgrade','historical/run_historical_verification.py','historical-receipt.json'),
 ('upgrade-rollback','rollback/run_rollback_verification.py','migration-rollback-receipt.json'),
 ('abrupt-process-exit','crash/run_crash_verification.py','process-crash-receipt.json'),
 ('committed-wal','run_wal_snapshot_verification.py','wal-snapshot-receipt.json'),
 ('declared-relationships','run_relationship_verification.py','relationship-receipt.json'),
)


def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True).encode()


def base_files():
    files={};stages=[]
    for name,script,receipt in STAGES:
        r={'passed':True,'revision':REVISION,'git_tree':TREE,'schema_version':11,'source_status':'unchanged_clean',
            'fixtures_cleaned':True,'blockers':[],'regression_tests':dict(TOTALS),
            'operator_configuration_loaded':False,'live_app_changed':False,'external_system_contacted':False,'merged':False,'deployed':False,
            'reproduction':{'script_sha256':None},'artifacts_sha256':{'regression.xml':sha(XML)}}
        if name=='restored-application':
            r.pop('fixtures_cleaned');r['fixture_files_cleaned']=True
            r.update(file_validity=dict(VALID),file_copy_only={'isolated_copy_created':True,'application_started':False,'restore_verified':False},
                functioning_restored_application={'verified':True,'separate_copy':True,'recovered_migration_or_seed':False,
                    'api_statuses':{'ready_status':200,'known_record_listing_status':200,'authorized_new_write_status':201,
                        'auditor_write_status':403,'cross_workspace_history_status':404,'anonymous_or_revoked_identity_status':401}})
        elif name=='interrupted-copy-retry':
            r.pop('fixtures_cleaned');r['cases']=[]
            for fault in ('copy','fsync','verification'):
                r['cases'].append({'fault':fault,'passed':True,'fixtures_cleaned':True,'recovered_api':dict(API),'proof':{
                    **{key:True for key in ('injected_failure_rejected','partial_directory_retained_during_failure','same_path_retry_refused',
                        'partial_bytes_preserved_on_retry','fresh_directory_copy_succeeded','fresh_copy_opened_in_isolation')},
                    'copy_primitive_claims_application_restore':False}})
        elif name=='schema-markers':
            r['cases']=[]
            for marker in (10,11,12):
                app={'startup_accepted':marker==11}
                if marker==11:app.update(ready_status=200,known_record_status=200,authorized_new_write_status=201,auditor_write_status=403)
                else:app.update(startup_refusal_verified=True,diagnostic_ready_status=503,logical_copy_unchanged_after_refusal=True)
                r['cases'].append({'fixture_schema_marker':marker,'passed':True,'file_validity':dict(VALID),
                    'recovered_migration_or_seed':False,'isolated_file_copy_created':True,'copy_primitive_claims_application_restore':False,'application':app})
        elif name=='snapshot-isolation':
            r.update(revision_observations={'at_backup':1,'later_source':2,'initial_restore':1,'independent_restored_edit':2},
                business_receipt_counts={'at_backup':1,'later_source':2,'restore':1},restored_api=dict(API))
        elif name=='historical-upgrade':
            r.update(historical_revision=HISTORICAL,historical_schema=10,restored_schema=11,dependency_declarations_match=True,restored_api=dict(HIST_API))
        elif name=='upgrade-rollback':
            r['rollback_proof']={key:True for key in ('failure_after_real_populated_table_rebuild','all_logical_rows_rolled_back',
                'all_table_index_trigger_definitions_rolled_back','schema_marker_remained_10','migration_scratch_tables_absent',
                'foreign_keys_reenabled','sqlite_integrity_valid','declared_foreign_keys_valid','app_startup_refused_after_failed_upgrade',
                'retry_upgraded_only_the_restored_copy')}
            r['rollback_proof']['completed_rebuilds_before_fault']=2;r['post_retry_api']=dict(HIST_API)
        elif name=='abrupt-process-exit':
            r['crash_proof']={'process_exit_code':73,'crash_point':{'stage':'after_populated_table_rebuild','completed_rebuilds':2,
                'uncommitted_wal_growth_observed':True,'migration_commit_not_reached':True},
                'fresh_process_reopen':{key:True for key in ('fresh_process_records_preserved','fresh_process_schema_and_indexes_preserved',
                    'schema_remained_10','integrity_valid','foreign_keys_valid_and_enabled','migration_scratch_tables_absent')},
                'parent_reopen_records_and_schema_preserved':True,'app_startup_stayed_blocked_at_schema10':True,'explicit_retry_upgraded_restored_copy':True}
            r['post_retry_api']=dict(HIST_API)
        elif name=='committed-wal':
            r.update(main_file_only_negative_controls={'physical_integrity_valid':True,'control_marker_count':0,'business_receipt_count':0},
                restored_counts={'control_marker_count':1,'business_receipt_count':1},restored_api=dict(API))
        else:
            r['negative_cases']=[{'case':case,'passed':True,**{key:True for key in ('encryption_authenticated','manifest_checksums_and_sizes_valid',
                'sqlite_physical_integrity_valid','invalid_declared_relationship_verified','native_inspection_rejected',
                'native_copy_rejected_before_destination_creation','input_bytes_preserved')}}
                for case in ('orphan-control','orphan-business','malformed-control-reference')]
            r['valid_backup_positive_control']={'passed':True,'restored_api':dict(API)}
        script_path='reproduce/scripts/'+script
        # Acceptance of the archive must not execute these deliberately failing scripts.
        files[script_path]=b'raise RuntimeError("fixture archive scripts must never execute")\n'
        r['reproduction']['script_sha256']=sha(files[script_path])
        files[name+'/regression.xml']=XML;files[name+'/'+receipt]=encoded(r)
        stages.append({'stage':name,'passed':True,'receipt':name+'/'+receipt,'receipt_sha256':sha(files[name+'/'+receipt]),'regression_tests':dict(TOTALS)})
    index={'format':'nexus-disposable-recovery-evidence-pack','format_version':2,'passed':True,
        'revision':REVISION,'git_tree':TREE,'historical_revision':HISTORICAL,'schema_version':11,'fixtures_cleaned':True,
        'operator_configuration_loaded':False,'live_app_changed':False,'external_system_contacted':False,'merged':False,'deployed':False,
        'blockers':[],'stage_counts_overlap':True,'stages':stages,'skipped_checks':[],'artifacts_sha256':{}}
    files['evidence-index.json']=encoded(index);seal(files);return files


def seal(files):
    index=json.loads(files['evidence-index.json'])
    for stage in index['stages']:
        path=stage['receipt'];r=json.loads(files[path]);prefix=stage['stage']+'/'
        for relative in r['artifacts_sha256']:r['artifacts_sha256'][relative]=sha(files[prefix+relative.replace('\\','/')])
        files[path]=encoded(r);stage['receipt_sha256']=sha(files[path])
    index['artifacts_sha256']={name:sha(data) for name,data in files.items() if name not in ('evidence-index.json','evidence-index.sha256')}
    files['evidence-index.json']=encoded(index)
    files['evidence-index.sha256']=(sha(files['evidence-index.json'])+'  evidence-index.json\n').encode()


def alter(files,stage,edit):
    index=json.loads(files['evidence-index.json']);path=next(s['receipt'] for s in index['stages'] if s['stage']==stage)
    r=json.loads(files[path]);edit(r);files[path]=encoded(r);seal(files)


def write(tmp_path,files,extra=None):
    path=tmp_path/'evidence.zip'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,data in files.items():archive.writestr(name,data)
            if extra:archive.writestr(*extra)
    return path


def rejects(path,code,**pins):
    with pytest.raises(checker.EvidenceError) as error:checker.verify(path,**pins)
    assert str(error.value)==code


def test_consistent_fixture_is_not_authenticated_or_executed(tmp_path):
    path=write(tmp_path,base_files());result=checker.verify(path,sha(path.read_bytes()),REVISION)
    assert result['stages_verified']==9 and result['recorded_results_consistent']
    assert not result['authenticated_signature'] and not result['bundle_scripts_executed'] and not result['application_or_database_opened']


@pytest.mark.parametrize('fault',['rollback','fresh_process','file_validity','repeated_scenarios','cleanup','unique_counts'])
def test_recomputed_hashes_do_not_replace_required_proof(tmp_path,fault):
    files=base_files()
    if fault=='rollback':alter(files,'upgrade-rollback',lambda r:r.update(rollback_proof={'completed_rebuilds_before_fault':2}))
    elif fault=='fresh_process':alter(files,'abrupt-process-exit',lambda r:r['crash_proof'].update(fresh_process_reopen={}))
    elif fault=='file_validity':alter(files,'schema-markers',lambda r:r['cases'][0].update(file_validity={}))
    elif fault=='repeated_scenarios':alter(files,'declared-relationships',lambda r:r.update(negative_cases=[r['negative_cases'][0]]*3))
    elif fault=='cleanup':alter(files,'snapshot-isolation',lambda r:r.update(fixtures_cleaned=False))
    else:
        index=json.loads(files['evidence-index.json']);index['stage_counts_overlap']=False;files['evidence-index.json']=encoded(index);seal(files)
    rejects(write(tmp_path,files),'STAGE_SCHEMA' if fault=='cleanup' else 'PACK_SCHEMA' if fault=='unique_counts' else 'RECORDED_CHECKS')


def test_rehashed_authorization_success_cannot_pass(tmp_path):
    files=base_files();alter(files,'restored-application',lambda r:r['functioning_restored_application']['api_statuses'].update(auditor_write_status=200))
    rejects(write(tmp_path,files),'API_STATUS')


def test_windows_receipt_references_normalize_without_relaxing_zip_paths(tmp_path):
    files=base_files();path='restored-application/restore-receipt.json';r=json.loads(files[path])
    data=files.pop('restored-application/regression.xml');files['restored-application/logs/regression.xml']=data
    r['artifacts_sha256']={'logs\\regression.xml':sha(data)};files[path]=encoded(r);seal(files)
    assert checker.verify(write(tmp_path,files))['verification']=='consistent'


@pytest.mark.parametrize('pin,code',[('hash','EXPECTED_HASH'),('revision','EXPECTED_REVISION')])
def test_optional_external_pins_must_match(tmp_path,pin,code):
    rejects(write(tmp_path,base_files()),code,**({'expected_sha256':'0'*64} if pin=='hash' else {'expected_revision':'0'*40}))


def test_changed_artifact_is_rejected(tmp_path):
    files=base_files();files['restored-application/regression.xml']+=b' '
    rejects(write(tmp_path,files),'ARTIFACT_HASH')


def test_missing_report_is_rejected(tmp_path):
    files=base_files();del files['restored-application/regression.xml']
    rejects(write(tmp_path,files),'MANIFEST_FILES')


def test_rehashed_junit_counts_cannot_hide_a_failure(tmp_path):
    files=base_files();files['restored-application/regression.xml']=XML.replace(b'<testcase name="policy_fixture"/>',b'<testcase name="policy_fixture"><failure/></testcase>');seal(files)
    rejects(write(tmp_path,files),'TEST_RESULTS')


def test_xml_entities_are_not_processed(tmp_path):
    files=base_files();files['restored-application/regression.xml']=b'<!DOCTYPE fixture [<!ENTITY x "fixture">]>'+XML;seal(files)
    rejects(write(tmp_path,files),'XML_FORMAT')


@pytest.mark.parametrize('name',['../outside.json','/absolute.json','C:drive.json','alias\\path.json'])
def test_unsafe_zip_names_are_rejected_without_extraction(tmp_path,name):
    # Windows ZipInfo normalizes backslashes while writing; preserve the raw
    # hostile name in both headers so this also exercises the reader on Windows.
    stored_name=name.replace('\\','/')
    path=write(tmp_path,base_files(),(stored_name,b'{}'))
    if stored_name!=name:
        path.write_bytes(path.read_bytes().replace(stored_name.encode(),name.encode()))
    rejects(path,'ZIP_PATH')
    assert {p.name for p in tmp_path.iterdir()}=={'evidence.zip'}


def test_duplicate_zip_entry_is_rejected(tmp_path):
    files=base_files();rejects(write(tmp_path,files,('evidence-index.json',files['evidence-index.json'])),'ZIP_DUPLICATE')


def test_duplicate_json_key_is_rejected(tmp_path):
    files=base_files();files['evidence-index.json']=files['evidence-index.json'].replace(b'"passed": true',b'"passed": true, "passed": true',1)
    files['evidence-index.sha256']=(sha(files['evidence-index.json'])+'  evidence-index.json\n').encode()
    rejects(write(tmp_path,files),'JSON_AMBIGUOUS')


def test_truncated_zip_is_a_fixed_error(tmp_path):
    path=tmp_path/'evidence.zip';path.write_bytes(b'PK truncated fixture')
    rejects(path,'UNREADABLE_OR_INVALID_EVIDENCE')


def test_large_member_is_refused_before_parsing(tmp_path):
    files=base_files();files['oversized.json']=b'x'*(2*1024*1024+1)
    rejects(write(tmp_path,files),'ARCHIVE_SIZE')


def test_ordinary_drill_report_is_not_a_version_two_pack(tmp_path):
    rejects(write(tmp_path,{'synthetic-drill.json':b'{"passed":true}'}),'MANIFEST_FILES')


def test_cli_runs_in_isolation_without_app_settings_and_has_failure_exit(tmp_path):
    path=write(tmp_path,base_files());environment={key:os.environ[key] for key in ('SystemRoot','WINDIR','PATH','TEMP','TMP') if key in os.environ}
    environment.update(NEXUS_MODE='broken-fixture',NEXUS_DATABASE_URL='unsupported-fixture://no-database')
    good=subprocess.run([sys.executable,'-I',str(SCRIPT),str(path)],cwd=tmp_path,env=environment,capture_output=True,text=True,timeout=15)
    assert good.returncode==0 and not json.loads(good.stdout)['application_or_database_opened']
    bad=subprocess.run([sys.executable,'-I',str(SCRIPT),str(path),'--expected-sha256','0'*64],cwd=tmp_path,env=environment,capture_output=True,text=True,timeout=15)
    assert bad.returncode==1 and json.loads(bad.stdout)['error_code']=='EXPECTED_HASH'
    assert {p.name for p in tmp_path.iterdir()}=={'evidence.zip'}
