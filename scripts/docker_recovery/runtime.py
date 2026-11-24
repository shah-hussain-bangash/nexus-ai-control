"""Exercise only the prepared disposable recovery API in an owned Docker project."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from .safety import local_endpoint
import re
import secrets
import shutil
import socket
import subprocess
import time
import uuid

PROXY_DISABLED={key:'' for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')}
PROXY_DISABLED.update(NO_PROXY='*',no_proxy='*')


class RehearsalFailure(Exception):pass


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def exercise(workdir,revision,image,password,schema,port):
    if not __debug__:raise RuntimeError('Optimized Python is unsupported for this drill.')
    ROOT=Path(workdir).resolve();REVISION=revision;IMAGE=image;PORT=port
    assert (ROOT/'owned-workspace.json').is_file()
    # Only the user-run mode reads the protected synthetic recovery directory.
    folder=ROOT/'fixture/recovered'
    marker=read(folder/'.nexus-disposable-fixture.json')
    assert marker=={'format':'nexus-disposable-docker-recovery-fixture','revision':REVISION,
        'schema_version':schema,'synthetic':True,'prepared_for':'nexus-disposable-docker-recovery'}
    for path in (folder,folder/'control.sqlite3',folder/'business.sqlite3'):
        assert not path.is_symlink() and path.resolve().is_relative_to((ROOT/'fixture').resolve())
        if path.is_file():assert path.stat().st_nlink==1
    assert all((folder/name).is_file() for name in ('control.sqlite3','business.sqlite3'))
    if password is not None and not 12<=len(password)<=128:raise RuntimeError('INVALID_DISPOSABLE_PASSWORD_LENGTH')
    import httpx
    project='nexus-recovery-'+uuid.uuid4().hex[:12]
    output=ROOT/'container-runs'/project;output.mkdir(parents=True,exist_ok=False)
    environment={key:os.environ[key] for key in ('SystemRoot','WINDIR','PATH','TEMP','TMP','PATHEXT','COMSPEC',
        'HOME','XDG_CONFIG_HOME','XDG_RUNTIME_DIR','USERPROFILE','APPDATA','LOCALAPPDATA','ProgramData','ProgramFiles','ProgramFiles(x86)','DOCKER_CONFIG') if key in os.environ}
    environment.update(NEXUS_REVIEW_IMAGE=IMAGE,NEXUS_REVIEW_HTTP_PORT=str(PORT),
        NEXUS_REVIEW_SECRET=secrets.token_urlsafe(48),NEXUS_REVIEW_AGENT_SECRET=secrets.token_urlsafe(48),
        NEXUS_REVIEW_FIXTURE_DIRECTORY=str(folder),NEXUS_REVIEW_GATEWAY_FILE=str(ROOT/'recovery_gateway.py'))
    docker=shutil.which('docker');context=None;cid=None;gateway_id=None;up_attempted=False;model=None
    started=datetime.now(timezone.utc).isoformat();clock=time.perf_counter()
    checks=[];statuses={};diagnostics={};failure=None;failure_category=None;phase='local_context';cleanup_ok=True;stopped_ok=False
    source_files=[ROOT/'fixture/source/control.db',ROOT/'fixture/source/business.db',ROOT/'fixture/synthetic-backup.enc']
    before={path:digest(path) for path in source_files}
    def call(arguments,timeout=30):
        completed=subprocess.run([docker,*arguments],cwd=ROOT,env=environment,
            capture_output=True,text=True,timeout=timeout)
        if completed.returncode:
            error=completed.stderr.lower()
            if 'address already in use' in error or 'port is already allocated' in error:code='TEST_PORT_CONFLICT'
            elif 'no such image' in error:code='CANDIDATE_IMAGE_UNAVAILABLE'
            elif 'mount' in error and ('denied' in error or 'not found' in error):code='FIXTURE_MOUNT_UNAVAILABLE'
            elif 'permission denied' in error or 'access is denied' in error:code='DOCKER_ACCESS_DENIED'
            else:code='DOCKER_OPERATION_FAILED'
            raise RehearsalFailure(code)
        return completed.stdout.strip()
    def dock(*arguments,timeout=30):return call(['--context',context,*arguments],timeout)
    def compose(*arguments,timeout=30):
        return dock('compose','--project-name',project,'--env-file',str(ROOT/'validation-only.env'),
            '--project-directory',str(ROOT),'-f',str(ROOT/'recovery-proxy.compose.yaml'),*arguments,timeout=timeout)
    def inspect(template):return json.loads(dock('inspect','--format',template,cid))
    def inspect_gateway(template):return json.loads(dock('inspect','--format',template,gateway_id))
    def check(name,value):
        checks.append({'id':name,'passed':bool(value)})
        if not value:raise RuntimeError('REHEARSAL_CHECK_FAILED')
    def expect(response,status,name):
        statuses[name]=response.status_code;check(name,response.status_code==status)
        return response.json()
    def headers(client):
        response=client.get('/v1/me');assert response.status_code==200
        me=response.json();binding=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':binding['binding_id'],'X-Nexus-Context-Revision':str(binding['revision'])}
    class LoopbackTransport(httpx.HTTPTransport):
        def handle_request(self,request):
            assert request.url.scheme=='http' and request.url.host=='127.0.0.1' and request.url.port==PORT
            return super().handle_request(request)
    def client():return httpx.Client(base_url='http://127.0.0.1:'+str(PORT),transport=LoopbackTransport(),
        trust_env=False,follow_redirects=False,timeout=5)
    def ready(client):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            try:
                response=client.get('/health/ready')
                if response.status_code==200:return response
            except httpx.TransportError:pass
            if inspect('{{json .State.Running}}') is not True:raise RehearsalFailure('CANDIDATE_API_EXITED')
            time.sleep(.25)
        raise RehearsalFailure('CANDIDATE_READY_TIMEOUT')
    payload={'kind':'prompt','name':'Docker rehearsal write '+uuid.uuid4().hex[:8],'description':'Disposable Docker rehearsal',
        'config':{'template':'Evidence: {{question}} / {{context}}','required_terms':['Evidence'],'forbidden_terms':['invent']}}
    try:
        context=call(['context','show'])
        endpoint=json.loads(call(['context','inspect',context,'--format','{{json .Endpoints.docker.Host}}']))
        check('docker_context_is_local_socket',local_endpoint(endpoint))
        check('docker_engine_is_linux',dock('version','--format','{{.Server.Os}}')=='linux')
        phase='image_identity'
        check('local_image_matches_recorded_reference',json.loads(dock('image','inspect','--format','{{json .Id}}',IMAGE))==IMAGE)
        labels=json.loads(dock('image','inspect','--format','{{json .Config.Labels}}',IMAGE))
        check('image_revision_label_matches',labels.get('org.opencontainers.image.revision')==REVISION)
        phase='configuration'
        model=json.loads(compose('config','--format','json'))
        api=model['services']['recovered-api'];gateway=model['services']['recovery-gateway']
        mounts=api.get('volumes',[]);ports=gateway.get('ports',[])
        check('only_api_gateway_and_no_build',set(model['services'])=={'recovered-api','recovery-gateway'} and all(not service.get('build') for service in (api,gateway)))
        check('candidate_images_and_no_pull',all(service['image']==IMAGE and service.get('pull_policy')=='never' for service in (api,gateway)))
        check('single_owned_fixture_mount',len(mounts)==1 and mounts[0]['type']=='bind' and Path(mounts[0]['source']).resolve()==folder.resolve() and mounts[0]['target']=='/recovery' and mounts[0]['bind'].get('create_host_path') is False)
        check('single_loopback_port',len(ports)==1 and ports[0]['host_ip']=='127.0.0.1' and str(ports[0]['published'])==str(PORT) and ports[0]['target']==8000)
        check('api_unpublished_and_internal_only',not api.get('ports') and set(api['networks'])=={'recovery'})
        check('gateway_no_database_or_secret_mount',gateway.get('environment')==PROXY_DISABLED and len(gateway['volumes'])==1 and gateway['volumes'][0]['target']=='/review/recovery_gateway.py' and gateway['volumes'][0]['read_only'] is True and Path(gateway['volumes'][0]['source']).resolve()==ROOT/'recovery_gateway.py')
        runtime=api['environment']
        check('synthetic_reference_inference_disabled',runtime.get('NEXUS_MODE')=='local' and runtime.get('NEXUS_POLICY_MODE')=='reference' and runtime.get('NEXUS_BUSINESS_CONNECTOR')=='synthetic' and runtime.get('NEXUS_LIVE_INFERENCE')=='0')
        check('explicit_empty_proxy_environment',all(runtime.get(key)==value for key,value in PROXY_DISABLED.items()))
        check('internal_owned_network',model['networks']['recovery']['internal'] is True and model['networks']['recovery']['name']==project+'_recovery')
        check('gateway_access_network_only',set(gateway['networks'])=={'recovery','access'} and model['networks']['access'].get('internal',False) is False and model['networks']['access']['name']==project+'_access')
        check('new_project_has_no_containers',compose('ps','--all','--quiet')=='')
        with socket.socket() as probe:probe.bind(('127.0.0.1',PORT))
        check('test_port_available_before_start',True)
        phase='container_start';print('Starting the disposable recovered API and fixed-target gateway...',flush=True)
        up_attempted=True
        compose('up','--detach','--no-build','--pull','never','--no-deps','recovered-api','recovery-gateway',timeout=90)
        ids=compose('ps','--all','--quiet').splitlines()
        check('two_owned_containers_created',len(ids)==2 and all(re.fullmatch('[a-f0-9]{64}',value) for value in ids))
        roles={}
        for value in ids:
            labels=json.loads(dock('inspect','--format','{{json .Config.Labels}}',value))
            assert labels.get('com.docker.compose.project')==project
            roles[labels.get('com.docker.compose.service')]=value
        check('owned_api_and_gateway_roles',set(roles)=={'recovered-api','recovery-gateway'})
        cid=roles['recovered-api'];gateway_id=roles['recovery-gateway'];labels=inspect('{{json .Config.Labels}}')
        check('running_container_ownership_and_revision',labels.get('com.docker.compose.project')==project and labels.get('com.docker.compose.service')=='recovered-api' and labels.get('org.opencontainers.image.revision')==REVISION)
        check('requested_image_reference_preserved',inspect('{{json .Config.Image}}')==IMAGE)
        check('gateway_uses_same_image_reference',inspect_gateway('{{json .Config.Image}}')==IMAGE)
        check('container_nonprivileged_read_only_root',inspect('{{json .HostConfig.Privileged}}') is False and inspect('{{json .HostConfig.ReadonlyRootfs}}') is True)
        network=model['networks']['recovery']['name']
        check('actual_docker_network_is_internal',json.loads(dock('network','inspect','--format','{{json .Internal}}',network)) is True)
        check('actual_app_has_only_internal_attachment',set(inspect('{{json .NetworkSettings.Networks}}'))=={network})
        access=model['networks']['access']['name']
        check('actual_gateway_has_two_expected_networks',set(inspect_gateway('{{json .NetworkSettings.Networks}}'))=={network,access})
        check('actual_gateway_access_network_not_internal',json.loads(dock('network','inspect','--format','{{json .Internal}}',access)) is False)
        phase='http_acceptance'
        with client() as http:
            state=expect(ready(http),200,'ready_200')
            check('current_schema_ready',state['schema_version']==schema)
            bound=inspect_gateway('{{json .NetworkSettings.Ports}}').get('8000/tcp',[])
            check('actual_publish_is_loopback_only',len(bound)==1 and bound[0]['HostIp']=='127.0.0.1' and bound[0]['HostPort']==str(PORT))
            expect(http.get('/v1/me'),401,'anonymous_401')
            expect(http.post('/auth/local/login',json={'email':'owner@nexus.local','password':password}),200,'owner_login_200')
            identity=expect(http.get('/v1/me'),200,'owner_identity_200')
            check('owner_staging_identity',identity['user']['role']=='owner' and identity['environment']=='staging')
            listing=expect(http.get('/v1/workbench'),200,'known_listing_200')['assets']
            markers=[row for row in listing if row['name']=='Disposable Docker recovery marker']
            check('exact_known_marker_configuration',len(markers)==1 and markers[0]['config']==payload['config'])
            baseline={row['id'] for row in listing}
            expect(http.post('/v1/workbench',json=payload),403,'csrf_missing_403')
            http.cookies.clear()
            expect(http.post('/auth/local/login',json={'email':'auditor@nexus.local','password':password}),200,'auditor_login_200')
            check('auditor_role_confirmed',http.get('/v1/me').json()['user']['role']=='auditor')
            listing=expect(http.get('/v1/workbench'),200,'auditor_read_200')['assets']
            check('auditor_reads_same_recovered_records',{row['id'] for row in listing}==baseline)
            expect(http.post('/v1/workbench',json=payload,headers=headers(http)),403,'auditor_valid_context_write_403')
            http.cookies.clear()
            expect(http.post('/auth/local/login',json={'email':'owner@nexus.local','password':password}),200,'owner_relogin_200')
            added=expect(http.post('/v1/workbench',json=payload,headers=headers(http)),201,'owner_write_201')
            expected=baseline|{added['id']}
            check('new_record_created',added['id'] not in baseline)
        phase='restart';started_before=inspect('{{json .State.StartedAt}}')
        print('Checking records and permissions after restart...',flush=True)
        compose('restart','--timeout','10','recovered-api',timeout=45)
        with client() as http:
            expect(ready(http),200,'restart_ready_200')
            check('container_process_restarted',inspect('{{json .State.StartedAt}}')!=started_before)
            expect(http.get('/v1/me'),401,'restart_anonymous_401')
            expect(http.post('/auth/local/login',json={'email':'owner@nexus.local','password':password}),200,'restart_owner_login_200')
            listing=expect(http.get('/v1/workbench'),200,'restart_listing_200')['assets']
            check('exact_records_persisted_after_restart',{row['id'] for row in listing}==expected and next(row for row in listing if row['id']==added['id'])['config']==payload['config'])
            http.cookies.clear()
            expect(http.post('/auth/local/login',json={'email':'auditor@nexus.local','password':password}),200,'restart_auditor_login_200')
            check('restart_auditor_role_confirmed',http.get('/v1/me').json()['user']['role']=='auditor')
            expect(http.post('/v1/workbench',json=payload,headers=headers(http)),403,'restart_auditor_valid_context_write_403')
        phase='completed'
    except Exception as exc:
        failure=checks[-1]['id'] if checks and not checks[-1]['passed'] else phase
        failure_category=str(exc) if isinstance(exc,RehearsalFailure) else 'CHECK_OR_RUNTIME_ERROR'
    finally:
        if up_attempted:
            try:
                ids=compose('ps','--all','--quiet').splitlines()
                for owned in ids:
                    labels=json.loads(dock('inspect','--format','{{json .Config.Labels}}',owned))
                    assert labels.get('com.docker.compose.project')==project and labels.get('com.docker.compose.service') in ('recovered-api','recovery-gateway')
                network=model['networks']['recovery']['name']
                networks=dock('network','ls','--quiet','--filter','label=com.docker.compose.project='+project).splitlines()
                for owned in networks:
                    labels=json.loads(dock('network','inspect','--format','{{json .Labels}}',owned))
                    assert labels.get('com.docker.compose.project')==project and labels.get('com.docker.compose.network') in ('recovery','access')
                compose('down','--timeout','10',timeout=45)
                stopped_ok=compose('ps','--all','--quiet')=='' and dock('network','ls','--quiet','--filter','label=com.docker.compose.project='+project)==''
                cleanup_ok=stopped_ok
            except Exception:cleanup_ok=False
        try:source_unchanged=all(digest(path)==value for path,value in before.items())
        except OSError:source_unchanged=False
    if up_attempted and cleanup_ok:
        with socket.socket() as probe:
            probe.settimeout(1);port_closed=probe.connect_ex(('127.0.0.1',PORT))!=0
    else:port_closed=not up_attempted
    passed=failure is None and cleanup_ok and stopped_ok and port_closed and source_unchanged and all(row['passed'] for row in checks)
    receipt={'format':'nexus-disposable-docker-recovery-rehearsal','format_version':1,'passed':passed,
        'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds':round(time.perf_counter()-clock,3),'revision':REVISION,'schema_version':schema,
        'local_image_reference':IMAGE,'owned_project':project,'checks':checks,'checks_passed':sum(row['passed'] for row in checks),
        'http_statuses':statuses,'diagnostics':diagnostics,'failure':failure,'failure_category':failure_category,'owned_container_and_network_removed':stopped_ok,
        'cleanup_passed':cleanup_ok,'test_port_closed':port_closed,'source_and_archive_unchanged':source_unchanged,
        'disposable_recovered_files_retained':True,'passwords_cookies_or_keys_in_report':False,
        'runtime_secrets_supplied_in_child_environment':True,'live_app_changed':False,'merged':False,
        'network_topology':'internal-only API plus fixed-target gateway on recovery/access networks',
        'gateway_has_external_capable_attachment':True,
        'topology_artifacts_sha256':{name:digest(ROOT/name) for name in ('recovery-proxy.compose.yaml','recovery_gateway.py')},
        'production_deployed':False,'authenticated_signature':False,'runner_sha256':digest(Path(__file__)),
        'boundary':'User-run local Docker SQLite fixture and API/restart exercise only. Local reference policy and synthetic connector; not pilot identity/TLS/OPA, PostgreSQL, production cutover, off-host key custody, measured production RPO/RTO or independent authenticated acceptance.'}
    receipt_path=output/'container-rehearsal-receipt.json'
    receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt
