"""Standard-library-only offline consistency checker. Never executes ZIP content."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

MAX_FILES=128
MAX_FILE=2*1024*1024
MAX_TOTAL=16*1024*1024
STAGES={
    'restored-application':('run_restore_verification.py','restore-receipt.json'),
    'interrupted-copy-retry':('run_retry_verification.py','retry-receipt.json'),
    'schema-markers':('run_schema_verification.py','schema-receipt.json'),
    'snapshot-isolation':('run_snapshot_verification.py','snapshot-receipt.json'),
    'historical-upgrade':('historical/run_historical_verification.py','historical-receipt.json'),
    'upgrade-rollback':('rollback/run_rollback_verification.py','migration-rollback-receipt.json'),
    'abrupt-process-exit':('crash/run_crash_verification.py','process-crash-receipt.json'),
    'committed-wal':('run_wal_snapshot_verification.py','wal-snapshot-receipt.json'),
    'declared-relationships':('run_relationship_verification.py','relationship-receipt.json'),
}
FLAGS=('operator_configuration_loaded','live_app_changed','external_system_contacted','merged','deployed')


class EvidenceError(Exception):pass


def require(value,code):
    if not value:raise EvidenceError(code)


def sha(data):return hashlib.sha256(data).hexdigest()


def safe_name(name):
    require(isinstance(name,str) and 0<len(name)<=240,'ZIP_PATH')
    require(not any(c in name for c in ('\\',':','\x00')) and not name.startswith('/'),'ZIP_PATH')
    require(all(part not in ('','.','..') for part in name.split('/')),'ZIP_PATH')
    return name


def json_object(data):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'JSON_AMBIGUOUS');result[key]=value
        return result
    def constant(_):raise EvidenceError('JSON_INVALID')
    try:value=json.loads(data.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,UnicodeError):raise EvidenceError('JSON_INVALID') from None
    require(isinstance(value,dict),'JSON_INVALID');return value


def statuses(values,expected):
    require(isinstance(values,dict) and all(type(values.get(k)) is int and values[k]==v for k,v in expected.items()),'API_STATUS')


def checks(rows,count=None):
    require(isinstance(rows,list) and rows and all(isinstance(r,dict) and isinstance(r.get('id'),str) and r['id'] and r.get('passed') is True for r in rows),'RECORDED_CHECKS')
    require(len({r['id'] for r in rows})==len(rows) and (count is None or len(rows)==count),'RECORDED_CHECKS')


def common_api(values):statuses(values,{'ready':200,'known_record_listing':200,'authorized_new_write':201,'auditor_write':403})


def historical_api(values):statuses(values,{'ready':200,'known_marker_read':200,'historical_document_read':200,
    'authorized_new_write':201,'auditor_write':403,'auditor_restricted_document':404})


def required_truths(values,*names):
    # Missing records cannot prove success: all({}.values()) is vacuously true.
    require(isinstance(values,dict) and names and all(values.get(name) is True for name in names),'RECORDED_CHECKS')


def stage_semantics(name,r,schema):
    if 'checks' in r:checks(r['checks'],r.get('checks_passed'))
    if name=='restored-application':
        require(all(r['file_validity'].get(k) is True for k in ('authenticated','checksums_valid','sqlite_integrity_valid')),'RECORDED_CHECKS')
        copy=r['file_copy_only'];require(copy.get('isolated_copy_created') is True and copy.get('application_started') is False and copy.get('restore_verified') is False,'RECORDED_CHECKS')
        app=r['functioning_restored_application'];require(app.get('verified') is True and app.get('separate_copy') is True and app.get('recovered_migration_or_seed') is False,'RECORDED_CHECKS')
        statuses(app['api_statuses'],{'ready_status':200,'known_record_listing_status':200,'authorized_new_write_status':201,'auditor_write_status':403,'cross_workspace_history_status':404,'anonymous_or_revoked_identity_status':401})
    elif name=='interrupted-copy-retry':
        require(len(r['cases'])==3 and {c['fault'] for c in r['cases']}=={'copy','fsync','verification'},'RECORDED_CHECKS')
        for case in r['cases']:
            p=case['proof'];require(case.get('passed') is True and all(p.get(k) is True for k in ('injected_failure_rejected','partial_directory_retained_during_failure','same_path_retry_refused','partial_bytes_preserved_on_retry','fresh_directory_copy_succeeded','fresh_copy_opened_in_isolation')) and p.get('copy_primitive_claims_application_restore') is False,'RECORDED_CHECKS')
            common_api(case['recovered_api'])
    elif name=='schema-markers':
        require(len(r['cases'])==3 and {c['fixture_schema_marker'] for c in r['cases']}=={schema-1,schema,schema+1},'RECORDED_CHECKS')
        for case in r['cases']:
            require(case.get('passed') is True and case.get('recovered_migration_or_seed') is False and
                case.get('isolated_file_copy_created') is True and case.get('copy_primitive_claims_application_restore') is False,'RECORDED_CHECKS')
            required_truths(case['file_validity'],'authenticated','checksums_valid','sqlite_integrity_valid')
            app=case['application'];current=case['fixture_schema_marker']==schema
            require(app.get('startup_accepted') is current,'RECORDED_CHECKS')
            if current:statuses(app,{'ready_status':200,'known_record_status':200,'authorized_new_write_status':201,'auditor_write_status':403})
            else:require(app.get('startup_refusal_verified') is True and app.get('diagnostic_ready_status')==503 and app.get('logical_copy_unchanged_after_refusal') is True,'RECORDED_CHECKS')
    elif name=='snapshot-isolation':
        require(r['revision_observations']=={'at_backup':1,'later_source':2,'initial_restore':1,'independent_restored_edit':2} and r['business_receipt_counts']=={'at_backup':1,'later_source':2,'restore':1},'RECORDED_CHECKS')
        common_api(r['restored_api'])
    elif name=='historical-upgrade':
        require(r.get('historical_schema')==10 and r.get('restored_schema')==schema and r.get('dependency_declarations_match') is True,'RECORDED_CHECKS')
        historical_api(r['restored_api'])
    elif name=='upgrade-rollback':
        p=r['rollback_proof'];require(p.get('completed_rebuilds_before_fault')==2,'RECORDED_CHECKS')
        required_truths(p,'failure_after_real_populated_table_rebuild','all_logical_rows_rolled_back',
            'all_table_index_trigger_definitions_rolled_back','schema_marker_remained_10','migration_scratch_tables_absent',
            'foreign_keys_reenabled','sqlite_integrity_valid','declared_foreign_keys_valid',
            'app_startup_refused_after_failed_upgrade','retry_upgraded_only_the_restored_copy')
        historical_api(r['post_retry_api'])
    elif name=='abrupt-process-exit':
        p=r['crash_proof'];c=p['crash_point']
        require(p.get('process_exit_code')==73 and c.get('stage')=='after_populated_table_rebuild' and c.get('completed_rebuilds')==2,'RECORDED_CHECKS')
        required_truths(c,'uncommitted_wal_growth_observed','migration_commit_not_reached')
        required_truths(p['fresh_process_reopen'],'fresh_process_records_preserved','fresh_process_schema_and_indexes_preserved',
            'schema_remained_10','integrity_valid','foreign_keys_valid_and_enabled','migration_scratch_tables_absent')
        required_truths(p,'parent_reopen_records_and_schema_preserved','app_startup_stayed_blocked_at_schema10','explicit_retry_upgraded_restored_copy')
        historical_api(r['post_retry_api'])
    elif name=='committed-wal':
        require(r['main_file_only_negative_controls']=={'physical_integrity_valid':True,'control_marker_count':0,'business_receipt_count':0} and r['restored_counts']=={'control_marker_count':1,'business_receipt_count':1},'RECORDED_CHECKS')
        common_api(r['restored_api'])
    elif name=='declared-relationships':
        require(len(r['negative_cases'])==3 and {case.get('case') for case in r['negative_cases']}=={
            'orphan-control','orphan-business','malformed-control-reference'},'RECORDED_CHECKS')
        for c in r['negative_cases']:
            require(c.get('passed') is True and all(c.get(k) is True for k in ('encryption_authenticated','manifest_checksums_and_sizes_valid','sqlite_physical_integrity_valid','invalid_declared_relationship_verified','native_inspection_rejected','native_copy_rejected_before_destination_creation','input_bytes_preserved')),'RECORDED_CHECKS')
        require(r['valid_backup_positive_control'].get('passed') is True,'RECORDED_CHECKS')
        common_api(r['valid_backup_positive_control']['restored_api'])


def _verify(path,expected_sha256=None,expected_revision=None):
    path=Path(path);require(path.is_file() and path.stat().st_size<=MAX_TOTAL,'ARCHIVE_SIZE')
    with path.open('rb') as stream:archive_bytes=stream.read(MAX_TOTAL+1)
    require(len(archive_bytes)<=MAX_TOTAL,'ARCHIVE_SIZE')
    if expected_sha256 is not None:
        require(re.fullmatch('[a-f0-9]{64}',expected_sha256 or '') and sha(archive_bytes)==expected_sha256,'EXPECTED_HASH')
    data={};folded=set();total=0
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        entries=archive.infolist();require(0<len(entries)<=MAX_FILES,'ARCHIVE_SIZE')
        for entry in entries:
            name=safe_name(entry.filename)
            require(entry.orig_filename==name and not entry.is_dir() and not stat.S_ISLNK(entry.external_attr>>16),'ZIP_PATH')
            require(name.casefold() not in folded,'ZIP_DUPLICATE');folded.add(name.casefold())
            require(not (entry.flag_bits&1) and entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'ZIP_FORMAT')
            total+=entry.file_size;require(0<=entry.file_size<=MAX_FILE and total<=MAX_TOTAL,'ARCHIVE_SIZE')
            with archive.open(entry) as stream:body=stream.read(MAX_FILE+1)
            require(len(body)==entry.file_size and len(body)<=MAX_FILE,'ARCHIVE_SIZE');data[name]=body
    require('evidence-index.json' in data and 'evidence-index.sha256' in data,'MANIFEST_FILES')
    index=json_object(data['evidence-index.json'])
    require(data['evidence-index.sha256'].decode('ascii').split()==[sha(data['evidence-index.json']),'evidence-index.json'],'INDEX_HASH')
    require(index.get('format')=='nexus-disposable-recovery-evidence-pack' and index.get('format_version')==2 and index.get('passed') is True,'PACK_SCHEMA')
    require(all(index.get(k) is False for k in FLAGS) and index.get('fixtures_cleaned') is True and
        index.get('blockers')==[] and index.get('stage_counts_overlap') is True,'PACK_SCHEMA')
    revision=index.get('revision');schema=index.get('schema_version')
    require(isinstance(revision,str) and re.fullmatch('[a-f0-9]{40}',revision) and type(schema) is int and schema>0,'PACK_SCHEMA')
    if expected_revision is not None:require(revision==expected_revision,'EXPECTED_REVISION')
    hashes=index['artifacts_sha256'];require(isinstance(hashes,dict) and hashes,'PACK_SCHEMA')
    require(set(data)==set(hashes)|{'evidence-index.json','evidence-index.sha256'},'MANIFEST_FILES')
    for name,value in hashes.items():
        safe_name(name);require(isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) and sha(data[name])==value,'ARTIFACT_HASH')
    def ref(prefix,relative):
        # Early receipt formats used native Windows separators. Normalize
        # references only; ZIP entry names themselves must stay canonical.
        require(isinstance(relative,str),'ZIP_PATH');relative=relative.replace('\\','/')
        safe_name(relative);name=(prefix+'/' if prefix else '')+relative
        require(name in data,'MANIFEST_FILES');return data[name]
    stages=index['stages'];require(isinstance(stages,list) and len(stages)==9 and {s.get('stage') for s in stages}==set(STAGES),'STAGE_SET')
    skipped=[]
    for stage in stages:
        name=stage['stage'];script,receipt_name=STAGES[name];receipt_path=name+'/'+receipt_name
        require(stage.get('passed') is True and stage.get('receipt')==receipt_path and stage.get('receipt_sha256')==sha(data[receipt_path]),'RECEIPT_HASH')
        r=json_object(data[receipt_path]);require(r.get('passed') is True and r.get('revision')==revision and r.get('blockers')==[] and all(r.get(k) is False for k in FLAGS),'STAGE_SCHEMA')
        if name=='interrupted-copy-retry':
            # This earlier receipt records cleanup per scenario, not at root.
            require(isinstance(r.get('cases'),list) and r['cases'] and
                all(case.get('fixtures_cleaned') is True for case in r['cases']) and
                ('fixtures_cleaned' not in r or r['fixtures_cleaned'] is True),'STAGE_SCHEMA')
        else:require(r.get('fixtures_cleaned',r.get('fixture_files_cleaned')) is True,'STAGE_SCHEMA')
        require(r.get('source_status') in ('unchanged_clean','both_checkouts_unchanged_clean') and r.get('schema_version',r.get('restored_schema'))==schema,'STAGE_SCHEMA')
        if 'historical_revision' in r:require(r['historical_revision']==index['historical_revision'],'STAGE_SCHEMA')
        reproduction=r['reproduction'];script_path='reproduce/scripts/'+script
        if 'script_sha256' in reproduction:require(sha(data[script_path])==reproduction['script_sha256'],'SCRIPT_HASH')
        else:
            parent=script_path.rsplit('/',1)[0]
            for relative,value in reproduction['scripts_sha256'].items():require(sha(ref(parent,relative))==value,'SCRIPT_HASH')
        xmls=[]
        for relative,value in r['artifacts_sha256'].items():
            body=ref(name,relative);require(sha(body)==value,'RECEIPT_ARTIFACT_HASH')
            if relative.endswith('.xml'):xmls.append(body)
            elif relative.endswith('.json'):
                nested=json_object(body)
                if nested.get('format')=='nexus-synthetic-recovery-drill':
                    require(nested.get('passed') is True and nested.get('synthetic_api_exercised') is True,'RECORDED_CHECKS');checks(nested['steps'])
        totals=r['regression_tests'];require(totals==stage.get('regression_tests') and all(type(totals.get(k)) is int and totals[k]>=0 for k in ('tests','failures','errors','skipped')) and totals['tests']>0 and totals['failures']==totals['errors']==0,'TEST_RESULTS')
        require(len(xmls)==1,'TEST_RESULTS')
        text=xmls[0].decode('utf-8');require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(),'XML_FORMAT')
        root=ET.fromstring(text);suites=list(root.findall('testsuite'));require(len(suites)==1,'TEST_RESULTS')
        suite=suites[0];require({k:int(suite.get(k,'-1')) for k in totals}==totals,'TEST_RESULTS')
        cases=list(suite.findall('testcase'));require(len(cases)==totals['tests'] and not any(c.find('failure') is not None or c.find('error') is not None for c in cases),'TEST_RESULTS')
        own_skips=[{'stage':name,'test':c.get('name'),'reason':c.find('skipped').get('message','')} for c in cases if c.find('skipped') is not None]
        require(len(own_skips)==totals['skipped'],'TEST_RESULTS');skipped.extend(own_skips)
        stage_semantics(name,r,schema)
    require(sorted(skipped,key=str)==sorted(index.get('skipped_checks',[]),key=str),'TEST_RESULTS')
    return {'verification':'consistent','byte_integrity_valid':True,'recorded_results_consistent':True,
        'stages_verified':9,'schema_version':schema,'revision':revision,'skipped_checks_count':len(skipped),
        'expected_hash_matched':True if expected_sha256 else None,'expected_revision_matched':True if expected_revision else None,
        'authenticated_signature':False,'bundle_scripts_executed':False,'application_or_database_opened':False,
        'boundary':'Offline consistency checks only. SHA-256/CRC and recorded API results do not authenticate the producer, prove execution or establish live-server state or production readiness.'}


def verify(path,expected_sha256=None,expected_revision=None):
    try:return _verify(path,expected_sha256,expected_revision)
    except EvidenceError:raise
    except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError,UnicodeError,
            zipfile.BadZipFile,RuntimeError,ET.ParseError,zlib.error):
        raise EvidenceError('UNREADABLE_OR_INVALID_EVIDENCE') from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-revision')
    a=parser.parse_args()
    try:result=verify(a.archive,a.expected_sha256,a.expected_revision)
    except EvidenceError as error:result={'verification':'invalid','error_code':str(error),'authenticated_signature':False}
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,zipfile.BadZipFile,RuntimeError,ET.ParseError):
        result={'verification':'invalid','error_code':'UNREADABLE_OR_INVALID_EVIDENCE','authenticated_signature':False}
    print(json.dumps(result));return 0 if result['verification']=='consistent' else 1


if __name__=='__main__':raise SystemExit(main())
