"""Operator-only bounded secret-file inputs. Paths never come from request bodies."""
import os
import re
import stat
from pathlib import Path

MAX_BYTES=16384
STARTUP_SECRETS={
    'secret':'Session signing',
    'agent_secret':'Workload signing',
    'oidc_client_secret':'SSO client',
    'metrics_token':'Metrics authentication',
}


class SecretInputError(RuntimeError):
    def __init__(self):super().__init__('Configured secret input is unavailable, ambiguous or invalid.')


def source(name):
    direct=bool(os.environ.get(name,''));mounted=bool(os.environ.get(name+'_FILE',''))
    return 'ambiguous' if direct and mounted else 'file' if mounted else 'environment' if direct else 'not_configured'


def read_secret(name):
    """Resolve one server-owned variable; reject ambiguity rather than choosing a key."""
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',name) or name.endswith('_FILE'):raise SecretInputError()
    mode=source(name)
    if mode=='ambiguous':raise SecretInputError()
    if mode=='not_configured':return ''
    try:
        if mode=='environment':value=os.environ[name];raw=value.encode('utf-8')
        else:
            path=Path(os.environ[name+'_FILE'])
            if not path.is_absolute():raise SecretInputError()
            before=path.lstat()
            if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or getattr(before,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):raise SecretInputError()
            if not 0<before.st_size<=MAX_BYTES:raise SecretInputError()
            flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
            with os.fdopen(os.open(path,flags),'rb') as stream:
                opened=os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode) or (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino):raise SecretInputError()
                if not 0<opened.st_size<=MAX_BYTES:raise SecretInputError()
                raw=stream.read(MAX_BYTES+1)
                after=os.fstat(stream.fileno())
                if len(raw)!=opened.st_size or len(raw)>MAX_BYTES or (opened.st_size,opened.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise SecretInputError()
            if raw.endswith(b'\r\n'):raw=raw[:-2]
            elif raw.endswith(b'\n'):raw=raw[:-1]
            value=raw.decode('utf-8')
        if not 0<len(raw)<=MAX_BYTES or value.startswith('\ufeff') or any(ord(c)<32 or ord(c)==127 for c in value):raise SecretInputError()
        return value
    except (OSError,UnicodeError,KeyError,ValueError):raise SecretInputError() from None


def descriptor(settings):
    startup=[]
    for field,label in STARTUP_SECRETS.items():
        origin=settings._secret_input_sources.get(field)
        if origin is None:origin='supplied_at_startup' if getattr(settings,field) else 'not_configured'
        startup.append({'name':label,'source':origin,'reload':'restart required'})
    provider_names={name[:-5] if name.endswith('_FILE') else name for name in os.environ
        if re.fullmatch(r'NEXUS_PROVIDER_[A-Z0-9_]{1,48}(?:_FILE)?',name)}
    counts={mode:0 for mode in ('environment','file','ambiguous','not_configured')}
    for name in provider_names:counts[source(name)]+=1
    return {'startup_inputs':startup,'provider_input_counts':counts,
        'business_input':{'enabled':settings.business_connector=='http','source':source(settings.business_token_env) if settings.business_connector=='http' else 'not_used'},
        'boundary':'Source configuration only; no secret file is opened by this view. No values, paths or provider variable names are returned. Provider/business credentials are resolved before dispatch; inference rechecks at admission. Core authentication inputs require restart. Mounted files do not establish vault custody, rotation acceptance or deployment egress isolation.'}


def register_secret_inputs(app,factory,settings,human):
    from fastapi import Request
    @app.get('/v1/secret-inputs')
    def inspect(request:Request):
        with factory() as db:
            human(request,db,False,'members');return descriptor(settings)
