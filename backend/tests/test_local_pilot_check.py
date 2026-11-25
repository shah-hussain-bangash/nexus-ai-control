import importlib.util
from pathlib import Path
import httpx
import pytest

spec=importlib.util.spec_from_file_location('local_pilot_check',Path(__file__).resolve().parents[2]/'scripts/check_local_pilot.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)


def test_wildcard_missing_and_foreign_bindings_cannot_pass():
    rows=[{'LocalPort':62346,'LocalAddress':'127.0.0.1'},{'LocalPort':11434,'LocalAddress':'127.0.0.1'}]
    assert check.loopback_only(rows,(62346,11434))
    for address in ('0.0.0.0','::','192.168.1.2'):
        assert not check.loopback_only([*rows,{'LocalPort':11434,'LocalAddress':address}],(62346,11434))
    assert not check.loopback_only(rows[:1],(62346,11434))


def test_socket_table_filters_local_ports_and_recognizes_ipv6_wildcards():
    text='''
TCP 127.0.0.1:62346 0.0.0.0:0 LISTENING 12
TCP [::]:11434 [::]:0 LISTENING 13
TCP 127.0.0.1:9999 127.0.0.1:11434 ESTABLISHED 14
'''
    rows=check.listener_rows(text,(62346,11434))
    assert rows==[{'LocalAddress':'127.0.0.1','LocalPort':62346},{'LocalAddress':'::','LocalPort':11434}]
    assert not check.loopback_only(rows,(62346,11434))


def test_http_checks_use_no_credentials_and_cannot_accept_redirects_or_exposed_runtime():
    def mock(request):
        assert request.url.host=='127.0.0.1' and not request.headers.get('cookie')
        if request.url.path=='/health/ready':return httpx.Response(200,json={'status':'ready','mode':'local','schema_version':11})
        if request.url.path=='/v1/runtime':return httpx.Response(200,json={})
        if request.url.path=='/metrics':return httpx.Response(302,headers={'location':'https://elsewhere.invalid'})
        return httpx.Response(200,json={})
    with httpx.Client(transport=httpx.MockTransport(mock),follow_redirects=False) as client:
        result=check.check_http(client,62346)
    assert [r['passed'] for r in result]==[True,True,False,False]


def test_unavailable_or_nonlocal_ready_service_fails_closed():
    def mock(request):
        if request.url.path=='/health/ready':return httpx.Response(200,json={'status':'ready','mode':'pilot'})
        raise httpx.ConnectError('private failure',request=request)
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        result=check.check_http(client,62346)
    assert not any(r['passed'] for r in result)
    assert 'private failure' not in str(result)


@pytest.mark.parametrize('body',[[],None,{'status':'ready','mode':'local'},
    {'status':'ready','mode':'local','schema_version':True}])
def test_malformed_readiness_cannot_pass(body):
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=body))) as client:
        results=check.check_http(client,62346)
    assert not results[1]['passed']
