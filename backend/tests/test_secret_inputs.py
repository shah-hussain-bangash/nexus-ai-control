"""Mounted-secret behavior with disposable files and mock transports only."""
import os
from pathlib import Path
import httpx,pytest
from sqlalchemy import select,func
from conftest import auth
from test_inference import setup
from test_business_connector import business,envelope,authoritative
from nexus.secret_inputs import read_secret,source,SecretInputError,MAX_BYTES,STARTUP_SECRETS
from nexus.config import Settings
from nexus.business_connector import HTTPBusiness
from nexus.db import InferenceCall

NAME='NEXUS_PROVIDER_MOUNTED_TEST'


def mount(monkeypatch,tmp_path,value=b'synthetic-file-token-1234567890\n',name=NAME):
    path=tmp_path/'private-do-not-display.txt';path.write_bytes(value)
    monkeypatch.delenv(name,raising=False);monkeypatch.setenv(name+'_FILE',str(path))
    return path


def test_direct_and_mounted_values_are_explicit_and_file_newline_is_bounded(monkeypatch,tmp_path):
    monkeypatch.delenv(NAME,raising=False);monkeypatch.delenv(NAME+'_FILE',raising=False)
    assert read_secret(NAME)=='' and source(NAME)=='not_configured'
    monkeypatch.setenv(NAME,'direct-synthetic-token');assert read_secret(NAME)=='direct-synthetic-token'
    path=mount(monkeypatch,tmp_path,b'file-synthetic-token\r\n')
    assert read_secret(NAME)=='file-synthetic-token' and source(NAME)=='file'
    monkeypatch.setenv(NAME,'direct-synthetic-token');assert source(NAME)=='ambiguous'
    with pytest.raises(SecretInputError) as error:read_secret(NAME)
    assert str(path) not in str(error.value) and 'direct-synthetic-token' not in str(error.value)
    monkeypatch.setenv(NAME,'');assert read_secret(NAME)=='file-synthetic-token'


@pytest.mark.parametrize('raw',[b'',b'\n',b'token\n\n',b'token\x00bad',b'token\rbad',b'\xff',b'\xef\xbb\xbftoken',b'x'*(MAX_BYTES+1)])
def test_invalid_file_content_fails_without_leaking_value_or_path(monkeypatch,tmp_path,raw):
    path=mount(monkeypatch,tmp_path,raw)
    with pytest.raises(SecretInputError) as error:read_secret(NAME)
    assert 'private-do-not-display' not in str(error.value)


def test_nonregular_relative_missing_and_reserved_name_fail(monkeypatch,tmp_path):
    monkeypatch.delenv(NAME,raising=False)
    for path in ('relative.txt',str(tmp_path/'missing'),str(tmp_path)):
        monkeypatch.setenv(NAME+'_FILE',path)
        with pytest.raises(SecretInputError):read_secret(NAME)
    with pytest.raises(SecretInputError):read_secret(NAME+'_FILE')


def test_symlink_is_not_accepted(monkeypatch,tmp_path):
    target=mount(monkeypatch,tmp_path)
    link=tmp_path/'link'
    try:link.symlink_to(target)
    except OSError:pytest.skip('This Windows identity cannot create symlinks.')
    monkeypatch.setenv(NAME+'_FILE',str(link))
    with pytest.raises(SecretInputError):read_secret(NAME)


def test_inode_swap_between_preflight_and_open_fails(monkeypatch,tmp_path):
    path=mount(monkeypatch,tmp_path);replacement=tmp_path/'replacement';replacement.write_text('replacement-synthetic-token')
    real_open=os.open
    def swap(file,flags,*args,**kwargs):
        if Path(file)==path:os.replace(replacement,path)
        return real_open(file,flags,*args,**kwargs)
    monkeypatch.setattr(os,'open',swap)
    with pytest.raises(SecretInputError):read_secret(NAME)


