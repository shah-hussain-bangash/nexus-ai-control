"""Request-size rejection events must correlate without exposing submitted data."""
import asyncio
import json
import re
from types import SimpleNamespace
import pytest
from nexus.http_controls import RequestControls
from nexus import http_controls


@pytest.fixture
def events(monkeypatch):
    result=[];monkeypatch.setattr(http_controls.log,'info',lambda value:result.append(json.loads(value)))
    return result


def scope(path='/private-fixture-record',method='POST'):
    return {'type':'http','method':method,'path':path,'raw_path':path.encode(),'query_string':b'key=private-query-sentinel',
        'headers':[(b'authorization',b'Bearer private-auth-sentinel'),(b'cookie',b'private-cookie-sentinel'),
            (b'x-request-id',b'private-untrusted-id')],'http_version':'1.1'}


def run(app,request,chunks,*,limit=8,send_failure=False):
    messages=[];pending=[{'type':'http.request','body':body,'more_body':i<len(chunks)-1} for i,body in enumerate(chunks)]
    async def receive():return pending.pop(0) if pending else {'type':'http.disconnect'}
    async def send(message):
        messages.append(message)
        if send_failure:raise OSError('private-send-sentinel')
    asyncio.run(RequestControls(app,limit=limit)(request,receive,send))
    return messages


def check_event(event,status,route='unmatched'):
    assert set(event)=={'event','request_id','method','route','status','duration_ms'}
    assert event['event']=='http.request' and event['status']==status and event['route']==route
    assert re.fullmatch('[a-f0-9]{32}',event['request_id']) and event['duration_ms']>=0
    assert 'private-' not in json.dumps(event)


@pytest.mark.parametrize('chunks',[[b'private-body-sentinel'],[b'1234',b'56789']])
def test_size_rejection_emits_one_private_safe_correlated_event(events,chunks):
    async def forbidden(*args):pytest.fail('Oversized input reached the application')
    messages=run(forbidden,scope(),chunks)
    assert len(events)==1;check_event(events[0],413)
    start=messages[0];headers=dict(start['headers'])
    assert start['status']==413 and headers[b'x-request-id'].decode()==events[0]['request_id']
    body=json.loads(messages[1]['body']);assert body['error']['code']=='PAYLOAD_TOO_LARGE'


def test_rejection_event_is_recorded_even_if_response_send_fails(events):
    async def forbidden(*args):pytest.fail('Oversized input reached the application')
    with pytest.raises(OSError,match='private-send-sentinel'):run(forbidden,scope(),[b'x'*9],send_failure=True)
    assert len(events)==1;check_event(events[0],413)


@pytest.mark.parametrize('length,status,code',[('9',413,'PAYLOAD_TOO_LARGE'),('private-invalid-length',400,'INVALID_LENGTH')])
def test_declared_size_errors_are_logged_without_receiving_body(events,length,status,code):
    messages=[];request=scope();request['headers'].append((b'content-length',length.encode()))
    async def forbidden(*args):pytest.fail('Declared size rejection read a body or dispatched the application')
    async def send(message):messages.append(message)
    asyncio.run(RequestControls(forbidden,limit=8)(request,forbidden,send))
    assert messages[0]['status']==status and json.loads(messages[1]['body'])['error']['code']==code
    assert len(events)==1;check_event(events[0],status)
    assert dict(messages[0]['headers'])[b'x-request-id'].decode()==events[0]['request_id']


@pytest.mark.parametrize('method,allowed',[('POST',True),('PUT',False)])
def test_ingestion_specific_size_allowance_is_unchanged(events,method,allowed):
    calls=[]
    async def app(request,receive,send):
        calls.append((await receive())['body'])
        await send({'type':'http.response.start','status':204,'headers':[]})
        await send({'type':'http.response.body','body':b''})
    messages=run(app,scope('/v1/ingestion-jobs',method),[b'x'*9])
    assert bool(calls)==allowed and messages[0]['status']==(204 if allowed else 413)
    assert len(events)==1;check_event(events[0],messages[0]['status'])


def test_ingestion_over_its_real_limit_is_still_rejected_and_logged(events):
    async def forbidden(*args):pytest.fail('Oversized ingestion reached the application')
    messages=run(forbidden,scope('/v1/ingestion-jobs'),[b'x'*1572864,b'y'])
    assert messages[0]['status']==413 and len(events)==1;check_event(events[0],413)


def test_allowed_boundary_body_is_delivered_once_and_event_uses_route_template(events):
    bodies=[]
    async def app(request,receive,send):
        request['route']=SimpleNamespace(path='/fixture/{record}')
        bodies.append(await receive());bodies.append(await receive())
        await send({'type':'http.response.start','status':201,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    messages=run(app,scope(),[b'1234',b'5678'])
    assert bodies==[{'type':'http.request','body':b'12345678','more_body':False},{'type':'http.disconnect'}]
    assert len(events)==1;check_event(events[0],201,'/fixture/{record}')
    assert dict(messages[0]['headers'])[b'x-request-id'].decode()==events[0]['request_id']


def test_downstream_exception_still_emits_one_private_safe_failure_event(events):
    async def broken(*args):raise RuntimeError('private-application-sentinel')
    with pytest.raises(RuntimeError,match='private-application-sentinel'):run(broken,scope(),[b''])
    assert len(events)==1;check_event(events[0],500)


def test_non_http_scope_is_passed_through_without_http_event(events):
    calls=[]
    async def app(request,receive,send):calls.append(request)
    request={'type':'lifespan'};run(app,request,[])
    assert calls==[request] and not events


@pytest.mark.parametrize('declared',[True,False])
def test_real_api_size_rejection_correlates_without_logging_credentials(ctx,events,declared):
    headers={'Authorization':'Bearer private-auth-sentinel','Cookie':'private-cookie-sentinel','X-Request-ID':'private-untrusted-id'}
    if not declared:headers['Content-Length']='0'
    response=ctx['client'].post('/auth/local/login?key=private-query-sentinel',
        content=b'private-body-sentinel'+b'x'*65536,headers=headers)
    assert response.status_code==413 and response.json()['error']['code']=='PAYLOAD_TOO_LARGE'
    assert len(events)==1;check_event(events[0],413)
    assert response.headers['x-request-id']==events[0]['request_id']
    assert response.headers['x-content-type-options']=='nosniff' and response.headers['cache-control']=='no-store'


def test_real_api_invalid_length_has_one_correlated_safe_event(ctx,events):
    response=ctx['client'].post('/auth/local/login?key=private-query-sentinel',content=b'private-body-sentinel',
        headers={'Content-Length':'private-invalid-length'})
    assert response.status_code==400 and response.json()['error']['code']=='INVALID_LENGTH'
    assert len(events)==1;check_event(events[0],400)
    assert response.headers['x-request-id']==events[0]['request_id']
