import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from nexus import synthetic_suite as suite
from nexus.config import Settings


def child_result(argv,**kwargs):
    output=Path(argv[-1]);entry=Path(argv[1]).stem.removeprefix('run_synthetic_').removesuffix('_drill')
    kind='knowledge' if '--include-hybrid' in argv else entry
    report={'format':'nexus-synthetic-'+kind+'-drill','format_version':1,'release':suite.__version__,
        'schema_version':suite.CURRENT_SCHEMA,'passed':True,'steps':[{'id':'one','passed':True},{'id':'two','passed':True}],
        'private':'private child output sentinel'}
    path=output/'child.json';path.write_text(json.dumps(report),encoding='utf-8')
    return SimpleNamespace(returncode=0,stdout=json.dumps({'passed':True,'steps_passed':2,'report':str(path),
        'private':'private child output sentinel'}),stderr='private child output sentinel')


def test_fixed_children_use_separate_directories_and_ignore_operator_configuration(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'preserve operator data')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_DATABASE_URL=invalid\n')
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY','private operator key sentinel')
    def forbidden(*args,**kwargs):pytest.fail('Operator settings were loaded')
    monkeypatch.setattr(Settings,'from_env',forbidden)
    calls=[]
    def launch(argv,**kwargs):calls.append((argv,kwargs));return child_result(argv,**kwargs)
    monkeypatch.setattr(suite.subprocess,'run',launch)
    result=suite.run_suite(tmp_path/'suite')
    assert result['passed'] and result['drills_total']==result['drills_passed']==len(calls)==8 and result['checks_passed']==16
    assert len({kw['cwd'] for _,kw in calls})==8
    for argv,kw in calls:
        assert argv[0]==sys.executable and Path(argv[1]).is_absolute() and Path(argv[1]).is_file()
        assert kw=={'cwd':Path(argv[-1]),'capture_output':True,'text':True,'encoding':'utf-8','timeout':60}
        assert argv[-2]=='--output-dir' and Path(argv[-1]).parent==tmp_path/'suite'
    assert sum('--include-hybrid' in argv for argv,_ in calls)==1
    assert private.read_bytes()==b'preserve operator data' and envfile.read_text()=='NEXUS_DATABASE_URL=invalid\n'
    assert os.environ['NEXUS_BACKUP_ENCRYPTION_KEY']=='private operator key sentinel'
    assert 'private child output sentinel' not in json.dumps(result)


@pytest.mark.parametrize('failure,status',[
    ('exit','drill_failed'),('timeout','timed_out'),('launch','could_not_run'),('encoding','could_not_run'),
])
def test_child_failure_cannot_pass_and_other_drills_continue(tmp_path,monkeypatch,failure,status):
    monkeypatch.setattr(suite,'DRILLS',suite.DRILLS[:2]);calls=[]
    def launch(argv,**kwargs):
        calls.append(argv)
        if len(calls)>1:return child_result(argv,**kwargs)
        if failure=='exit':return SimpleNamespace(returncode=1,stdout='private child failure',stderr='private child failure')
        if failure=='timeout':raise subprocess.TimeoutExpired(argv,60,output=b'private child failure',stderr=b'private child failure')
        if failure=='encoding':raise UnicodeDecodeError('utf-8',b'\xff',0,1,'private child failure')
        raise OSError('private child failure')
    monkeypatch.setattr(suite.subprocess,'run',launch)
    result=suite.run_suite(tmp_path/'suite')
    assert not result['passed'] and len(calls)==2 and result['drills_passed']==1 and result['checks_passed']==2
    assert result['drills'][0]=={'id':'connector','passed':False,'checks_passed':0,'status':status}
    assert result['drills'][1]['passed'] and 'private child failure' not in json.dumps(result)


