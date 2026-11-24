"""Safety/orchestration tests; mocked orchestration is not restore evidence."""
import importlib.util
import json
from pathlib import Path
import sys
import zipfile
import pytest

REPO=Path(__file__).resolve().parents[2]
SCRIPT=REPO/'scripts/run_docker_recovery_drill.py'
spec=importlib.util.spec_from_file_location('docker_drill_entry',SCRIPT)
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
from docker_recovery import safety,fixture


@pytest.mark.parametrize('endpoint',['unix:///var/run/docker.sock','unix:///run/user/1000/docker.sock',
    'npipe:////./pipe/dockerDesktopLinuxEngine','npipe:////./pipe/docker_engine'])
def test_local_docker_socket_endpoints(endpoint):assert safety.local_endpoint(endpoint)


@pytest.mark.parametrize('endpoint',['tcp://127.0.0.1:2375','tcp://example.invalid:2376','ssh://host',
    'unix://host/path','unix:relative','npipe:////remote/pipe/docker_engine',None])
def test_remote_and_ambiguous_docker_endpoints_refused(endpoint):assert not safety.local_endpoint(endpoint)


def test_container_user_matches_nonroot_unix_fixture_owner():
    assert safety.container_user(uid=1001,gid=1002)=='1001:1002'


@pytest.mark.parametrize('uid,gid',[(0,0),(-1,1001),(True,1001),(1001,-1)])
def test_root_or_invalid_fixture_user_refused(uid,gid):
    with pytest.raises(safety.DrillError,match='NONROOT_UNIX_HOST_USER_REQUIRED'):safety.container_user(uid=uid,gid=gid)


def test_environment_does_not_inherit_operator_runtime_or_remote_host(monkeypatch):
    monkeypatch.setenv('NEXUS_SECRET','private-fixture-canary');monkeypatch.setenv('DOCKER_HOST','tcp://remote.invalid:2375')
    monkeypatch.setenv('HTTP_PROXY','http://proxy.invalid')
    result=safety.client_environment()
    assert all(name not in result for name in ('NEXUS_SECRET','DOCKER_HOST','HTTP_PROXY'))


def test_workspace_cleanup_requires_matching_marker_and_preserves_neighbors(tmp_path):
    owned=tmp_path/'.docker-recovery-owned';owned.mkdir();neighbor=tmp_path/'existing';neighbor.mkdir()
    (neighbor/'canary').write_text('preserve')
    (owned/'owned-workspace.json').write_text(json.dumps({'format':'nexus-owned-docker-recovery','nonce':'ours'}))
    with pytest.raises(safety.DrillError,match='WORKSPACE_CLEANUP_REFUSED'):safety.cleanup_workspace(owned,tmp_path,'theirs')
    assert owned.exists() and (neighbor/'canary').read_text()=='preserve'
    assert safety.cleanup_workspace(owned,tmp_path,'ours')
    assert (neighbor/'canary').read_text()=='preserve'


def test_workspace_cleanup_rejects_parent_itself(tmp_path):
    with pytest.raises(safety.DrillError,match='WORKSPACE_CLEANUP_REFUSED'):safety.cleanup_workspace(tmp_path,tmp_path,'ours')


def test_image_cleanup_refuses_wrong_owner_without_remove():
    calls=[]
    class Client:
        def run(self,*args):calls.append(args);return 'image'
        def value(self,*args):return {'io.nexus.recovery.run':'other'}
    with pytest.raises(safety.DrillError,match='IMAGE_CLEANUP_OWNERSHIP_MISMATCH'):
        safety.remove_owned_image(Client(),'nexus-disposable-recovery:ours','ours')
    assert not any(args[:2]==('image','rm') for args in calls)


@pytest.mark.parametrize('name',['../escape','/absolute','C:drive','alias\\file'])
def test_source_export_rejects_unsafe_members(tmp_path,monkeypatch,name):
    def fake_git(repo,*args):
        with zipfile.ZipFile(tmp_path/'source.zip','x') as archive:
            stored=name.replace('\\','/');archive.writestr(stored,b'fixture')
        if stored!=name:
            path=tmp_path/'source.zip';path.write_bytes(path.read_bytes().replace(stored.encode(),name.encode()))
        return ''
    monkeypatch.setattr(safety,'git',fake_git)
    with pytest.raises(safety.DrillError,match='UNSAFE_SOURCE_ARCHIVE'):safety.export_source(tmp_path,'a'*40,tmp_path)
    assert not (tmp_path/'source').exists()


def test_source_gate_refuses_dirty_checkout_before_archive(tmp_path,monkeypatch):
    monkeypatch.setattr(safety,'git',lambda *args:' M tracked.py')
    with pytest.raises(safety.DrillError,match='CLEAN_CHECKOUT_REQUIRED'):safety.source_metadata(tmp_path)


