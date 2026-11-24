"""Local-only Docker and owned-workspace boundaries for the disposable drill."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from urllib.parse import urlsplit
import zipfile


class DrillError(Exception):pass


def require(value,code):
    if not value:raise DrillError(code)


def local_endpoint(endpoint):
    if not isinstance(endpoint,str):return False
    if re.fullmatch(r'npipe:/{2,}\./pipe/[A-Za-z0-9_.-]+',endpoint):return True
    try:
        parsed=urlsplit(endpoint)
        return parsed.scheme=='unix' and not parsed.netloc and parsed.path.startswith('/') and not parsed.query and not parsed.fragment
    except ValueError:return False


def client_environment():
    names=('SystemRoot','WINDIR','PATH','TEMP','TMP','PATHEXT','COMSPEC','HOME','XDG_CONFIG_HOME',
        'XDG_RUNTIME_DIR','USERPROFILE','APPDATA','LOCALAPPDATA','ProgramData','ProgramFiles','ProgramFiles(x86)','DOCKER_CONFIG')
    return {name:os.environ[name] for name in names if name in os.environ}


def container_user(uid=None,gid=None):
    # Native recovery files remain 0700/0600. On Unix, run as their non-root
    # creator instead of changing private file modes or ownership globally.
    if uid is None:
        if os.name=='nt':return '10001:10001'
        uid=os.getuid();gid=os.getgid()
    require(type(uid) is int and uid>0 and type(gid) is int and gid>=0,'NONROOT_UNIX_HOST_USER_REQUIRED')
    return str(uid)+':'+str(gid)


class Docker:
    def __init__(self,work):
        self.work=Path(work);self.environment=client_environment();self.executable=shutil.which('docker')
        require(self.executable,'DOCKER_CLI_MISSING')
        self.context=self.raw(['context','show'])
        endpoint=json.loads(self.raw(['context','inspect',self.context,'--format','{{json .Endpoints.docker.Host}}']))
        require(local_endpoint(endpoint),'REMOTE_DOCKER_CONTEXT_REFUSED')
        require(self.run('version','--format','{{.Server.Os}}')=='linux','LINUX_DOCKER_ENGINE_REQUIRED')
    def raw(self,arguments,timeout=60):
        try:
            result=subprocess.run([self.executable,*arguments],cwd=self.work,env=self.environment,
                capture_output=True,text=True,timeout=timeout)
        except (OSError,subprocess.SubprocessError):raise DrillError('DOCKER_TOOL_UNAVAILABLE_OR_TIMEOUT') from None
        require(result.returncode==0,'DOCKER_OPERATION_FAILED')
        return result.stdout.strip()
    def run(self,*arguments,timeout=60):return self.raw(['--context',self.context,*arguments],timeout)
    def value(self,*arguments):return json.loads(self.run(*arguments))


def git(repo,*arguments):
    try:
        result=subprocess.run(['git','-c','safe.directory='+Path(repo).resolve().as_posix(),'-C',str(repo),*arguments],
            capture_output=True,text=True,timeout=30)
    except (OSError,subprocess.SubprocessError):raise DrillError('SOURCE_GIT_UNAVAILABLE') from None
    require(result.returncode==0,'SOURCE_GIT_FAILED')
    return result.stdout.strip()


def source_metadata(repo):
    require(__debug__,'OPTIMIZED_PYTHON_REFUSED')
    repo=Path(repo).resolve()
    require(git(repo,'status','--porcelain','--untracked-files=all')=='','CLEAN_CHECKOUT_REQUIRED')
    require(not re.search(r'(?m)^(120000|160000) ',git(repo,'ls-tree','-r','HEAD')),'SOURCE_LINKS_OR_SUBMODULES_REFUSED')
    require(all((repo/name).is_file() for name in ('Dockerfile','.dockerignore','backend/nexus/app.py')),'SOURCE_LAYOUT_INVALID')
    return {'revision':git(repo,'rev-parse','HEAD'),'tree':git(repo,'rev-parse','HEAD^{tree}')}


def export_source(repo,revision,work):
    archive=Path(work)/'source.zip';context=Path(work)/'source'
    git(repo,'archive','--format=zip','--output',str(archive),revision)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            name=entry.filename;parts=PurePosixPath(name).parts
            require(entry.orig_filename==name and parts and not name.startswith('/') and '\\' not in name and ':' not in name and
                all(part not in ('.','..') for part in parts),'UNSAFE_SOURCE_ARCHIVE')
            require((context/name).resolve().is_relative_to(context.resolve()),'UNSAFE_SOURCE_ARCHIVE')
        bundle.extractall(context)
    return archive,context


def cleanup_workspace(work,parent,nonce):
    work=Path(work);parent=Path(parent).resolve();resolved=work.resolve()
    require(not work.is_symlink() and resolved!=parent and resolved.is_relative_to(parent) and
        resolved.name.startswith('.docker-recovery-'),'WORKSPACE_CLEANUP_REFUSED')
    marker=resolved/'owned-workspace.json'
    require(marker.is_file() and not marker.is_symlink(),'WORKSPACE_CLEANUP_REFUSED')
    require(json.loads(marker.read_text())=={'format':'nexus-owned-docker-recovery','nonce':nonce},'WORKSPACE_CLEANUP_REFUSED')
    shutil.rmtree(resolved)
    return not resolved.exists()


def remove_owned_image(client,tag,nonce):
    if not client.run('image','ls','--quiet','--filter','reference='+tag):return True
    labels=client.value('image','inspect','--format','{{json .Config.Labels}}',tag)
    require(labels.get('io.nexus.recovery.run')==nonce,'IMAGE_CLEANUP_OWNERSHIP_MISMATCH')
    client.run('image','rm',tag)
    return not client.run('image','ls','--quiet','--filter','reference='+tag)
