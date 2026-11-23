"""Fresh-database recovery on the fixed disposable GitHub PostgreSQL service."""
import base64
from dataclasses import replace
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from nexus import backup as backup_module,encrypted_backup as sealed
from nexus.app import create_app
from nexus.backup_drill import LocalKeyOS,records
from nexus.cli import seed
from nexus.config import Settings
from nexus.db import Base,CURRENT_SCHEMA,migrate


def ci_service_url(environment):
    try:
        url=make_url(environment.get('NEXUS_TEST_DATABASE_URL',''))
        valid=(environment.get('GITHUB_ACTIONS')=='true' and environment.get('NEXUS_TEST_ALLOW_SCHEMA_CREATE')=='1' and
            url.drivername=='postgresql+psycopg' and url.host=='127.0.0.1' and url.port==5432 and
            url.database=='nexus_ci' and url.username=='nexus_ci' and not url.query)
    except (ArgumentError,ValueError):valid=False
    if not valid:raise RuntimeError('Recovery drill requires the fixed disposable GitHub PostgreSQL service.')
    return url


def owned_name(name):
    if not re.fullmatch(r'nexus_recovery_[a-f0-9]{32}',name):raise RuntimeError('Invalid disposable recovery database name.')
    return name


def pg_environment(url):
    return {'PGHOST':url.host,'PGPORT':str(url.port),'PGDATABASE':url.database,'PGUSER':url.username,'PGPASSWORD':url.password or ''}


class ContainerTools:
    """Match the service's client major; never put its password into argv."""
    def __init__(self,root,source,target,identity):
        self.root=Path(root).resolve();self.source=owned_name(source);self.target=owned_name(target);self.identity=identity
    def run(self,argv,*,env,**options):
        tool=argv[0]
        if tool=='pg_dump' and argv[1:4]==['--format=custom','--no-owner','--file'] and len(argv)==5:
            path=Path(argv[4]).resolve();arguments=argv[1:4]+['/nexus-fixture/'+path.name];database=self.source;access='rw'
        elif tool=='pg_restore' and argv[1:5]==['--exit-on-error','--no-owner','--no-privileges','--dbname'] and len(argv)==7 and argv[5]==self.target:
            path=Path(argv[6]).resolve();arguments=argv[1:6]+['/nexus-fixture/'+path.name];database=self.target;access='ro'
        else:raise RuntimeError('Unsupported disposable PostgreSQL tool invocation.')
        if not path.is_relative_to(self.root) or not path.parent.is_dir():raise RuntimeError('PostgreSQL fixture path is outside the drill.')
        if env.get('PGHOST')!='127.0.0.1' or env.get('PGPORT')!='5432' or env.get('PGUSER')!='nexus_ci' or env.get('PGDATABASE')!=database:
            raise RuntimeError('PostgreSQL fixture destination changed.')
        container='nexus-recovery-client-'+uuid.uuid4().hex
        command=['docker','run','--rm','--pull=never','--name',container,'--network','host','--user',self.identity,
            '--volume',str(path.parent)+':/nexus-fixture:'+access]
        environment=os.environ.copy()
        for key in ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD'):
            environment[key]=env.get(key,'');command+=['--env',key]
        command+=['postgres:16-alpine',tool,*arguments]
        try:return subprocess.run(command,env=environment,check=True,capture_output=True,timeout=60)
        except (OSError,subprocess.SubprocessError):
            # A killed docker client can leave its server-side container alive.
            # Remove only this invocation's generated, private client name.
            try:subprocess.run(['docker','rm','--force',container],check=False,capture_output=True,timeout=30)
            except (OSError,subprocess.SubprocessError):pass
            raise RuntimeError('Disposable PostgreSQL tool failed; no operator database was selected.') from None


def logical_records(engine):
    result={}
    with engine.connect() as db:
        for table in Base.metadata.sorted_tables:
            rows=[json.dumps(list(row),sort_keys=True,separators=(',',':'),default=lambda value:
                {'binary':base64.b64encode(value).decode()} if isinstance(value,bytes) else str(value)) for row in db.execute(select(table))]
            result[table.name]=(len(rows),hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest())
    return result