def test_check_mode_never_contacts_engine_or_creates_fixture(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(entry,'source_metadata',lambda repo:{'revision':'a'*40,'tree':'b'*40})
    monkeypatch.setattr(entry.shutil,'which',lambda name:'docker')
    monkeypatch.setattr(entry,'Docker',lambda *args:pytest.fail('daemon was contacted'))
    assert entry.main(['--check','--output-dir',str(tmp_path/'absent')])==0
    result=json.loads(capsys.readouterr().out)
    assert not result['docker_engine_contacted'] and not result['application_container_start_attempted']
    assert not (tmp_path/'absent').exists()


@pytest.mark.parametrize('outcome',['success','uncertain_build','runtime_cleanup_failure','runtime_unknown'])
def test_orchestration_preserves_uncertain_runtime_mounts_and_redacts_password(tmp_path,monkeypatch,capsys,outcome):
    monkeypatch.setattr(entry,'source_metadata',lambda repo:{'revision':'a'*40,'tree':'b'*40})
    monkeypatch.setattr(entry.shutil,'which',lambda name:'docker')
    monkeypatch.setattr(entry,'git',lambda repo,*args:'a'*40 if args[0]=='rev-parse' else '')
    password='private-fixture-password-canary-123456'
    monkeypatch.setattr(entry.secrets,'token_urlsafe',lambda size:password)
    class Client:
        def __init__(self,work):self.work=work;self.nonce=None
        def run(self,*args,**kwargs):
            if args[0]=='build':
                self.nonce=next(value.split('=',1)[1] for value in args if value.startswith('io.nexus.recovery.run='))
                if outcome=='uncertain_build':raise safety.DrillError('DOCKER_TOOL_UNAVAILABLE_OR_TIMEOUT')
                (self.work/'image-id.txt').write_text('sha256:'+'1'*64)
            return ''
        def value(self,*args):
            if args[-1].startswith('nexus-disposable-recovery:'):
                return 'sha256:'+'1'*64 if '.Id' in args[-2] else {'org.opencontainers.image.revision':'a'*40,'io.nexus.recovery.run':self.nonce}
            raise AssertionError('unexpected image query')
    monkeypatch.setattr(entry,'Docker',Client)
    def export(repo,revision,work):
        context=work/'source';context.mkdir();(context/'Dockerfile').write_text('FROM fixture')
        archive=work/'source.zip';archive.write_bytes(b'synthetic')
        return archive,context
    monkeypatch.setattr(entry,'export_source',export)
    def prepare(repo,destination,secret,revision):
        assert secret==password;destination.mkdir()
        return {'schema_version':11,'checks_passed':24,'fixture_files_retained_for_container_review':True}
    monkeypatch.setattr(entry.fixture,'prepare',prepare)
    def exercise(*args):
        assert args[3]==password
        if outcome=='runtime_unknown':raise RuntimeError(password)
        return {'passed':outcome=='success','cleanup_passed':outcome=='success','checks_passed':53}
    monkeypatch.setattr(entry.runtime,'exercise',exercise)
    removed=[];monkeypatch.setattr(entry,'remove_owned_image',lambda *args:removed.append(True) or True)
    code=entry.main(['--run','--output-dir',str(tmp_path)])
    result=json.loads(next(tmp_path.glob('synthetic-docker-recovery-*.json')).read_text())
    assert password not in json.dumps(result) and password not in capsys.readouterr().out
    if outcome=='success':
        assert code==0 and result['temporary_workspace_cleaned'] and removed
        assert not list(tmp_path.glob('.docker-recovery-*'))
    else:
        assert code==1 and not result['temporary_workspace_cleaned'] and not removed
        assert Path(result['retained_workspace']).is_dir()


def test_real_disposable_fixture_preparation_without_env_or_docker(tmp_path):
    result=fixture.prepare(REPO,tmp_path/'new-fixture','synthetic-only-password-123456','a'*40)
    assert result['passed'] and result['checks_passed']==24 and result['file_validity']['authenticated']
    assert result['probe_api_statuses']=={'ready':200,'known_record_read':200,'auditor_write':403}
    assert result['password_or_key_written_in_plaintext'] is False
    assert (tmp_path/'new-fixture/recovered/control.sqlite3').is_file()


def test_gateway_preserves_http_and_never_uses_client_selected_destination():
    import http.client
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    from docker_recovery.gateway import make_server,BACKEND
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']))
            requests.append((self.path,self.headers.get('X-Fixture'),body))
            self.send_response(201);self.send_header('Content-Length',str(len(body)))
            self.send_header('Set-Cookie','fixture=synthetic; HttpOnly');self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    backend=ThreadingHTTPServer(('127.0.0.1',0),Handler);backend.daemon_threads=True
    gateway=make_server(('127.0.0.1',0),backend.server_address)
    threads=[threading.Thread(target=server.serve_forever,daemon=True) for server in (backend,gateway)]
    for thread in threads:thread.start()
    client=http.client.HTTPConnection(*gateway.server_address,timeout=5)
    try:
        client.request('POST','/known',body=b'synthetic',headers={'X-Fixture':'context'})
        response=client.getresponse()
        assert response.status==201 and response.read()==b'synthetic' and response.getheader('Set-Cookie')=='fixture=synthetic; HttpOnly'
        client.request('POST','http://not-contacted.invalid/path',body=b'fixed')
        response=client.getresponse();assert response.status==201 and response.read()==b'fixed'
        assert requests==[('/known','context',b'synthetic'),('http://not-contacted.invalid/path',None,b'fixed')]
        assert BACKEND==('recovered-api',8000)
    finally:
        client.close()
        for server in (gateway,backend):server.shutdown();server.server_close()
        for thread in threads:thread.join(timeout=5)
    assert not any(thread.is_alive() for thread in threads)
