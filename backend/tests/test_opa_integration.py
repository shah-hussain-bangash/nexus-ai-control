"""Optional real OPA integration. Set OPA_BIN to a trusted local OPA executable."""
import os
import socket
import subprocess
import time
from pathlib import Path
import httpx
import pytest
from conftest import submit


@pytest.fixture
def live_opa():
    executable=os.environ.get('OPA_BIN')
    if not executable: pytest.skip('Set OPA_BIN to run the real OPA HTTP integration.')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    policies=Path(__file__).resolve().parents[2]/'policies'
    process=subprocess.Popen([executable,'run','--server','--addr',f'127.0.0.1:{port}',str(policies)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                if httpx.get(base+'/health',timeout=.2).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.05)
        else:raise RuntimeError('OPA did not become ready')
        yield base+'/v1/data/nexus/decision'
    finally:
        process.terminate();process.wait(timeout=10)


@pytest.mark.parametrize('amount,decision',[('5000.00','allow'),('12500.00','require_approval'),('30000.00','deny')])
def test_real_opa_governs_http_action(ctx,live_opa,amount,decision):
    ctx['settings'].policy_mode='opa';ctx['settings'].opa_url=live_opa
    response=submit(ctx,amount=amount)
    assert response.status_code==202 and response.json()['decision']==decision
    assert ctx['connector'].count()==0
