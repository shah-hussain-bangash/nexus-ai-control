import json
from pathlib import Path
import subprocess
import sys
import httpx
import pytest
from nexus import hybrid, retrieval_drill as drill
from nexus.business_connector import HTTPBusiness
from nexus.config import Settings


def test_combined_drill_uses_real_worker_without_operator_config_or_network(tmp_path,monkeypatch):
    private=tmp_path/'operator.db';private.write_bytes(b'private operator sentinel')
    envfile=tmp_path/'.env';envfile.write_text('NEXUS_SECRET=private-config\nNEXUS_MODE=pilot\n')
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_BUSINESS_CONNECTOR','http');monkeypatch.setenv('NEXUS_LIVE_INFERENCE','1')
    def forbidden(*args,**kwargs):pytest.fail('Operator configuration or external transport used')
    monkeypatch.setattr(Settings,'from_env',forbidden)
    monkeypatch.setattr(HTTPBusiness,'request',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    original=hybrid.subprocess.Popen;inputs=[]
    def worker(args,**kwargs):
        assert args[1:3]==['-m','nexus.hybrid_worker']
        assert not any(key.startswith('NEXUS_') for key in kwargs['env'])
        inputs.append((Path(args[-2]),Path(args[-1])))
        return original(args,**kwargs)
    monkeypatch.setattr(hybrid.subprocess,'Popen',worker)
    before=(private.read_bytes(),envfile.read_bytes())
    result=drill.run_drill(tmp_path/'disposable',include_hybrid=True)
    assert result['passed'] and len(result['steps'])==36 and all(row['passed'] for row in result['steps'])
    assert len(inputs)==5 and all(not source.exists() and not output.exists() for source,output in inputs)
    assert result['format']=='nexus-synthetic-knowledge-drill' and result['boundary']==drill.KNOWLEDGE_BOUNDARY
    assert not result['production_ready'] and not result['customer_acceptance']
    assert (private.read_bytes(),envfile.read_bytes())==before


def test_broken_ranker_cannot_pass_combined_exercise(tmp_path,monkeypatch):
    monkeypatch.setattr(hybrid,'compute',lambda payload:{'scores':[],'rank':2,'vocabulary':9})
    result=drill.run_drill(tmp_path/'disposable',include_hybrid=True)
    assert not result['passed'] and result['failure']=='hybrid_real_cooccurrence_retrieval'
    assert result['steps'][-1]=={'id':'hybrid_real_cooccurrence_retrieval','passed':False}


def test_history_that_leaks_a_stale_hit_cannot_pass_combined_exercise(tmp_path,monkeypatch):
    original=hybrid.visible_run
    def leaking(db,row,user):
        value=original(db,row,user)
        if value['withheld_stale_or_inaccessible'] and row.result.get('hits'):
            value['items'].append(row.result['hits'][0])
        return value
    monkeypatch.setattr(hybrid,'visible_run',leaking)
    result=drill.run_drill(tmp_path/'disposable',include_hybrid=True)
    assert not result['passed'] and result['failure']=='hybrid_history_withholds_revoked_source'


def test_combined_report_is_unique_private_and_cleans_databases(tmp_path,capsys):
    output=tmp_path/'reports'
    for _ in range(2):
        assert drill.main(['--include-hybrid','--output-dir',str(output)])==0
        summary=json.loads(capsys.readouterr().out)
        assert summary['passed'] and summary['steps_passed']==36 and summary['boundary']==drill.KNOWLEDGE_BOUNDARY
        path=Path(summary['report']);assert path.name.startswith('synthetic-knowledge-')
        result=json.loads(path.read_text(encoding='utf-8'))
        assert result['format']=='nexus-synthetic-knowledge-drill'
        assert all(set(row)=={'id','passed'} for row in result['steps'])
        assert not any(value in json.dumps(result) for value in ['@drill.invalid','hybrid-private-query-marker',
            'car vehicle engine road','content_base64','password','cookie'])
    assert len(list(output.iterdir()))==2 and not list(output.rglob('*.db'))
    assert not list(output.glob('.retrieval-*'))


def test_combined_failure_preserves_scope_and_hides_private_error(tmp_path,capsys,monkeypatch):
    def broken(*args):raise RuntimeError('private-ranking-error')
    monkeypatch.setattr('nexus.hybrid_drill.exercise',broken)
    output=tmp_path/'reports'
    assert drill.main(['--include-hybrid','--output-dir',str(output)])==1
    captured=capsys.readouterr();assert 'private-ranking-error' not in captured.out+captured.err
    summary=json.loads(captured.out);assert not summary['passed'] and summary['boundary']==drill.KNOWLEDGE_BOUNDARY
    report=Path(summary['report']).read_text(encoding='utf-8')
    assert 'private-ranking-error' not in report and json.loads(report)['failure']=='isolated_drill_could_not_finish'
    assert not list(output.rglob('*.db'))


def test_portable_combined_entry_from_unrelated_directory(tmp_path):
    (tmp_path/'.env').write_text('NEXUS_MODE=pilot\nNEXUS_DATABASE_URL=invalid\n')
    script=Path(__file__).resolve().parents[2]/'scripts/run_synthetic_retrieval_drill.py'
    response=subprocess.run([sys.executable,str(script),'--include-hybrid','--output-dir',str(tmp_path/'saved reports')],
        cwd=tmp_path,capture_output=True,text=True)
    assert response.returncode==0,response.stderr
    summary=json.loads(response.stdout);assert summary['passed'] and summary['steps_passed']==36 and not response.stderr
    assert list((tmp_path/'saved reports').iterdir())==[Path(summary['report'])]
