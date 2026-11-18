"""Bounded request buffering and credential-free structured request events."""
import json
import logging
import time
import uuid
from starlette.responses import JSONResponse

log = logging.getLogger('nexus.http')
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(handler)
log.setLevel(logging.INFO)
log.propagate = False


class RequestControls:
    def __init__(self, app, limit=65536):
        self.app = app; self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        started = time.perf_counter(); status = 500
        limit=1572864 if scope.get('method')=='POST' and scope.get('path')=='/v1/ingestion-jobs' else self.limit
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect': return
            part = message.get('body', b'')
            if len(body) + len(part) > limit:
                response = JSONResponse({'error': {'code':'PAYLOAD_TOO_LARGE','message':f'Maximum request size is {limit} bytes.'}},413,headers={'X-Request-ID':request_id})
                return await response(scope, receive, send)
            body.extend(part)
            if not message.get('more_body', False): break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        async def traced_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                message['headers'] = list(message.get('headers', [])) + [(b'x-request-id',request_id.encode())]
            await send(message)
        try:
            await self.app(scope, bounded_receive, traced_send)
        finally:
            route = getattr(scope.get('route'), 'path', 'unmatched')
            log.info(json.dumps({'event':'http.request','request_id':request_id,'method':scope.get('method'),'route':route,'status':status,'duration_ms':round((time.perf_counter()-started)*1000,3)},separators=(',',':')))
