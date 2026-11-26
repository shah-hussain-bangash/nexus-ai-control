"""Development-only Business v1 reference gateway; no ERP or financial effects.

Not registered in the control-plane app and never starts a listener on import.
Every workspace and credential must be supplied explicitly by its developer.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Path as ApiPath, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator
from .business_connector import CONTRACT
from .http_controls import RequestControls
from .schemas import PurchaseArguments, Strict

APPLICATION_ID = int.from_bytes(b'NBS1', 'big')
STORE_VERSION = 1
MAX_OPERATIONS = 1000
SUPPLIERS = frozenset(('SUP-DEMO-104', 'SUP-DEMO-105'))
SUPPLIER_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
OPERATION_PATTERN = r'^[A-Za-z0-9-]{1,64}$'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def reject(status, code):
    raise HTTPException(status, {'code':code})


@dataclass(frozen=True)
class ReferenceCredential:
    token: str = field(repr=False)
    tenant_id: str
    organization_id: str


class ReferencePurchaseArguments(PurchaseArguments):
    @field_validator('amount')
    @classmethod
    def positive(cls, value):
        # Echo the exact wire argument; do not silently normalize a new body
        # into an existing operation's idempotency fingerprint.
        if Decimal(value) <= 0:
            raise ValueError('Amount must be positive')
        return value


class PurchaseEnvelope(Strict):
    operation_id: str = Field(pattern=OPERATION_PATTERN)
    tenant_id: str = Field(min_length=2, max_length=64)
    organization_id: str = Field(min_length=1, max_length=64)
    arguments: ReferencePurchaseArguments


class ReferenceBusinessStore:
    """An explicitly owned SQLite workspace, separate from NEXUS control data."""
    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def create(cls, directory):
        root = Path(directory).resolve()
        root.mkdir(exist_ok=False)
        store = cls(root/'synthetic-business.sqlite3')
        with closing(sqlite3.connect(store.path)) as db:
            db.executescript('''
                PRAGMA foreign_keys=ON;
                CREATE TABLE operations (
                    tenant TEXT NOT NULL, organization TEXT NOT NULL,
                    operation TEXT NOT NULL, kind TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, result TEXT NOT NULL,
                    PRIMARY KEY(tenant, organization, operation)
                );
                CREATE TABLE synthetic_purchases (
                    tenant TEXT NOT NULL, organization TEXT NOT NULL,
                    operation TEXT NOT NULL, external_ref TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    PRIMARY KEY(tenant, organization, operation),
                    FOREIGN KEY(tenant, organization, operation)
                        REFERENCES operations(tenant, organization, operation)
                );
            ''')
            db.execute('PRAGMA application_id='+str(APPLICATION_ID))
            db.execute('PRAGMA user_version='+str(STORE_VERSION))
            db.commit()
        return store

    @classmethod
    def open(cls, directory):
        path = Path(directory).resolve()/'synthetic-business.sqlite3'
        # mode=rw never creates a missing database. Only inspect reference
        # metadata before accepting an explicitly reopened developer workspace.
        try:
            with closing(sqlite3.connect(path.as_uri()+'?mode=rw', uri=True)) as db:
                valid = (db.execute('PRAGMA application_id').fetchone()[0]==APPLICATION_ID and
                         db.execute('PRAGMA user_version').fetchone()[0]==STORE_VERSION)
        except sqlite3.Error:
            raise ValueError('Not a supported reference business workspace.') from None
        if not valid:
            raise ValueError('Not a supported reference business workspace.')
        return cls(path)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=5)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def lookup(self, tenant, organization, operation):
        with self.connect() as db:
            row = db.execute('SELECT result FROM operations WHERE tenant=? AND organization=? AND operation=?',
                             (tenant, organization, operation)).fetchone()
        return json.loads(row[0]) if row else None

    def admit(self, tenant, organization, operation, kind, arguments):
        fingerprint = hashlib.sha256(canonical({'kind':kind, 'arguments':arguments}).encode()).hexdigest()
        with self.connect() as db:
            # The key check, effect and receipt share one serialized transaction.
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT fingerprint,result FROM operations WHERE tenant=? AND organization=? AND operation=?',
                             (tenant, organization, operation)).fetchone()
            if row:
                if not hmac.compare_digest(row[0], fingerprint):
                    reject(409, 'IDEMPOTENCY_CONFLICT')
                return json.loads(row[1]), False
            if arguments['supplier_id'] not in SUPPLIERS:
                reject(404, 'SYNTHETIC_SUPPLIER_NOT_FOUND')
            if db.execute('SELECT count(*) FROM operations').fetchone()[0]>=MAX_OPERATIONS:
                reject(429, 'REFERENCE_CAPACITY')
            ref = hashlib.sha256(canonical([tenant, organization, operation]).encode()).hexdigest()[:24]
            result = {'operation_id':operation, 'organization_id':organization, 'tenant_id':tenant,
                'result':{**arguments, 'state':'created' if kind=='purchase:create' else 'found',
                          'external_ref':('SYN-PR-' if kind=='purchase:create' else 'SYN-SUP-')+ref}}
            db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?)',
                       (tenant, organization, operation, kind, fingerprint, canonical(result)))
            if kind=='purchase:create':
                db.execute('INSERT INTO synthetic_purchases VALUES (?,?,?,?,?)',
                    (tenant, organization, operation, result['result']['external_ref'], canonical(arguments)))
        return result, True


def create_reference_gateway(store, credentials):
    """Build an unmounted synthetic ASGI app with credential-bound scopes."""
    credentials = tuple(credentials)
    if not 1<=len(credentials)<=32:
        raise ValueError('Provide one to 32 synthetic credential bindings.')
    bindings = []
    for grant in credentials:
        if (not isinstance(grant, ReferenceCredential) or not isinstance(grant.token, str) or
            not 16<=len(grant.token)<=4096 or any(not 33<=ord(c)<=126 for c in grant.token) or
            not isinstance(grant.tenant_id, str) or not isinstance(grant.organization_id, str) or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,63}', grant.tenant_id) or
            not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}', grant.organization_id)):
            raise ValueError('Invalid synthetic credential binding.')
        token_hash = hashlib.sha256(grant.token.encode()).digest()
        if any(hmac.compare_digest(token_hash, item[0]) for item in bindings):
            raise ValueError('Each synthetic credential must have one unambiguous scope.')
        bindings.append((token_hash, grant.tenant_id, grant.organization_id))
    app = FastAPI(title='Synthetic Business v1 reference gateway', docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestControls, limit=8192)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {'code':'REFERENCE_REQUEST_REJECTED'}
        return JSONResponse({'error':detail}, status_code=exc.status_code,
                            headers={'WWW-Authenticate':'Bearer'} if exc.status_code==401 else None)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Do not echo submitted bodies, header values or validation input.
        return JSONResponse({'error':{'code':'INVALID_REFERENCE_REQUEST'}}, status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def unavailable(request, exc):
        return JSONResponse({'error':{'code':'REFERENCE_STORE_UNAVAILABLE'}}, status_code=503)

    def scope(request: Request):
        names = ('Authorization', 'X-Nexus-Tenant', 'X-Nexus-Organization', 'X-Nexus-Contract', 'Idempotency-Key')
        if any(len(request.headers.getlist(name))!=1 for name in names):
            reject(401, 'REFERENCE_AUTH_REQUIRED')
        authorization = request.headers['Authorization']
        if not authorization.startswith('Bearer ') or len(authorization)>4103:
            reject(401, 'REFERENCE_AUTH_REQUIRED')
        supplied = hashlib.sha256(authorization[7:].encode()).digest()
        match = None
        for token_hash, tenant, organization in bindings:
            if hmac.compare_digest(supplied, token_hash):
                match = (tenant, organization)
        if match is None:
            reject(401, 'REFERENCE_AUTH_REQUIRED')
        tenant, organization = match
        if (request.headers['X-Nexus-Tenant'], request.headers['X-Nexus-Organization'])!=match:
            reject(403, 'REFERENCE_SCOPE_FORBIDDEN')
        if request.headers['X-Nexus-Contract']!=CONTRACT:
            reject(400, 'REFERENCE_CONTRACT_REQUIRED')
        operation = request.headers['Idempotency-Key']
        if not re.fullmatch(OPERATION_PATTERN, operation):
            reject(422, 'REFERENCE_OPERATION_REQUIRED')
        return tenant, organization, operation

    @app.get('/api/v1/suppliers/{supplier_id}')
    def supplier(supplier_id: str = ApiPath(pattern=SUPPLIER_PATTERN), binding=Depends(scope)):
        payload, _ = store.admit(*binding, 'supplier:read', {'supplier_id':supplier_id})
        return payload

    @app.post('/api/v1/purchase-requests')
    def purchase(body: PurchaseEnvelope, binding=Depends(scope)):
        tenant, organization, operation = binding
        if (body.tenant_id, body.organization_id, body.operation_id)!=(tenant, organization, operation):
            reject(403, 'REFERENCE_BODY_SCOPE_MISMATCH')
        payload, created = store.admit(*binding, 'purchase:create', body.arguments.model_dump())
        return JSONResponse(payload, status_code=201 if created else 200)

    @app.get('/api/v1/operations/{operation_id}')
    def operation(operation_id: str = ApiPath(pattern=OPERATION_PATTERN), binding=Depends(scope)):
        tenant, organization, supplied_id = binding
        if operation_id!=supplied_id:
            reject(409, 'REFERENCE_OPERATION_MISMATCH')
        payload = store.lookup(tenant, organization, operation_id)
        if payload is None:
            reject(404, 'REFERENCE_OPERATION_NOT_FOUND')
        return payload

    return app
