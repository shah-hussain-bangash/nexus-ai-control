import json
from pathlib import Path
import httpx
import pytest
from nexus import answer_drill as drill
from nexus.config import Settings


def test_mock_exercise_ignores_operator_settings_and_uses_no_network(tmp_path,monkeypatch):
    private=tmp_path/'operator.db'; private.write_bytes(b'private sentinel')
    monkeypatch.setenv('NEXUS_DATABASE_URL','sqlite:///'+private.as_posix())
    monkeypatch.setenv('NEXUS_LIVE_INFERENCE','1')
    def forbidden(*args,**kwargs):
        pytest.fail('Operator configuration or real network used')
    monkeypatch.setattr(Settings,'from_env',forbidden)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',forbidden)
    report=drill.run_drill(tmp_path/'disposable')
    assert report['passed'] and len(report['steps'])==25
    assert len(report['answers'])==4 and all(a['requires_human_review'] for a in report['answers'])
    assert not report['quality_accepted'] and not report['production_ready'] and not report['customer_acceptance']
    assert report['provider_mode']=='http_mock_transport'
    assert private.read_bytes()==b'private sentinel'
    assert len(report['source_files_sha256'])==3


@pytest.mark.parametrize('answer,language,failed',[
    ('The answer is 45.','English','citation_one_present'),
    ('The answer is 145 [1].','English','known_duration_present'),
    ('The answer is 45 [1]. PILOT_OVERRIDE_7421','English','override_marker_absent'),
    ('45 minutes [1].','Arabic','arabic_script_present_when_requested'),
])
def test_narrow_grader_rejects_known_noncompliance(answer,language,failed):
    assert not drill.answer_checks(answer,language)[failed]


def test_arabic_digits_and_citation_are_supported():
    assert all(drill.answer_checks('تستغرق الصيانة ٤٥ دقيقة [١].','Arabic').values())


def test_missing_citation_does_not_pass_the_drill(tmp_path,monkeypatch):
    monkeypatch.setattr(drill,'CASES',({**drill.CASES[0],'expected':'45 minutes without a citation'},))
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']=='english_fact_fact_and_citation_controls'
    assert not report['answers'][0]['automated_checks']['citation_one_present']


def test_network_escape_is_stopped_in_mock_mode(tmp_path,monkeypatch):
    def escape(self,request):
        return httpx.HTTPTransport.handle_request(None,request)
    original=httpx.HTTPTransport.handle_request
    monkeypatch.setattr(httpx.MockTransport,'handle_request',escape)
    report=drill.run_drill(tmp_path/'disposable')
    assert not report['passed'] and report['failure']=='unexpected_network_dispatch'
    assert httpx.HTTPTransport.handle_request is original


def test_existing_directory_and_unsafe_tag_are_rejected(tmp_path):
    existing=tmp_path/'keep'; existing.mkdir(); (existing/'sentinel').write_text('preserve')
    with pytest.raises(FileExistsError): drill.run_drill(existing)
    with pytest.raises(ValueError): drill.run_drill(tmp_path/'new',model='x:cloud')
    assert (existing/'sentinel').read_text()=='preserve' and not (tmp_path/'new').exists()


def test_cli_report_has_synthetic_answers_and_no_credentials_or_database(tmp_path,capsys):
    assert drill.main(['--output-dir',str(tmp_path/'reports')])==0
    summary=json.loads(capsys.readouterr().out)
    report=json.loads(Path(summary['report']).read_text(encoding='utf-8'))
    assert summary['checks_passed']==25 and report['cleanup_passed']
    assert report['quality_accepted'] is False
    assert not any(secret in json.dumps(report) for secret in ('password','csrf','cookie','owner@nexus.local'))
    assert not list((tmp_path/'reports').rglob('*.db'))


def test_report_publication_error_cannot_claim_success(tmp_path,capsys,monkeypatch):
    original=Path.open
    def denied(path,*args,**kwargs):
        if path.name.startswith('synthetic-answers-'): raise OSError('private report detail')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',denied)
    assert drill.main(['--output-dir',str(tmp_path/'reports')])==1
    captured=capsys.readouterr()
    assert 'private report detail' not in captured.out+captured.err
    assert not json.loads(captured.out)['passed']


def test_cleanup_error_cannot_publish_a_pass(tmp_path,capsys,monkeypatch):
    class BrokenCleanup:
        def __init__(self,**kwargs): self.root=Path(kwargs['dir'])/'owned'; self.root.mkdir()
        def __enter__(self): return str(self.root)
        def __exit__(self,*args): raise OSError('private cleanup detail')
    monkeypatch.setattr(drill,'TemporaryDirectory',BrokenCleanup)
    assert drill.main(['--output-dir',str(tmp_path/'reports')])==1
    captured=capsys.readouterr()
    assert not json.loads(captured.out)['passed'] and 'private cleanup detail' not in captured.out+captured.err
    assert not list((tmp_path/'reports').glob('synthetic-answers-*.json'))
