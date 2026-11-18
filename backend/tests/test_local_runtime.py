import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import httpx
import pytest
from nexus.local import bind_listener
from conftest import identifiers


def build_stub(ctx):
    frontend = Path(ctx['settings'].frontend_dir)
    frontend.mkdir(exist_ok=True)
    (frontend / 'index.html').write_text('<html>synthetic portal</html>')
    return frontend


@pytest.mark.parametrize('name,mime', [('nexus-agent-neon.png', 'image/png'), ('nexus-governance.svg', 'image/svg+xml')])
def test_root_illustrations_are_files_not_spa_html(ctx, name, mime):
    frontend = build_stub(ctx)
    payload = b'synthetic-public-asset'
    (frontend / name).write_bytes(payload)
    response = ctx['client'].get('/' + name)
    assert response.status_code == 200
    assert response.content == payload and response.headers['content-type'].startswith(mime)
    assert response.headers['x-content-type-options'] == 'nosniff'


def test_missing_asset_is_404_and_extensionless_route_still_loads(ctx):
    build_stub(ctx)
    for path in ['/nexus-agent-neon.png', '/nexus-governance.svg', '/missing.png', '/.env', '/v1/not-an-endpoint']:
        assert ctx['client'].get(path).status_code == 404
    assert ctx['client'].get('/executions').text == '<html>synthetic portal</html>'


def test_port_is_reserved_until_listener_closed():
    listener = bind_listener(0)
    try:
        assert listener.getsockname()[0] == '127.0.0.1'
        with pytest.raises(OSError): bind_listener(listener.getsockname()[1])
    finally:
        listener.close()


def test_occupied_default_port_falls_back_without_stopping_owner():
    occupied = socket.socket()
    try:
        try:
            occupied.bind(('127.0.0.1', 8000))
        except OSError:
            pass  # Another existing service owns 8000; it must also be left alone.
        listener = bind_listener()
        try:
            assert listener.getsockname()[1] != 8000
        finally:
            listener.close()
    finally:
        occupied.close()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process shutdown assertion; Windows wrapper needs native smoke testing')
def test_local_launcher_runs_api_worker_and_verified_action(ctx, tmp_path):
    if not ctx['settings'].database_url.startswith('sqlite'):
        pytest.skip('Local launcher smoke uses the disposable SQLite fixture')
    frontend = build_stub(ctx)
    settings = ctx['settings']
    listener = bind_listener(0)
    port = listener.getsockname()[1]
    listener.close()
    origin = f'http://127.0.0.1:{port}'
    env = os.environ.copy()
    for name in settings.__dataclass_fields__:
        env['NEXUS_' + name.upper()] = str(getattr(settings, name))
    env['NEXUS_FRONTEND_DIR'] = str(frontend.resolve())
    env['NEXUS_ORIGIN'] = 'http://127.0.0.1:1'  # Launcher must replace a stale terminal value.
    log = tmp_path / 'local-launch.log'
    backend = Path(__file__).resolve().parents[1]
    with log.open('w+') as output:
        proc = subprocess.Popen([sys.executable, '-m', 'nexus.local', '--port', str(port)], cwd=backend,
                                env=env, stdout=output, stderr=output)
        try:
            with httpx.Client(base_url=origin, trust_env=False, timeout=2) as client:
                deadline = time.monotonic() + 20
                while True:
                    assert proc.poll() is None, log.read_text()
                    try:
                        if client.get('/health/ready').status_code == 200: break
                    except httpx.TransportError:
                        pass
                    assert time.monotonic() < deadline, log.read_text()
                    time.sleep(.1)
                login = client.post('/auth/local/login', json={'email': 'owner@nexus.local', 'password': 'Test-Only-Password-123!'}, headers={'Origin': origin})
                assert login.status_code == 200, login.text
                csrf = login.json()['csrf']
                agent, tool = identifiers(ctx, kind='supplier')
                r = client.post('/v1/console/actions', headers={'Origin': origin, 'X-CSRF-Token': csrf, 'Idempotency-Key': 'local-process-smoke-0001'},
                    json={'agent_id': agent, 'tool_id': tool, 'request': {'action': 'supplier:read', 'resource': 'suppliers', 'arguments': {'supplier_id': 'SUP-DEMO-104'}}})
                assert r.status_code == 202, r.text
                action_id = r.json()['id']
                while True:
                    result = client.get('/v1/actions/' + action_id)
                    assert result.status_code == 200, result.text
                    if result.json()['status'] == 'verified': break
                    assert time.monotonic() < deadline, result.text
                    time.sleep(.1)
        finally:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
        assert 'NEXUS execution worker started.' in log.read_text()
        with socket.socket() as probe:
            assert probe.connect_ex(('127.0.0.1', port)) != 0