@pytest.mark.parametrize('fault',[
    'stdout','boolean_count','zero_count','missing_report','outside_report','oversized_report',
    'wrong_format','boolean_version','wrong_release','boolean_schema','false_success','count_mismatch','failed_step','duplicate_step',
])
def test_inconsistent_or_unsafe_child_report_cannot_pass(tmp_path,monkeypatch,fault):
    monkeypatch.setattr(suite,'DRILLS',suite.DRILLS[:1])
    outside=tmp_path/'operator-private.json';outside.write_text('private report sentinel')
    original_read=Path.read_text
    def guarded(path,*args,**kwargs):
        if path==outside:pytest.fail('Report outside the child directory was read')
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',guarded)
    def launch(argv,**kwargs):
        completed=child_result(argv,**kwargs);summary=json.loads(completed.stdout);path=Path(summary['report'])
        report=json.loads(path.read_text())
        if fault=='stdout':completed.stdout='private malformed output';return completed
        if fault=='boolean_count':summary['steps_passed']=True
        elif fault=='zero_count':summary['steps_passed']=0
        elif fault=='missing_report':path.unlink()
        elif fault=='outside_report':summary['report']=str(outside)
        elif fault=='oversized_report':path.write_text('x'*262145)
        elif fault=='wrong_format':report['format']='wrong-drill'
        elif fault=='boolean_version':report['format_version']=True
        elif fault=='wrong_release':report['release']='unknown-release'
        elif fault=='boolean_schema':report['schema_version']=True
        elif fault=='false_success':report['passed']=False
        elif fault=='count_mismatch':report['steps'].pop()
        elif fault=='failed_step':report['steps'][1]['passed']=False
        elif fault=='duplicate_step':report['steps'][1]['id']='one'
        if fault not in ('missing_report','oversized_report'):path.write_text(json.dumps(report))
        completed.stdout=json.dumps(summary);return completed
    monkeypatch.setattr(suite.subprocess,'run',launch)
    result=suite.run_suite(tmp_path/'suite')
    assert not result['passed'] and result['checks_passed']==0 and result['drills'][0]['status']=='invalid_report'
    assert 'private' not in json.dumps(result)


def test_existing_workspace_and_empty_registry_cannot_report_success(tmp_path,monkeypatch):
    root=tmp_path/'existing';root.mkdir();sentinel=root/'keep';sentinel.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):suite.run_suite(root)
    assert sentinel.read_bytes()==b'preserve'
    monkeypatch.setattr(suite,'DRILLS',())
    assert not suite.run_suite(tmp_path/'empty')['passed']