@pytest.mark.parametrize('change',[
    {'GITHUB_ACTIONS':'false'},{'NEXUS_TEST_ALLOW_SCHEMA_CREATE':'0'},
    {'NEXUS_TEST_DATABASE_URL':'postgresql+psycopg://nexus_ci:fixture@customer.invalid:5432/nexus_ci'},
    {'NEXUS_TEST_DATABASE_URL':'postgresql+psycopg://nexus_ci:fixture@127.0.0.1:5432/postgres'},
    {'NEXUS_TEST_DATABASE_URL':'postgresql+psycopg://other:fixture@127.0.0.1:5432/nexus_ci'},
    {'NEXUS_TEST_DATABASE_URL':'postgresql+psycopg://nexus_ci:fixture@127.0.0.1:5432/nexus_ci?options=private'},
])
def test_ci_recovery_rejects_non_fixture_configuration(change):
    environment={'GITHUB_ACTIONS':'true','NEXUS_TEST_ALLOW_SCHEMA_CREATE':'1',
        'NEXUS_TEST_DATABASE_URL':'postgresql+psycopg://nexus_ci:fixture@127.0.0.1:5432/nexus_ci',**change}
    with pytest.raises(RuntimeError):ci_service_url(environment)


@pytest.mark.parametrize('name',['nexus_ci','postgres','nexus_recovery_existing','unsafe; DROP DATABASE nexus_ci'])
def test_existing_or_unowned_database_names_are_rejected(name):
    with pytest.raises(RuntimeError):owned_name(name)


def test_container_bridge_confines_files_databases_and_passwords(tmp_path,monkeypatch):
    source='nexus_recovery_'+'a'*32;target='nexus_recovery_'+'b'*32;tools=ContainerTools(tmp_path,source,target,'1001:1001')
    calls=[]
    def launch(command,**kwargs):calls.append((command,kwargs));return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess,'run',launch)
    env={'PGHOST':'127.0.0.1','PGPORT':'5432','PGUSER':'nexus_ci','PGDATABASE':source,'PGPASSWORD':'private fixture password'}
    tools.run(['pg_dump','--format=custom','--no-owner','--file',str(tmp_path/'control.dump')],env=env)
    assert len(calls)==1 and 'private fixture password' not in ' '.join(calls[0][0])
    assert calls[0][1]['env']['PGPASSWORD']=='private fixture password' and calls[0][1]['timeout']==60
    with pytest.raises(RuntimeError):tools.run(['pg_dump','--format=custom','--no-owner','--file',str(tmp_path.parent/'outside.dump')],env=env)
    with pytest.raises(RuntimeError):tools.run(['pg_dump','--format=custom','--no-owner','--file',str(tmp_path/'control.dump')],env={**env,'PGDATABASE':'nexus_ci'})
    assert len(calls)==1


def test_container_tool_errors_hide_private_details(tmp_path,monkeypatch):
    tools=ContainerTools(tmp_path,'nexus_recovery_'+'a'*32,'nexus_recovery_'+'b'*32,'1001:1001')
    def broken(*args,**kwargs):raise OSError('private fixture exception')
    monkeypatch.setattr(subprocess,'run',broken)
    with pytest.raises(RuntimeError) as error:
        tools.run(['pg_dump','--format=custom','--no-owner','--file',str(tmp_path/'control.dump')],env={
            'PGHOST':'127.0.0.1','PGPORT':'5432','PGUSER':'nexus_ci','PGDATABASE':tools.source,'PGPASSWORD':'fixture'})
    assert 'private fixture exception' not in str(error.value) and error.value.__suppress_context__


