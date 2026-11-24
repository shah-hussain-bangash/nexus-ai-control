"""Opt-in disposable Docker SQLite recovery/restart rehearsal; never live data."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import tempfile
import time
import uuid

SCRIPTS=Path(__file__).resolve().parent
REPO=SCRIPTS.parent
sys.path.insert(0,str(SCRIPTS))
from docker_recovery import fixture,runtime
from docker_recovery.safety import (Docker,DrillError,cleanup_workspace,export_source,git,
    remove_owned_image,require,source_metadata,container_user)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true',help='Check source and CLI prerequisites only; no daemon/build/containers.')
    mode.add_argument('--run',action='store_true',help='Build/run only newly owned synthetic recovery resources, then clean them up.')
    parser.add_argument('--output-dir',type=Path,default=REPO/'backend/data/drills')
    args=parser.parse_args(argv)
    try:
        source=source_metadata(REPO)
        require(shutil.which('docker'),'DOCKER_CLI_MISSING')
        user=container_user()
    except DrillError as error:
        print(json.dumps({'passed':False,'failure':str(error),'application_container_start_attempted':False}));return 1
    if args.check:
        print(json.dumps({'passed':True,'check_only':True,**source,'docker_cli_present':True,
            'docker_engine_contacted':False,'images_built':False,'application_container_start_attempted':False,'container_user':user,
            'boundary':'Source/CLI prerequisites only. Docker runtime, permissions, image and recovery acceptance remain untested.'}))
        return 0
    output=args.output_dir.resolve();default=(REPO/'backend/data/drills').resolve()
    require(not output.is_relative_to(REPO.resolve()) or output.is_relative_to(default),'OUTPUT_MUST_BE_IGNORED_OR_OUTSIDE_SOURCE')
    output.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='.docker-recovery-',dir=output)).resolve()
    require(work.is_relative_to(output),'OWNED_WORKSPACE_REQUIRED')
    nonce=uuid.uuid4().hex;tag='nexus-disposable-recovery:'+nonce
    (work/'owned-workspace.json').write_text(json.dumps({'format':'nexus-owned-docker-recovery','nonce':nonce}))
    started=datetime.now(timezone.utc).isoformat();clock=time.perf_counter()
    client=None;phase='docker_preflight';failure=None;image=None;fixture_result=None;runtime_result=None
    workspace_cleaned=False;image_removed=False;build_attempted=False;build_completed=False;build_result=None
    try:
        client=Docker(work)
        require(not client.run('image','ls','--quiet','--filter','reference='+tag),'IMAGE_TAG_ALREADY_EXISTS')
        archive,context=export_source(REPO,source['revision'],work)
        phase='image_build';print('Building the disposable source-pinned image...',flush=True)
        build_attempted=True
        client.run('build','--pull','--iidfile',str(work/'image-id.txt'),'--tag',tag,
            '--label','org.opencontainers.image.revision='+source['revision'],
            '--label','io.nexus.recovery.run='+nonce,'--file',str(context/'Dockerfile'),str(context),timeout=900)
        build_completed=True
        image=(work/'image-id.txt').read_text().strip()
        require(image.startswith('sha256:') and len(image)==71,'INVALID_LOCAL_IMAGE_ID')
        require(client.value('image','inspect','--format','{{json .Id}}',tag)==image,'IMAGE_ID_MISMATCH')
        labels=client.value('image','inspect','--format','{{json .Config.Labels}}',tag)
        require(labels.get('org.opencontainers.image.revision')==source['revision'] and labels.get('io.nexus.recovery.run')==nonce,'IMAGE_PROVENANCE_MISMATCH')
        build_result={'local_image_reference':image,'source_archive_sha256':sha(archive),'dockerfile_sha256':sha(context/'Dockerfile'),
            'docker_engine_version':client.run('version','--format','{{.Server.Version}}'),
            'platform':client.run('image','inspect','--format','{{.Os}}/{{.Architecture}}',tag)}
        for old,new in (('compose.yaml','recovery-proxy.compose.yaml'),('gateway.py','recovery_gateway.py')):
            shutil.copyfile(SCRIPTS/'docker_recovery'/old,work/new)
        (work/'validation-only.env').write_text('# Empty: inputs are generated privately by this invocation.\n')
        phase='fixture_preparation'
        password=secrets.token_urlsafe(32)
        fixture_result=fixture.prepare(REPO,work/'fixture',password,source['revision'])
        phase='runtime'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        runtime_result=runtime.exercise(work,source['revision'],image,password,fixture_result['schema_version'],port)
        password=None
        require(runtime_result['passed'],'RUNTIME_ACCEPTANCE_FAILED')
        require(git(REPO,'rev-parse','HEAD')==source['revision'] and git(REPO,'status','--porcelain','--untracked-files=all')=='','SOURCE_CHANGED_DURING_REHEARSAL')
        phase='completed'
    except (Exception,KeyboardInterrupt) as error:
        failure=str(error) if isinstance(error,DrillError) else 'TEST_INTERRUPTED' if isinstance(error,KeyboardInterrupt) else 'DISPOSABLE_REHEARSAL_FAILED'
    finally:
        # If runtime ownership/cleanup is uncertain, retain its mount and image
        # instead of deleting files that an application container may still use.
        safe_to_clean=(not build_attempted or build_completed) and (phase!='runtime' if runtime_result is None else runtime_result['cleanup_passed'])
        if safe_to_clean:
            try:image_removed=remove_owned_image(client,tag,nonce) if client and build_attempted else True
            except Exception:image_removed=False
            try:workspace_cleaned=cleanup_workspace(work,output,nonce)
            except Exception:workspace_cleaned=False
    passed=failure is None and bool(runtime_result and runtime_result['passed']) and workspace_cleaned and image_removed
    if fixture_result:fixture_result['fixture_files_retained_for_container_review']=not workspace_cleaned
    if runtime_result:runtime_result['disposable_recovered_files_retained']=not workspace_cleaned
    receipt={'format':'nexus-disposable-docker-recovery-drill','format_version':1,'passed':passed,
        'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds':round(time.perf_counter()-clock,3),**source,'local_image_reference':image,
        'phase':phase,'failure':failure,'build':build_result,'fixture':fixture_result,'runtime':runtime_result,
        'temporary_workspace_cleaned':workspace_cleaned,'owned_image_tag_removed':image_removed,
        'retained_workspace':str(work) if not workspace_cleaned else None,
        'artifact_sha256':{name:sha(SCRIPTS/name) for name in ('run_docker_recovery_drill.py','docker_recovery/fixture.py','docker_recovery/runtime.py','docker_recovery/safety.py','docker_recovery/compose.yaml','docker_recovery/gateway.py')},
        'authenticated_signature':False,'live_app_changed':False,'production_deployed':False,
        'boundary':'New synthetic SQLite Docker fixture only. Overlapping fixture/runtime checks are not unique aggregate coverage. Unsigned local receipt; not customer/pilot identity/TLS/OPA, PostgreSQL deployment recovery, off-host key custody, power-loss durability or measured production RPO/RTO acceptance.'}
    path=output/('synthetic-docker-recovery-'+uuid.uuid4().hex+'.json')
    with path.open('x',encoding='utf-8') as stream:json.dump(receipt,stream,indent=2)
    print(json.dumps({'passed':passed,'fixture_checks_passed':fixture_result['checks_passed'] if fixture_result else 0,
        'runtime_checks_passed':runtime_result['checks_passed'] if runtime_result else 0,
        'failure':failure,'runtime_failure':runtime_result.get('failure') if runtime_result else None,
        'runtime_failure_category':runtime_result.get('failure_category') if runtime_result else None,
        'cleanup_passed':workspace_cleaned and image_removed,'report':str(path)}))
    return 0 if passed else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit('Could not create or publish the disposable drill result. Preserve any owned workspace; no acceptance or cleanup success is claimed.') from None
