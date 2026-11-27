"""Ephemeral signing keys and disposable evidence only."""
import copy,json,subprocess,sys,os
from pathlib import Path
import pytest
from sqlalchemy import select,func
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from conftest import auth
from nexus.db import Audit,WorkbenchRun
from nexus.audit_signature import verify,canonical,key_id,MAX_BYTES

BASE='/v1/signed-audit-evidence'


@pytest.fixture
def signing(ctx,tmp_path):
    key=Ed25519PrivateKey.generate()
    path=tmp_path/'disposable-private.pem'
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    ctx['settings'].audit_signing_key_file=str(path)
    return key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)


def create(ctx,key='signed-audit-intent-0001',limit=200,role='owner',identity=None):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    if identity is None:identity=ctx['client'].get(BASE).json().get('key_id') or '0'*64
    return ctx['client'].post(BASE,headers=headers,json={'expected_key_id':identity,'limit':limit,'note':'Reviewed synthetic audit metadata.'})


def download(ctx,result):
    response=ctx['client'].get(BASE+'/'+result['id']);assert response.status_code==200,response.text
    return response.json()


def test_disabled_by_default_and_invalid_key_does_not_disclose_path(ctx,tmp_path):
    auth(ctx);assert ctx['client'].get(BASE).json()['enabled'] is False
    assert create(ctx).status_code==409
    path=tmp_path/'private-path-do-not-expose.pem';path.write_text('not a signing key')
    ctx['settings'].audit_signing_key_file=str(path)
    overview=ctx['client'].get(BASE);assert overview.json()['available'] is False and 'private-path' not in overview.text
    assert create(ctx).status_code==503
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkbenchRun))==0


def test_signed_metadata_is_verifiable_scoped_bounded_and_omits_detail(ctx,signing):
    with ctx['db'].begin() as db:
        for i in range(4):db.add(Audit(org_id='northstar',env='staging',event='synthetic.'+str(i),actor='synthetic',created=100+i,detail={'private':'NEVER EXPORT REQUEST CONTENT'}))
        db.add(Audit(org_id='other',env='staging',event='OTHER WORKSPACE',actor='synthetic'))
        db.add(Audit(org_id='northstar',env='development',event='OTHER ENVIRONMENT',actor='synthetic'))
    result=create(ctx,limit=2);assert result.status_code==201,result.text
    receipt=result.json();assert receipt['records']==2 and receipt['truncated']
    envelope=download(ctx,receipt);checked=verify(canonical(envelope),signing,'northstar','staging')
    assert checked['authenticated_signature'] and checked['records']==2 and checked['truncated']
    text=json.dumps(envelope);assert 'NEVER EXPORT' not in text and 'OTHER WORKSPACE' not in text and 'OTHER ENVIRONMENT' not in text
    assert [row['event'] for row in envelope['payload']['records']]==['synthetic.2','synthetic.3']
    assert all(type(row['created_at_us']) is int for row in envelope['payload']['records'])
    assert receipt['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


@pytest.mark.parametrize('tamper',['record','scope','key_id','signature','algorithm','extra','duplicate','float_time'])
def test_offline_verifier_rejects_mutation_and_malformed_envelopes(ctx,signing,tamper):
    with ctx['db'].begin() as db:db.add(Audit(org_id='northstar',env='staging',event='synthetic',actor='synthetic'))
    envelope=download(ctx,create(ctx).json())
    if tamper=='record':envelope['payload']['records'][0]['event']='changed'
    if tamper=='scope':envelope['payload']['environment']='development'
    if tamper=='key_id':envelope['key_id']='0'*64
    if tamper=='signature':envelope['signature']='A'*88
    if tamper=='algorithm':envelope['algorithm']='none'
    if tamper=='extra':envelope['unsigned_extra']='injected'
    if tamper=='float_time':envelope['payload']['created_at_us']=1.5
    raw=canonical(envelope)
    if tamper=='duplicate':raw=raw.replace(b'"format":',b'"format":"duplicate","format":',1)
    with pytest.raises(ValueError):verify(raw,signing,'northstar','staging')


def test_trusted_key_and_expected_scope_are_independent_requirements(ctx,signing):
    envelope=download(ctx,create(ctx).json());raw=canonical(envelope)
    other=Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    for public,org,env in [(other,'northstar','staging'),(signing,'other','staging'),(signing,'northstar','development')]:
        with pytest.raises(ValueError):verify(raw,public,org,env)
    with pytest.raises(ValueError):verify(b'x'*(MAX_BYTES+1),signing,'northstar','staging')


def test_retries_and_recovery_return_original_snapshot_after_rotation_or_disable(ctx,signing,tmp_path):
    first=create(ctx).json();assert create(ctx).json()['id']==first['id']
    assert create(ctx,limit=1).status_code==409
    assert create(ctx,key='signed-audit-intent-stale',identity='0'*64).status_code==409
    original=download(ctx,first)
    key=Ed25519PrivateKey.generate();path=tmp_path/'rotated-test.pem'
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));ctx['settings'].audit_signing_key_file=str(path)
    assert create(ctx,identity=first['key_id']).json()['id']==first['id']
    second=create(ctx,key='signed-audit-intent-0002').json();assert second['key_id']!=first['key_id']
    ctx['settings'].audit_signing_key_file=''
    headers,_=auth(ctx)
    recovered=ctx['client'].post(BASE+'/recover',json={'key':'signed-audit-intent-0001'},headers=headers).json()
    assert recovered['id']==first['id'] and download(ctx,first)==original
    assert verify(canonical(original),signing,'northstar','staging')['authenticated_signature']