def test_startup_secret_fields_resolve_files_without_exporting_values_to_environment(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    for field in STARTUP_SECRETS:
        name='NEXUS_'+field.upper();monkeypatch.delenv(name,raising=False);monkeypatch.delenv(name+'_FILE',raising=False)
    for field in STARTUP_SECRETS:
        path=tmp_path/(field+'.txt');path.write_text('synthetic-'+field+'-'+'x'*40)
        monkeypatch.setenv('NEXUS_'+field.upper()+'_FILE',str(path))
    settings=Settings.from_env()
    assert settings.secret.startswith('synthetic-secret-')
    assert settings.agent_secret.startswith('synthetic-agent_secret-')
    assert set(settings._secret_input_sources.values())=={'file'}
    assert os.environ.get('NEXUS_SECRET') is None
    (tmp_path/'secret.txt').write_text('rotated-startup-token-'+'x'*40)
    assert settings.secret.startswith('synthetic-secret-')
    assert Settings.from_env().secret.startswith('rotated-startup-token-')
    monkeypatch.setenv('NEXUS_SECRET','ambiguous-direct-secret')
    with pytest.raises(SecretInputError):Settings.from_env()


def test_provider_file_rotation_is_used_once_per_dispatch_without_changing_reference(ctx,monkeypatch,tmp_path):
    headers,body,sent=setup(ctx,monkeypatch)
    path=mount(monkeypatch,tmp_path,b'provider-first-synthetic-token\n',name='NEXUS_PROVIDER_TEST_KEY')
    first=ctx['client'].post('/v1/inference',headers=headers,json=body);assert first.status_code==200,first.text
    assert sent[0].headers['authorization']=='Bearer provider-first-synthetic-token'
    path.write_text('provider-second-synthetic-token\n')
    headers['Idempotency-Key']='mounted-provider-second-intent'
    second=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert second.status_code==200 and sent[1].headers['authorization']=='Bearer provider-second-synthetic-token'
    assert len(sent)==2 and 'provider-second' not in second.text
    path.unlink();headers['Idempotency-Key']='mounted-provider-unavailable'
    failed=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert failed.status_code==503 and len(sent)==2
    assert 'private-do-not-display' not in failed.text


def test_inference_uses_the_credential_rechecked_under_admission_lock(ctx,monkeypatch,tmp_path):
    headers,body,sent=setup(ctx,monkeypatch)
    path=mount(monkeypatch,tmp_path,b'before-admission-synthetic-token',name='NEXUS_PROVIDER_TEST_KEY')
    import nexus.secret_inputs as inputs
    original=inputs.read_secret;reads=[]
    def rotate_after_first_read(name):
        value=original(name);reads.append(value)
        if len(reads)==1:path.write_text('at-admission-synthetic-token')
        return value
    monkeypatch.setattr(inputs,'read_secret',rotate_after_first_read)
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==200,response.text
    assert reads==['before-admission-synthetic-token','at-admission-synthetic-token']
    assert len(sent)==1 and sent[0].headers['authorization']=='Bearer at-admission-synthetic-token'


@pytest.mark.parametrize('mode',['ambiguous','invalid','missing'])
def test_provider_secret_failure_blocks_before_network_and_reservation(ctx,monkeypatch,tmp_path,mode):
    headers,body,sent=setup(ctx,monkeypatch)
    path=mount(monkeypatch,tmp_path,b'provider-synthetic-token',name='NEXUS_PROVIDER_TEST_KEY')
    if mode=='ambiguous':monkeypatch.setenv('NEXUS_PROVIDER_TEST_KEY','other-synthetic-token')
    if mode=='invalid':path.write_bytes(b'bad\ntoken')
    if mode=='missing':path.unlink()
    response=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert response.status_code==503 and response.json()['error']['code']=='PROVIDER_SECRET_UNAVAILABLE' and sent==[]
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(InferenceCall))==0


def test_business_file_rotation_and_failure_never_resend(business,monkeypatch,tmp_path):
    path=mount(monkeypatch,tmp_path,b'business-first-synthetic-token',name=business.business_token_env);seen=[]
    def handler(request):seen.append(request);return authoritative(request,business)
    adapter=HTTPBusiness(business,transport=httpx.MockTransport(handler))
    adapter.invoke('operation-001',envelope(business));assert seen[0].headers['authorization']=='Bearer business-first-synthetic-token'
    path.write_text('business-second-synthetic-token\n')
    adapter.invoke('operation-002',envelope(business));assert seen[1].headers['authorization']=='Bearer business-second-synthetic-token'
    monkeypatch.setenv(business.business_token_env,'ambiguous-synthetic-token')
    with pytest.raises(RuntimeError):adapter.invoke('operation-003',envelope(business))
    assert len(seen)==2


def test_status_is_owner_only_and_reports_sources_without_reading_files(ctx,monkeypatch,tmp_path):
    path=mount(monkeypatch,tmp_path,b'NEVER RETURN THIS VALUE')
    monkeypatch.setenv('NEXUS_PROVIDER_AMBIGUOUS','ambiguous-value');monkeypatch.setenv('NEXUS_PROVIDER_AMBIGUOUS_FILE',str(path))
    import nexus.secret_inputs as inputs
    monkeypatch.setattr(inputs,'read_secret',lambda _:(_ for _ in ()).throw(AssertionError('Status must not resolve secrets')))
    auth(ctx);response=ctx['client'].get('/v1/secret-inputs');assert response.status_code==200,response.text
    assert response.json()['provider_input_counts']['file']>=1 and response.json()['provider_input_counts']['ambiguous']>=1
    assert 'NEVER RETURN' not in response.text and str(path) not in response.text and NAME not in response.text
    assert ctx['client'].get('/v1/secret-inputs',headers={'X-Nexus-Environment':'production'}).status_code==409
    auth(ctx,'auditor');assert ctx['client'].get('/v1/secret-inputs').status_code==403
    ctx['client'].cookies.clear();assert ctx['client'].get('/v1/secret-inputs').status_code==401