def test_ci_encrypted_postgresql_recovery_into_fresh_database(tmp_path,monkeypatch):
    if os.name!='posix' or os.environ.get('GITHUB_ACTIONS')!='true' or not os.environ.get('NEXUS_TEST_DATABASE_URL'):
        pytest.skip('Requires the disposable Linux GitHub PostgreSQL service; never selects local operator data.')
    url=ci_service_url(os.environ)
    def no_operator_settings(*args,**kwargs):pytest.fail('Operator Settings were loaded')
    monkeypatch.setattr(Settings,'from_env',no_operator_settings)
    source_name='nexus_recovery_'+uuid.uuid4().hex;target_name='nexus_recovery_'+uuid.uuid4().hex
    admin=create_engine(url,isolation_level='AUTOCOMMIT');owned=[];apps=[]
    tools=ContainerTools(tmp_path,source_name,target_name,str(os.getuid())+':'+str(os.getgid()))
    key_view=LocalKeyOS({sealed.KEY_ENV:base64.b64encode(os.urandom(32)).decode()})
    def private_temp(**options):
        options.setdefault('dir',tmp_path)
        return TemporaryDirectory(**options)
    def expect(response,status):
        assert response.status_code==status
        return response.json()
    def headers(client):
        me=expect(client.get('/v1/me'),200);context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'],'X-Nexus-Context-Revision':str(context['revision'])}
    password=secrets.token_urlsafe(32)
    payload={'kind':'prompt','name':'Disposable PostgreSQL recovery marker','description':'CI recovery fixture',
        'config':{'template':'Evidence: {{question}}','required_terms':['Evidence'],'forbidden_terms':['invent']}}
    try:
        for name in (source_name,target_name):
            with admin.connect() as db:db.execute(text('CREATE DATABASE "'+owned_name(name)+'" TEMPLATE template0'))
            owned.append(name)
        settings=Settings(database_url=url.set(database=source_name).render_as_string(hide_password=False),
            mock_database=str(tmp_path/'source-business.db'),secret=secrets.token_urlsafe(48),agent_secret=secrets.token_urlsafe(48),
            frontend_dir=str(tmp_path/'no-frontend'),mode='local',policy_mode='reference',business_connector='synthetic',live_inference=0)
        source=create_app(settings);apps.append(source)
        migrate(source.state.engine,source.state.factory);seed(source.state.factory,password)
        with TestClient(source) as client:
            expect(client.post('/auth/local/login',json={'email':'owner@nexus.local','password':password}),200)
            marker=expect(client.post('/v1/workbench',json=payload,headers=headers(client)),201)
        # An explicit synthetic receipt fixture, not governed customer dispatch.
        receipt=source.state.connector.invoke('ci-recovery-receipt',{'action':'supplier:read','arguments':{'supplier_id':'SUP-DEMO-104'}})
        source.state.engine.dispose();gc.collect()
        before=logical_records(source.state.engine);business_before=records(settings.mock_database)
        assert before['users'][0]==3 and before['workspace_assets'][0]==1
        archive=tmp_path/'snapshot.enc'
        with monkeypatch.context() as patch:
            patch.setattr(backup_module,'subprocess',SimpleNamespace(run=tools.run,SubprocessError=subprocess.SubprocessError))
            patch.setattr(sealed,'os',key_view);patch.setattr(sealed,'tempfile',SimpleNamespace(TemporaryDirectory=private_temp))
            created=sealed.encrypted_backup(settings,archive,True);encrypted_bytes=archive.read_bytes()
            assert created['kind']=='postgresql' and not created['restore_verified']
            checked=sealed.inspect_encrypted_backup(archive)
            assert checked['authenticated'] and not checked['postgresql_restore_verified']
            with pytest.raises(RuntimeError):sealed.recover_encrypted_sqlite(archive,tmp_path/'wrong-kind')
            assert not (tmp_path/'wrong-kind').exists()
            with sealed.authenticated_snapshot(archive,temporary_parent=tmp_path) as (snapshot,inspection):
                assert inspection['kind']=='postgresql'
                tools.run(['pg_restore','--exit-on-error','--no-owner','--no-privileges','--dbname',target_name,str(snapshot/'control.dump')],
                    env=pg_environment(url.set(database=target_name)))
                business=tmp_path/'restored-business.db';shutil.copyfile(snapshot/'business.sqlite3',business)
        restored_settings=replace(settings,database_url=url.set(database=target_name).render_as_string(hide_password=False),mock_database=str(business))
        restored=create_app(restored_settings);apps.append(restored)
        # No migration or seeding is allowed on the recovered fixture.
        assert logical_records(restored.state.engine)==before and records(business)==business_before
        with TestClient(restored) as client:
            ready=expect(client.get('/health/ready'),200);assert ready['status']=='ready' and ready['schema_version']==CURRENT_SCHEMA
            assert client.get('/v1/me').status_code==401
            expect(client.post('/auth/local/login',json={'email':'owner@nexus.local','password':password}),200)
            assert expect(client.get('/v1/me'),200)['environment']=='staging'
            assert [row['id'] for row in expect(client.get('/v1/workbench'),200)['assets']]==[marker['id']]
            assert client.post('/v1/workbench',json=payload).status_code==403
            expect(client.post('/v1/workbench',json={**payload,'name':'Recovered copy only'},headers=headers(client)),201)
            client.cookies.clear();expect(client.post('/auth/local/login',json={'email':'auditor@nexus.local','password':password}),200)
            assert client.post('/v1/workbench',json=payload,headers=headers(client)).status_code==403
            assert len(expect(client.get('/v1/workbench'),200)['assets'])==2
            assert restored.state.connector.lookup('ci-recovery-receipt')==receipt and restored.state.connector.count()==1
        assert logical_records(source.state.engine)==before and records(settings.mock_database)==business_before
        assert archive.read_bytes()==encrypted_bytes
    finally:
        for app in apps:app.state.engine.dispose()
        gc.collect();errors=[]
        for name in reversed(owned):
            try:
                with admin.connect() as db:db.execute(text('DROP DATABASE "'+owned_name(name)+'" WITH (FORCE)'))
            except Exception:errors.append(True)
        admin.dispose()
        if errors:raise RuntimeError('Disposable PostgreSQL recovery database cleanup failed.')