def test_export_permission_owner_and_environment_boundaries(ctx,signing):
    first=create(ctx).json()
    headers,_=auth(ctx,'auditor')
    assert ctx['client'].get(BASE+'/'+first['id']).status_code==404
    assert ctx['client'].post(BASE+'/recover',json={'key':'signed-audit-intent-0001'},headers=headers).status_code==404
    assert create(ctx,role='approver').status_code==403
    auth(ctx,org='other');assert ctx['client'].get(BASE+'/'+first['id']).status_code==404
    auth(ctx);assert ctx['client'].get(BASE,headers={'X-Nexus-Environment':'production'}).status_code==409
    from test_runtime_context import revoke
    headers,user_id=auth(ctx);revoke(ctx,user_id)
    assert ctx['client'].get(BASE+'/'+first['id']).status_code==403


def test_expired_or_scope_modified_evidence_is_not_downloaded(ctx,signing):
    first=create(ctx).json()
    with ctx['db'].begin() as db:
        row=db.get(WorkbenchRun,first['id']);row.result={**row.result,'expires':1}
    assert ctx['client'].get(BASE+'/'+first['id']).status_code==404
    second=create(ctx,key='signed-audit-intent-0002').json()
    with ctx['db'].begin() as db:
        row=db.get(WorkbenchRun,second['id']);value=copy.deepcopy(row.result);value['envelope']['payload']['workspace_id']='other';row.result=value
    assert ctx['client'].get(BASE+'/'+second['id']).status_code==409


def test_rsa_private_key_is_rejected_and_no_private_material_is_returned(ctx,tmp_path):
    key=generate_private_key(public_exponent=65537,key_size=2048);path=tmp_path/'rsa.pem'
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));ctx['settings'].audit_signing_key_file=str(path)
    auth(ctx);assert ctx['client'].get(BASE).json()['available'] is False
    result=create(ctx);assert result.status_code==503 and 'PRIVATE KEY' not in result.text


def test_offline_cli_needs_no_settings_database_or_private_key(ctx,signing,tmp_path):
    evidence=tmp_path/'evidence.json';evidence.write_bytes(canonical(download(ctx,create(ctx).json())))
    public=tmp_path/'trusted.pub.pem';public.write_bytes(signing)
    command=[sys.executable,'-m','nexus.audit_signature','--evidence',str(evidence),'--public-key',str(public),'--workspace','northstar','--environment','staging']
    environment={**os.environ,'NEXUS_DATABASE_URL':'invalid://unavailable','NEXUS_SECRET':'','NEXUS_AUDIT_SIGNING_KEY_FILE':'missing-private-key'}
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',env=environment,timeout=20)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['authenticated_signature']
    evidence.write_text('{}')
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',env=environment,timeout=20)
    assert result.returncode==1 and not json.loads(result.stdout)['authenticated_signature']


def test_capacity_preserves_existing_evidence(ctx,signing):
    first=create(ctx).json()
    with ctx['db'].begin() as db:
        for i in range(99):db.add(WorkbenchRun(org_id='northstar',env='staging',author_id='capacity-fixture',kind='signed_audit_metadata',status='ready',duration_ms=0,result={}))
    assert create(ctx,key='signed-audit-over-capacity').status_code==429
    assert verify(canonical(download(ctx,first)),signing,'northstar','staging')['authenticated_signature']


@pytest.mark.parametrize('limit',[0,1001,True,1.5])
def test_invalid_bounds_and_notes_do_not_create_snapshots(ctx,signing,limit):
    assert create(ctx,limit=limit).status_code==422
    headers,_=auth(ctx);headers['Idempotency-Key']='signed-audit-invalid-note'
    identity=ctx['client'].get(BASE).json()['key_id']
    assert ctx['client'].post(BASE,headers=headers,json={'limit':1,'expected_key_id':identity,'note':' '*10}).status_code==422
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkbenchRun))==0


def test_mutating_endpoints_require_csrf_and_create_requires_intent_key(ctx,signing):
    headers,_=auth(ctx);identity=ctx['client'].get(BASE).json()['key_id']
    body={'limit':1,'expected_key_id':identity,'note':'Synthetic audit review.'}
    assert ctx['client'].post(BASE,headers=headers,json=body).status_code==422
    assert ctx['client'].post(BASE,headers={'Idempotency-Key':'signed-audit-missing-csrf'},json=body).status_code==403
    assert ctx['client'].post(BASE+'/recover',json={'key':'signed-audit-intent-0001'}).status_code==403


def test_browser_json_roundtrip_preserves_signature_and_near_equal_times(ctx,signing):
    with ctx['db'].begin() as db:
        db.add(Audit(id='z-near-time',org_id='northstar',env='staging',event='synthetic',actor='synthetic',created=1000.0000001))
        db.add(Audit(id='a-near-time',org_id='northstar',env='staging',event='synthetic',actor='synthetic',created=1000.0000002))
    envelope=download(ctx,create(ctx).json())
    browser=subprocess.run(['node','-e','let s="";process.stdin.on("data",c=>s+=c);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s),null,2)));'],input=json.dumps(envelope),capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert browser.returncode==0,browser.stderr
    assert verify(browser.stdout.encode('utf-8'),signing,'northstar','staging')['authenticated_signature']
