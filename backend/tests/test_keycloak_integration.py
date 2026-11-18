"""Real Keycloak development-realm protocol tests, using generated disposable identities only.
Set NEXUS_KEYCLOAK_HOME to a trusted extracted Keycloak distribution to opt in.
No test credentials, OTP seeds, imported realm or service binaries are included in the source release.
"""
import hashlib
import ssl
import datetime
import ipaddress
import hmac
import html
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
import httpx
import pytest
from sqlalchemy import select
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from nexus.db import User


class PrivateProvider:
    def __init__(self, **values): self.values = values
    def __getitem__(self, key): return self.values[key]
    def __repr__(self): return '<Disposable Keycloak provider; credentials redacted>'


class Forms(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.forms=[]; self.current=None; self.feed(source)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='form': self.current={'action':attrs.get('action',''),'id':attrs.get('id',''),'inputs':{}};self.forms.append(self.current)
        if tag=='input' and self.current is not None and attrs.get('name'):
            self.current['inputs'][attrs['name']]=attrs.get('value','')
    def handle_endtag(self, tag):
        if tag=='form':self.current=None
    def containing(self, name):
        return next((f for f in self.forms if name in f['inputs']),None)


def totp(secret):
    # Keycloak default OTP credential representation stores the UTF-8 secret, not Base32.
    counter=struct.pack('>Q',int(time.time())//30)
    raw=hmac.new(secret.encode(),counter,hashlib.sha1).digest();offset=raw[-1]&15
    return str((struct.unpack('>I',raw[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)


def make_certificates(folder):
    """Private test CA + localhost server certificate; TLS verification is never disabled."""
    current=datetime.datetime.now(datetime.timezone.utc)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'NEXUS disposable test CA')])
    ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(current-datetime.timedelta(minutes=1))
        .not_valid_after(current+datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,content_commitment=False,
          data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=False,decipher_only=False),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
        .sign(ca_key,hashes.SHA256()))
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    server=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]))
        .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(current-datetime.timedelta(minutes=1)).not_valid_after(current+datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
        .sign(ca_key,hashes.SHA256()))
    ca_file=folder/'ca.pem';cert=folder/'server.pem';private=folder/'server.key'
    ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert.write_bytes(server.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    os.chmod(private,0o600)
    return ca_file,cert,private


@pytest.fixture(scope='session')
def keycloak(tmp_path_factory):
    configured=os.environ.get('NEXUS_KEYCLOAK_HOME')
    if not configured:pytest.skip('Set NEXUS_KEYCLOAK_HOME to run real Keycloak protocol tests.')
    home=Path(configured).resolve();script=home/'bin/kc.sh'
    if not script.is_file():raise RuntimeError('Keycloak distribution not found')
    folder=tmp_path_factory.mktemp('keycloak-fixture')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    realm_name='nexus-test-'+secrets.token_hex(4)
    issuer=f'https://127.0.0.1:{port}/realms/{realm_name}'
    ca_file,cert_file,key_file=make_certificates(folder)
    password=secrets.token_urlsafe(24);otp_secret=secrets.token_urlsafe(24)
    realm={'realm':realm_name,'enabled':True,'registrationAllowed':False,'sslRequired':'none',
      'loginWithEmailAllowed':True,'otpPolicyType':'totp','otpPolicyAlgorithm':'HmacSHA1','otpPolicyDigits':6,'otpPolicyPeriod':30,
      'clients':[{'clientId':'nexus-console','enabled':True,'publicClient':True,'standardFlowEnabled':True,
       'directAccessGrantsEnabled':False,'redirectUris':['http://localhost:8000/auth/oidc/callback'],
       'webOrigins':['http://localhost:8000'],'defaultClientScopes':['profile','email'],
       'attributes':{'pkce.code.challenge.method':'S256'}}], 'users':[]}
    for email,otp in [('owner@nexus.local',False),('reviewer@nexus.local',True),('unprovisioned@nexus.local',False)]:
        creds=[{'type':'password','value':password,'temporary':False}]
        if otp:creds.append({'type':'otp','userLabel':'Disposable test authenticator',
          'secretData':json.dumps({'value':otp_secret}),
          'credentialData':json.dumps({'subType':'totp','digits':6,'counter':0,'period':30,'algorithm':'HmacSHA1'})})
        realm['users'].append({'username':email,'email':email,'emailVerified':True,'enabled':True,
                              'firstName':'Synthetic','lastName':'Tester','requiredActions':[],'credentials':creds})
    imports=home/'data/import';imports.mkdir(parents=True,exist_ok=True)
    file=imports/(realm_name+'-realm.json');file.write_text(json.dumps(realm));os.chmod(file,0o600)
    log=(folder/'keycloak.log').open('w')
    env=dict(os.environ, JAVA_OPTS_APPEND='-Xms64m -Xmx512m')
    command=[str(script),'start-dev','--db=dev-mem','--http-enabled=false','--http-host=127.0.0.1',f'--https-port={port}',
             f'--https-certificate-file={cert_file}',f'--https-certificate-key-file={key_file}',
             f'--hostname=https://127.0.0.1:{port}','--import-realm','--log-level=warn']
    process=subprocess.Popen(command,cwd=home,env=env,stdout=log,stderr=subprocess.STDOUT)
    try:
        for _ in range(180):
            if process.poll() is not None:raise RuntimeError('Keycloak exited during startup; inspect the private fixture log.')
            try:
                if httpx.get(issuer+'/.well-known/openid-configuration',timeout=.5,verify=ssl.create_default_context(cafile=str(ca_file))).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.5)
        else:raise RuntimeError('Keycloak did not become ready within the fixture deadline.')
        yield PrivateProvider(issuer=issuer,password=password,otp_secret=otp_secret,ca_file=str(ca_file))
    finally:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        log.close();file.unlink(missing_ok=True)


