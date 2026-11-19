"""OIDC protocol boundary: server-side single-use state and encrypted PKCE verifier.
The selected issuer is operator-configured. Discovery cannot silently redirect secrets to a different origin.
"""
import base64
import hashlib
import secrets
import ssl
from urllib.parse import urlencode, urlsplit
import httpx
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, update
from .db import OIDCTransaction, User, now
from .security import digest, fail, issue_session
from .service import audit
from .runtime_context import CURRENT_ENVIRONMENT


def origin(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid provider URL')
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == 'https' else 80)


def tls_verify(settings):
    return ssl.create_default_context(cafile=settings.oidc_ca_bundle) if settings.oidc_ca_bundle else True


def discover(settings):
    try:
        issuer = settings.oidc_issuer.rstrip('/')
        response = httpx.get(issuer + '/.well-known/openid-configuration', timeout=5, follow_redirects=False, verify=tls_verify(settings))
        response.raise_for_status(); metadata = response.json()
        if metadata['issuer'] != issuer: raise ValueError('Issuer mismatch')
        for field in ['authorization_endpoint', 'token_endpoint', 'jwks_uri']:
            if origin(metadata[field]) != origin(issuer): raise ValueError('Cross-origin metadata endpoint')
        if 'S256' not in metadata.get('code_challenge_methods_supported', []): raise ValueError('PKCE unavailable')
        return metadata
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        fail(503, 'OIDC_UNAVAILABLE', 'Identity provider configuration is unavailable or invalid.')


def encrypt_verifier(verifier, secret):
    key = hashlib.sha256(('nexus:oidc:verifier:' + secret).encode()).digest()
    iv = secrets.token_bytes(12)
    return base64.urlsafe_b64encode(iv + AESGCM(key).encrypt(iv, verifier.encode(), b'nexus-oidc-v2')).decode()


def decrypt_verifier(value, secret):
    key = hashlib.sha256(('nexus:oidc:verifier:' + secret).encode()).digest()
    raw = base64.urlsafe_b64decode(value)
    return AESGCM(key).decrypt(raw[:12], raw[12:], b'nexus-oidc-v2').decode()


def begin(factory, settings):
    if not settings.oidc_issuer: fail(503, 'OIDC_UNCONFIGURED', 'Organization SSO has not been configured.')
    metadata = discover(settings)
    state, binding, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
    with factory.begin() as db:
        # A new browser transaction does not expose the PKCE verifier in a signed client cookie.
        db.add(OIDCTransaction(id=digest(state), binding_hash=digest(binding), nonce=nonce,
              verifier_ciphertext=encrypt_verifier(verifier, settings.secret), expires=now() + 300))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    query = {'client_id': settings.oidc_client_id, 'response_type': 'code', 'scope': 'openid email profile',
             'redirect_uri': settings.origin + '/auth/oidc/callback', 'state': state, 'nonce': nonce,
             'code_challenge': challenge, 'code_challenge_method': 'S256'}
    if settings.oidc_required_acr: query['acr_values'] = settings.oidc_required_acr
    return metadata['authorization_endpoint'] + '?' + urlencode(query), binding


def consume(factory, state, binding):
    if not state or not binding: fail(401, 'OIDC_FAILED', 'SSO verification failed. Start sign-in again.')
    with factory.begin() as db:
        row = db.get(OIDCTransaction, digest(state))
        if not row or not secrets.compare_digest(row.binding_hash, digest(binding)):
            fail(401, 'OIDC_FAILED', 'SSO verification failed. Start sign-in again.')
        changed = db.execute(update(OIDCTransaction).where(OIDCTransaction.id == row.id,
             OIDCTransaction.used_at == 0, OIDCTransaction.expires > now()).values(used_at=now()))
        if changed.rowcount != 1: fail(401, 'OIDC_FAILED', 'SSO transaction expired or was already consumed.')
        return row


def finish(factory, settings, state, binding, code):
    row = consume(factory, state, binding)
    if not code: fail(401, 'OIDC_FAILED', 'Identity provider did not return an authorization code.')
    try:
        metadata = discover(settings)
        payload = {'grant_type': 'authorization_code', 'code': code,
                   'redirect_uri': settings.origin + '/auth/oidc/callback',
                   'client_id': settings.oidc_client_id,
                   'code_verifier': decrypt_verifier(row.verifier_ciphertext, settings.secret)}
        if settings.oidc_client_secret: payload['client_secret'] = settings.oidc_client_secret
        token_response = httpx.post(metadata['token_endpoint'], data=payload, timeout=5, follow_redirects=False, verify=tls_verify(settings))
        token_response.raise_for_status(); id_token = token_response.json()['id_token']
        # Fetch JWKS with the same bounded/trusted HTTP path; no unverified JWT claims drive endpoints.
        jwks_response = httpx.get(metadata['jwks_uri'], timeout=5, follow_redirects=False, verify=tls_verify(settings))
        jwks_response.raise_for_status(); jwks = jwt.PyJWKSet.from_dict(jwks_response.json())
        header = jwt.get_unverified_header(id_token)
        if header.get('alg') != 'RS256' or not header.get('kid'): raise ValueError('Unsupported signing key')
        candidates = [k for k in jwks.keys if k.key_id == header['kid'] and k.key_type == 'RSA']
        if len(candidates) != 1: raise ValueError('Ambiguous signing key')
        claims = jwt.decode(id_token, candidates[0].key, algorithms=['RS256'],
             audience=settings.oidc_client_id, issuer=settings.oidc_issuer.rstrip('/'),
             options={'require': ['exp', 'iat', 'sub', 'nonce', 'aud', 'iss']})
        if not isinstance(claims['sub'], str) or not claims['sub']: raise ValueError('Missing subject')
        if not secrets.compare_digest(str(claims['nonce']), row.nonce): raise ValueError('Nonce mismatch')
        if claims.get('email_verified') is not True: raise ValueError('Email not verified')
        audiences = claims['aud'] if isinstance(claims['aud'], list) else [claims['aud']]
        if len(audiences) > 1 and claims.get('azp') != settings.oidc_client_id: raise ValueError('Authorized party mismatch')
        if claims.get('azp') not in (None, settings.oidc_client_id): raise ValueError('Authorized party mismatch')
        if settings.oidc_required_acr and claims.get('acr') != settings.oidc_required_acr:
            raise ValueError('Required authentication context missing')
    except Exception:
        fail(401, 'OIDC_FAILED', 'SSO verification failed. Start sign-in again.')
    with factory.begin() as db:
        user = db.scalar(select(User).where(User.email == str(claims.get('email', '')).lower(), User.active == 1).with_for_update())
        subject = settings.oidc_issuer.rstrip('/') + '|' + claims['sub']
        if not user or (user.oidc_subject and user.oidc_subject != subject):
            fail(403, 'NO_MEMBERSHIP', 'Ask your administrator for workspace access.')
        user.oidc_subject = subject
        token, _ = issue_session(db, user, settings)
        audit(db, user.org_id, user.id, 'session.oidc_created', detail={'acr': str(claims.get('acr', 'unspecified'))},env=CURRENT_ENVIRONMENT)
        return token
