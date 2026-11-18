"""Cryptographic OIDC negative cases; no real user credentials or provider calls."""
import json
from urllib.parse import parse_qs, urlsplit
import jwt
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from nexus import oidc
from nexus.db import OIDCTransaction, User, SchemaVersion, migrate, now


@pytest.fixture
def provider(ctx, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())); public.update(kid='test-rsa', use='sig', alg='RS256')
    ctx['settings'].oidc_issuer = 'http://127.0.0.1:9009/realm'
    metadata = {'issuer': ctx['settings'].oidc_issuer, 'authorization_endpoint': 'http://127.0.0.1:9009/auth',
                'token_endpoint': 'http://127.0.0.1:9009/token', 'jwks_uri': 'http://127.0.0.1:9009/keys',
                'code_challenge_methods_supported': ['S256']}
    state = {'claims': {}, 'metadata': metadata, 'public': public, 'key': key, 'nonce': None}
    def get(url, **kwargs):
        data = metadata if url.endswith('openid-configuration') else {'keys': [state['public']]}
        return httpx.Response(200, json=data, request=httpx.Request('GET', url))
    def post(url, **kwargs):
        claims = {'iss': ctx['settings'].oidc_issuer, 'aud': 'nexus-console', 'sub': 'owner-idp-subject',
                  'iat': int(now()), 'exp': int(now()) + 120, 'nonce': state['nonce'],
                  'email': 'owner@nexus.local', 'email_verified': True, **state['claims']}
        token = jwt.encode(claims, state['key'], algorithm='RS256', headers={'kid': 'test-rsa'})
        return httpx.Response(200, json={'id_token': token}, request=httpx.Request('POST', url))
    monkeypatch.setattr(oidc.httpx, 'get', get); monkeypatch.setattr(oidc.httpx, 'post', post)
    return state


def begin(ctx, provider):
    response = ctx['client'].get('/auth/oidc/start', follow_redirects=False)
    assert response.status_code == 307
    query = parse_qs(urlsplit(response.headers['location']).query)
    provider['nonce'] = query['nonce'][0]
    return query


def finish(ctx, query):
    return ctx['client'].get('/auth/oidc/callback', params={'state': query['state'][0], 'code': 'synthetic-code'}, follow_redirects=False)


def test_oidc_server_side_pkce_and_success(ctx, provider):
    q = begin(ctx, provider)
    assert q['code_challenge_method'] == ['S256']
    binding = ctx['client'].cookies.get('nexus_oidc')
    assert binding and len(binding.split('.')) == 1  # No signed JWT containing a plaintext verifier.
    with ctx['db']() as db:
        transaction = db.scalar(select(OIDCTransaction))
        verifier = oidc.decrypt_verifier(transaction.verifier_ciphertext, ctx['settings'].secret)
        assert verifier not in transaction.verifier_ciphertext and verifier not in binding
    assert finish(ctx, q).status_code == 307
    assert ctx['client'].get('/v1/me').json()['user']['role'] == 'owner'


@pytest.mark.parametrize('claims', [
    {'aud': 'wrong-client'}, {'iss': 'https://wrong-issuer.invalid'}, {'nonce': 'wrong-nonce'},
    {'exp': 1}, {'email_verified': False}, {'azp': 'wrong-authorized-party'},
    {'aud': ['nexus-console', 'another-client']}, {'email': 'unknown@nexus.local'},
])
def test_oidc_invalid_claims_never_create_session(ctx, provider, claims):
    provider['claims'] = claims
    q = begin(ctx, provider)
    response = finish(ctx, q)
    assert response.status_code in (401, 403)
    assert ctx['client'].get('/v1/me').status_code == 401


def test_oidc_signature_from_untrusted_key_denied(ctx, provider):
    provider['key'] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert finish(ctx, begin(ctx, provider)).status_code == 401


def test_oidc_transaction_is_single_use(ctx, provider):
    q = begin(ctx, provider)
    original_binding = ctx['client'].cookies.get('nexus_oidc')
    assert finish(ctx, q).status_code == 307
    ctx['client'].cookies.set('nexus_oidc', original_binding, path='/auth')
    assert finish(ctx, q).status_code == 401


def test_oidc_bad_browser_binding_and_expiry(ctx, provider):
    q = begin(ctx, provider)
    ctx['client'].cookies.clear(); ctx['client'].cookies.set('nexus_oidc', 'wrong-binding', path='/auth')
    assert finish(ctx, q).status_code == 401
    q = begin(ctx, provider)
    with ctx['db'].begin() as db:
        for row in db.scalars(select(OIDCTransaction)): row.expires = now() - 1
    assert finish(ctx, q).status_code == 401


def test_oidc_prebound_subject_cannot_change(ctx, provider):
    with ctx['db'].begin() as db:
        db.scalar(select(User).where(User.email == 'owner@nexus.local')).oidc_subject = 'http://127.0.0.1:9009/realm|different-subject'
    assert finish(ctx, begin(ctx, provider)).status_code == 403


def test_oidc_required_context_enforced(ctx, provider):
    ctx['settings'].oidc_required_acr = '2'
    q = begin(ctx, provider); assert q['acr_values'] == ['2']
    assert finish(ctx, q).status_code == 401
    provider['claims']['acr'] = '2'
    assert finish(ctx, begin(ctx, provider)).status_code == 307


@pytest.mark.parametrize('change', [{'issuer': 'https://wrong.invalid'}, {'token_endpoint': 'https://other.invalid/token'}, {'code_challenge_methods_supported': ['plain']}])
def test_oidc_discovery_boundary_enforced(ctx, provider, change):
    provider['metadata'].update(change)
    assert ctx['client'].get('/auth/oidc/start', follow_redirects=False).status_code == 503


def test_schema_upgrade_v1_preserves_existing_accounts(ctx):
    with ctx['app'].state.engine.begin() as conn:
        OIDCTransaction.__table__.drop(conn)
        conn.execute(SchemaVersion.__table__.delete().where(SchemaVersion.version >= 2))
    migrate(ctx['app'].state.engine, ctx['db'])
    with ctx['db']() as db:
        assert db.get(SchemaVersion, 2)
        assert db.scalar(select(User).where(User.email == 'owner@nexus.local'))
    migrate(ctx['app'].state.engine, ctx['db'])
    with ctx['db']() as db: assert len(db.scalars(select(SchemaVersion)).all()) == 8


def test_schema_newer_than_application_is_rejected(ctx):
    with ctx['db'].begin() as db: db.add(SchemaVersion(version=99))
    with pytest.raises(RuntimeError, match='newer'): migrate(ctx['app'].state.engine, ctx['db'])


def test_readiness_rejects_outdated_schema(ctx):
    with ctx['db'].begin() as db:
        db.query(SchemaVersion).filter(SchemaVersion.version == 8).delete()
    response = ctx['client'].get('/health/ready')
    assert response.status_code == 503 and response.json()['error']['code'] == 'SCHEMA_UPGRADE_REQUIRED'


def test_startup_refuses_uninitialized_database(tmp_path):
    from fastapi.testclient import TestClient
    from nexus.app import create_app
    from nexus.config import Settings
    app = create_app(Settings(database_url='sqlite:///' + str(tmp_path/'missing.db'), mock_database=str(tmp_path/'mock.db'),
                             secret='s'*48, agent_secret='a'*48))
    with pytest.raises(RuntimeError, match='Initialize or upgrade'):
        with TestClient(app): pass