def test_cli_unique_safe_aggregate_reports_after_child_cleanup(tmp_path,capsys,monkeypatch):
    monkeypatch.setattr(suite.subprocess,'run',child_result);output=tmp_path/'reports'
    for _ in range(2):
        assert suite.main(['--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out);assert summary['passed'] and summary['drills_passed']==8
        report=json.loads(Path(summary['report']).read_text())
        assert set(report)=={'format','format_version','release','schema_version','created_at_utc','passed','drills_total',
            'drills_passed','checks_passed','per_drill_timeout_seconds','drills','source','active_database_restored','customer_acceptance','production_ready','boundary'}
        assert report['format_version']==2 and report['source']['status']=='unchanged'
        assert report['source']['before']==report['source']['after'] and report['source']['before']['files']>0
        assert all(set(row)=={'id','passed','checks_passed','status'} for row in report['drills'])
        assert not any(report[key] for key in ('active_database_restored','customer_acceptance','production_ready'))
        assert 'private child output sentinel' not in json.dumps(report)
    assert len(list(output.iterdir()))==2 and all(path.name.startswith('synthetic-suite-') for path in output.iterdir())


@pytest.mark.parametrize('failure',['cleanup','write'])
def test_cleanup_or_report_write_failure_cannot_claim_success(tmp_path,capsys,monkeypatch,failure):
    monkeypatch.setattr(suite.subprocess,'run',child_result)
    if failure=='cleanup':
        class BrokenCleanup:
            def __init__(self,**kw):self.root=Path(kw['dir'])/'scratch';self.root.mkdir()
            def __enter__(self):return str(self.root)
            def __exit__(self,*args):raise OSError('private failure sentinel')
        monkeypatch.setattr(suite,'TemporaryDirectory',BrokenCleanup)
    else:
        original=Path.open
        def denied(path,*args,**kwargs):
            if path.name.startswith('synthetic-suite-'):raise OSError('private failure sentinel')
            return original(path,*args,**kwargs)
        monkeypatch.setattr(Path,'open',denied)
    output=tmp_path/'reports';assert suite.main(['--output-dir',str(output)])==1
    captured=capsys.readouterr();assert not json.loads(captured.out)['passed'] and 'private failure sentinel' not in captured.out+captured.err
    assert not list(output.glob('synthetic-suite-*.json'))


def test_portable_full_suite_from_unrelated_directory_preserves_operator_files(tmp_path,monkeypatch):
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_DATABASE_URL=invalid\nNEXUS_MODE=pilot\n')
    private=tmp_path/'operator.db';private.write_bytes(b'private operator database')
    monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BACKUP_ENCRYPTION_KEY','invalid private operator key')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_suite.py'
    response=subprocess.run([sys.executable,str(script),'--output-dir',str(tmp_path/'reports')],cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['drills_passed']==8 and summary['checks_passed']==218 and not response.stderr
    assert list((tmp_path/'reports').iterdir())==[Path(summary['report'])]
    assert private.read_bytes()==b'private operator database' and envfile.read_text()=='NEXUS_DATABASE_URL=invalid\nNEXUS_MODE=pilot\n'


def source_project(root):
    modules=root/'backend/nexus';modules.mkdir(parents=True)
    (modules/'__init__.py').write_bytes(b'fixture version\n')
    (modules/'synthetic_suite.py').write_bytes(b'fixture suite\n')
    scripts=root/'scripts';scripts.mkdir()
    for entry in {entry for _,entry,_ in suite.DRILLS}:
        (scripts/('run_synthetic_'+entry+'_drill.py')).write_bytes(b'fixture entry\n')
    (scripts/'run_synthetic_suite.py').write_bytes(b'fixture parent\n')
    return root


def test_source_fingerprint_is_portable_and_excludes_private_data_and_caches(tmp_path):
    first=source_project(tmp_path/'first');second=source_project(tmp_path/'second')
    original=suite.source_fingerprint(first)
    assert original==suite.source_fingerprint(second) and len(original['sha256'])==64
    (first/'.env').write_bytes(b'private operator key sentinel')
    data=first/'backend/data';data.mkdir();(data/'operator.db').write_bytes(b'private operator data')
    cache=first/'backend/nexus/__pycache__';cache.mkdir();(cache/'ignored.py').write_bytes(b'ignored cached fixture')
    (first/'README.md').write_text('Unrelated documentation')
    assert suite.source_fingerprint(first)==original


@pytest.mark.parametrize('change',['edit','add','remove','entry'])
def test_source_edits_additions_removals_and_entry_changes_change_fingerprint(tmp_path,change):
    project=source_project(tmp_path/'project');extra=project/'backend/nexus/nested';extra.mkdir()
    module=extra/'fixture.py';module.write_bytes(b'original fixture')
    original=suite.source_fingerprint(project)
    if change=='edit':module.write_bytes(b'changed fixture')
    elif change=='add':(extra/'added.py').write_bytes(b'new fixture')
    elif change=='remove':module.unlink()
    else:(project/'scripts/run_synthetic_suite.py').write_bytes(b'changed entry')
    assert suite.source_fingerprint(project)!=original


@pytest.mark.parametrize('failure',['missing_entry','too_large','too_many','unreadable'])
def test_unavailable_or_oversized_source_inventory_fails_closed(tmp_path,monkeypatch,failure):
    project=source_project(tmp_path/'project')
    if failure=='missing_entry':(project/'scripts/run_synthetic_suite.py').unlink()
    elif failure=='too_large':monkeypatch.setattr(suite,'MAX_SOURCE_BYTES',1)
    elif failure=='too_many':monkeypatch.setattr(suite,'MAX_SOURCE_FILES',1)
    else:
        original=Path.open
        def denied(path,*args,**kwargs):
            if path==project/'backend/nexus/__init__.py':raise PermissionError('private source error')
            return original(path,*args,**kwargs)
        monkeypatch.setattr(Path,'open',denied)
    with pytest.raises((OSError,ValueError)):suite.source_fingerprint(project)


def test_source_link_is_rejected_before_reading_its_target(tmp_path,monkeypatch):
    project=source_project(tmp_path/'project');outside=tmp_path/'private.py';outside.write_bytes(b'private source sentinel')
    link=project/'backend/nexus/linked.py'
    try:link.symlink_to(outside)
    except OSError:pytest.skip('Creating symlinks requires Windows privileges on this host.')
    original=Path.open
    def guarded(path,*args,**kwargs):
        if path in (outside,link):pytest.fail('Redirected source contents were read')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded)
    with pytest.raises(ValueError):suite.source_fingerprint(project)


@pytest.mark.parametrize('failure',['changed','before_unavailable','after_unavailable'])
def test_all_drills_passing_cannot_hide_changed_or_unavailable_source(tmp_path,monkeypatch,failure):
    fingerprint={'sha256':'a'*64,'files':10};calls=[]
    def probe():
        calls.append(True)
        if failure=='before_unavailable' or failure=='after_unavailable' and len(calls)>1:raise OSError('private source error')
        return {**fingerprint,'sha256':'b'*64} if failure=='changed' and len(calls)>1 else fingerprint
    monkeypatch.setattr(suite,'source_fingerprint',probe);launched=[]
    def launch(argv,**kwargs):launched.append(argv);return child_result(argv,**kwargs)
    monkeypatch.setattr(suite.subprocess,'run',launch)
    result=suite.run_suite(tmp_path/'suite')
    assert not result['passed'] and result['source']['status']==('changed' if failure=='changed' else 'unavailable')
    assert 'private source error' not in json.dumps(result)
    if failure=='before_unavailable':
        assert not launched and result['checks_passed']==0 and all(row['status']=='not_run' for row in result['drills'])
    else:assert len(launched)==result['drills_passed']==8 and result['checks_passed']==16