def begin_login(ctx, provider, email):
    ctx['settings'].oidc_issuer=provider['issuer']
    ctx['settings'].oidc_ca_bundle=provider['ca_file']
    response=ctx['client'].get('/auth/oidc/start',follow_redirects=False)
    assert response.status_code==307
    browser=httpx.Client(follow_redirects=False,timeout=10,verify=ssl.create_default_context(cafile=provider['ca_file']))
    page=browser.get(response.headers['location'])
    for _ in range(5):
        if page.status_code not in (302,303,307):break
        page=browser.get(page.headers['location'])
    form=Forms(page.text).containing('username')
    assert form is not None,'Keycloak did not render its username/password form'
    fields={**form['inputs'],'username':email,'password':provider['password']}
    result=browser.post(html.unescape(form['action']),data=fields)
    return browser,result


def callback(ctx, response):
    assert response.status_code in (302,303),'Keycloak did not issue the expected authorization redirect'
    location=response.headers['location'];parsed=urlsplit(location)
    assert parsed.netloc=='localhost:8000' and parsed.path=='/auth/oidc/callback'
    q=parse_qs(parsed.query);assert 'code' in q and 'state' in q
    return ctx['client'].get(parsed.path+'?'+parsed.query,follow_redirects=False)


def test_keycloak_real_authorization_code_login(ctx,keycloak):
    browser,result=begin_login(ctx,keycloak,'owner@nexus.local')
    try:
        assert callback(ctx,result).status_code==307
        me=ctx['client'].get('/v1/me')
        assert me.status_code==200 and me.json()['user']['role']=='owner'
    finally:browser.close()


def test_keycloak_unprovisioned_verified_email_has_no_access(ctx,keycloak):
    browser,result=begin_login(ctx,keycloak,'unprovisioned@nexus.local')
    try:
        assert callback(ctx,result).status_code==403
        assert ctx['client'].get('/v1/me').status_code==401
    finally:browser.close()


def test_keycloak_revoked_membership_has_no_access(ctx,keycloak):
    with ctx['db'].begin() as db:db.scalar(select(User).where(User.email=='owner@nexus.local')).active=0
    browser,result=begin_login(ctx,keycloak,'owner@nexus.local')
    try:assert callback(ctx,result).status_code==403
    finally:browser.close()


def test_keycloak_totp_is_required_and_verified(ctx,keycloak):
    browser,result=begin_login(ctx,keycloak,'reviewer@nexus.local')
    try:
        assert result.status_code==200
        form=Forms(result.text).containing('otp')
        assert form is not None,'Keycloak did not require the configured second factor'
        code=totp(keycloak['otp_secret']);wrong=str((int(code)+123)%1000000).zfill(6)
        rejected=browser.post(html.unescape(form['action']),data={**form['inputs'],'otp':wrong})
        assert rejected.status_code==200 and Forms(rejected.text).containing('otp') is not None
        form=Forms(rejected.text).containing('otp')
        accepted=browser.post(html.unescape(form['action']),data={**form['inputs'],'otp':totp(keycloak['otp_secret'])})
        assert callback(ctx,accepted).status_code==307
        assert ctx['client'].get('/v1/me').json()['user']['role']=='approver'
    finally:browser.close()


def test_keycloak_untrusted_tls_certificate_is_rejected(ctx,keycloak):
    ctx['settings'].oidc_issuer=keycloak['issuer']
    # No private test CA is configured: the self-signed test chain must fail verification.
    assert ctx['client'].get('/auth/oidc/start',follow_redirects=False).status_code==503


def test_keycloak_rejects_wrong_pkce_verifier(ctx,keycloak):
    from nexus.db import OIDCTransaction
    from nexus.oidc import encrypt_verifier
    browser,result=begin_login(ctx,keycloak,'owner@nexus.local')
    try:
        with ctx['db'].begin() as db:
            row=db.scalar(select(OIDCTransaction))
            row.verifier_ciphertext=encrypt_verifier(secrets.token_urlsafe(32),ctx['settings'].secret)
        assert callback(ctx,result).status_code==401
        assert ctx['client'].get('/v1/me').status_code==401
    finally:browser.close()
