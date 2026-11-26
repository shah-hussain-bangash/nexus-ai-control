"""Real Windows console delivery, scoped to a newly created disposable console."""
import ctypes as c
from ctypes import wintypes as w
import os
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest
from conftest import identifiers
from test_local_runtime import build_stub

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Native Windows console acceptance')


class Entry(c.Structure):
    _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',c.c_size_t),
        ('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),
        ('flags',w.DWORD),('exe',w.WCHAR*260)]


def kernel():
    k=c.WinDLL('kernel32',use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
    k.Process32FirstW.argtypes=[w.HANDLE,c.POINTER(Entry)]
    k.Process32NextW.argtypes=[w.HANDLE,c.POINTER(Entry)]
    k.CloseHandle.argtypes=[w.HANDLE]
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    k.GetExitCodeProcess.argtypes=[w.HANDLE,c.POINTER(w.DWORD)]
    k.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
    k.AttachConsole.argtypes=[w.DWORD]
    k.GetConsoleProcessList.argtypes=[c.POINTER(w.DWORD),w.DWORD]
    k.SetConsoleCtrlHandler.argtypes=[c.c_void_p,w.BOOL]
    k.GenerateConsoleCtrlEvent.argtypes=[w.DWORD,w.DWORD]
    return k


def descendants(k,root):
    snapshot=k.CreateToolhelp32Snapshot(2,0)
    assert snapshot not in (None,c.c_void_p(-1).value)
    try:
        entry=Entry();entry.size=c.sizeof(entry);parents={}
        more=k.Process32FirstW(snapshot,c.byref(entry))
        while more:
            parents[entry.pid]=entry.parent
            more=k.Process32NextW(snapshot,c.byref(entry))
    finally:k.CloseHandle(snapshot)
    owned={root}
    while True:
        extra={pid for pid,parent in parents.items() if parent in owned}
        if extra<=owned:return owned
        owned|=extra


def alive(k,handle):
    code=w.DWORD()
    assert k.GetExitCodeProcess(handle,c.byref(code))
    return code.value==259


def send_owned_ctrl_c(root,owned,tmp_path):
    # Attach/detach changes standard console handles. Keep it out of pytest's
    # process so subsequent tests retain their original runner handles.
    controller=tmp_path/'console_controller.py'
    controller.write_text('''import ctypes as c,json,os,sys,time
from ctypes import wintypes as w
k=c.WinDLL('kernel32',use_last_error=True)
k.AttachConsole.argtypes=[w.DWORD]
k.GetConsoleProcessList.argtypes=[c.POINTER(w.DWORD),w.DWORD]
k.SetConsoleCtrlHandler.argtypes=[c.c_void_p,w.BOOL]
k.GenerateConsoleCtrlEvent.argtypes=[w.DWORD,w.DWORD]
owned=set(json.loads(sys.argv[2]))
k.FreeConsole()
assert k.AttachConsole(int(sys.argv[1]))
try:
    ids=(w.DWORD*32)();count=k.GetConsoleProcessList(ids,32)
    assert 0<count<=32
    assert set(ids[:count])<=owned|{os.getpid()}
    assert k.SetConsoleCtrlHandler(None,True)
    assert k.GenerateConsoleCtrlEvent(0,0)
    time.sleep(.25)
finally:k.FreeConsole()
''',encoding='utf-8')
    result=subprocess.run([sys.executable,'-I',str(controller),str(root),json.dumps(sorted(owned))],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert result.returncode==0,'Owned console signal controller failed'


@pytest.mark.parametrize('inherited_ignore',[False,True])
def test_windows_ctrl_c_stops_api_and_worker_after_verified_action(ctx,tmp_path,inherited_ignore):
    assert ctx['settings'].database_url.startswith('sqlite')
    frontend=build_stub(ctx)
    backend=Path(__file__).resolve().parents[1]
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    origin='http://127.0.0.1:'+str(port)
    env={name:value for name,value in os.environ.items() if not name.startswith('NEXUS_')}
    for name in ctx['settings'].__dataclass_fields__:
        env['NEXUS_'+name.upper()]=str(getattr(ctx['settings'],name))
    env['NEXUS_FRONTEND_DIR']=str(frontend.resolve())
    env['NEXUS_ORIGIN']='http://127.0.0.1:1'
    # Set the inherited flag inside the new console, never in the caller's console.
    bootstrap=tmp_path/'console_bootstrap.py'
    bootstrap.write_text('import ctypes,sys\n'
        'sys.path.insert(0,sys.argv[1])\n'
        'from nexus.local import main\n'
        f'assert ctypes.WinDLL("kernel32").SetConsoleCtrlHandler(None,{inherited_ignore!r})\n'
        'raise SystemExit(main(["--port",sys.argv[2]]))\n',encoding='utf-8')
    startup=subprocess.STARTUPINFO()
    startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    log=tmp_path/'console.log';handles=[];k=kernel();proc=None
    with log.open('w',encoding='utf-8') as output:
        try:
            proc=subprocess.Popen([sys.executable,'-I',str(bootstrap),str(backend),str(port)],
                cwd=backend,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=output,
                creationflags=subprocess.CREATE_NEW_CONSOLE,startupinfo=startup)
            with httpx.Client(base_url=origin,trust_env=False,follow_redirects=False,timeout=2) as client:
                deadline=time.monotonic()+30
                while True:
                    assert proc.poll() is None,'Owned launcher exited during startup'
                    try:
                        if client.get('/health/ready').status_code==200:break
                    except httpx.TransportError:pass
                    assert time.monotonic()<deadline,'Owned API readiness deadline'
                    time.sleep(.1)
                assert client.get('/v1/runtime').status_code==401
                login=client.post('/auth/local/login',headers={'Origin':origin},
                    json={'email':'owner@nexus.local','password':'Test-Only-Password-123!'})
                assert login.status_code==200
                agent,tool=identifiers(ctx,name='Supplier Scout',kind='supplier')
                action=client.post('/v1/console/actions',headers={'Origin':origin,
                    'X-CSRF-Token':login.json()['csrf'],'Idempotency-Key':'windows-console-action-0001'},json={
                    'agent_id':agent,'tool_id':tool,'request':{'action':'supplier:read','resource':'suppliers',
                    'arguments':{'supplier_id':'SUP-DEMO-104'}}})
                assert action.status_code==202
                deadline=time.monotonic()+30
                while True:
                    response=client.get('/v1/actions/'+action.json()['id'])
                    assert response.status_code==200
                    if response.json()['status']=='verified':break
                    assert time.monotonic()<deadline,'Owned worker verification deadline'
                    time.sleep(.1)
            owned=descendants(k,proc.pid)
            for pid in owned:
                handle=k.OpenProcess(0x1001,False,pid)
                if handle:handles.append(handle)  # Held handles prevent PID-reuse cleanup races.
            send_owned_ctrl_c(proc.pid,owned,tmp_path)
            proc.wait(timeout=15)
            deadline=time.monotonic()+5
            while any(alive(k,h) for h in handles) and time.monotonic()<deadline:time.sleep(.1)
            assert not any(alive(k,h) for h in handles),'Owned process survived Ctrl+C'
            with socket.socket() as probe:
                assert probe.connect_ex(('127.0.0.1',port))!=0
        finally:
            # Only new descendants of this still-owned launcher; never match by
            # name, kill a port owner or inspect operator configuration.
            if proc is not None and proc.poll() is None and not handles:
                for pid in descendants(k,proc.pid):
                    handle=k.OpenProcess(0x1001,False,pid)
                    if handle:handles.append(handle)
            for handle in reversed(handles):
                try:
                    if alive(k,handle):assert k.TerminateProcess(handle,1)
                finally:k.CloseHandle(handle)
            if proc is not None and proc.poll() is None:
                proc.terminate();proc.wait(timeout=10)
            time.sleep(.2)
