"""Loopback-only development launcher: python -m nexus.local."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import uvicorn
from .config import Settings


def enable_console_interrupts():
    """Undo Windows' inherited ignore-Ctrl+C flag before starting the worker."""
    if os.name != 'nt':
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetConsoleCP.restype = wintypes.UINT
    if not kernel.GetConsoleCP():
        return  # A background process without a console has no console events.
    kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
    if not kernel.SetConsoleCtrlHandler(None, False):
        raise ctypes.WinError(ctypes.get_last_error())


def bind_listener(port=None):
    """Retain the bound socket so another process cannot claim a chosen free port."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(('127.0.0.1', 8000 if port is None else port))
        except OSError:
            if port is not None: raise
            listener.bind(('127.0.0.1', 0))
        return listener
    except BaseException:
        listener.close()
        raise


def stop_worker(worker):
    if worker.poll() is None:
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Start the local API and worker together. Keep this terminal open.')
    parser.add_argument('--port', type=int, help='Fixed port, or 0 for an available port. Default: 8000 if free, otherwise an available port.')
    args = parser.parse_args(argv)
    if args.port is not None and not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    os.chdir(Path(__file__).resolve().parent.parent)
    settings = Settings.from_env()
    settings.validate()
    if settings.mode != 'local':
        parser.error('This launcher is for NEXUS_MODE=local. Use your reviewed deployment process for pilot mode.')
    if not (Path(settings.frontend_dir) / 'index.html').is_file():
        parser.error('Build the frontend first: cd frontend && npm ci && npm run build')
    try:
        listener = bind_listener(args.port)
    except OSError:
        parser.error('Cannot bind this port. Choose --port 0 or another available local port.')
    port = listener.getsockname()[1]
    os.environ['NEXUS_ORIGIN'] = f'http://127.0.0.1:{port}'
    print(f'Starting NEXUS at: {os.environ["NEXUS_ORIGIN"]}', flush=True)
    print('API and execution worker share this terminal. Press Ctrl+C to stop both.', flush=True)
    worker = None
    done = threading.Event()
    try:
        enable_console_interrupts()
        worker = subprocess.Popen([sys.executable, '-m', 'nexus.worker'], cwd=Path.cwd(), env=os.environ.copy())
        server = uvicorn.Server(uvicorn.Config('nexus.main:app', host='127.0.0.1', port=port))
        def supervise():
            while not done.wait(1):
                if worker.poll() is not None:
                    print('Execution worker stopped; shutting down the local API. Check the terminal error before restarting.', flush=True)
                    server.should_exit = True
                    return
        threading.Thread(target=supervise, daemon=True).start()
        server.run(sockets=[listener])
        return 0 if server.started and worker.poll() is None else 1
    except KeyboardInterrupt:
        return 130
    finally:
        done.set()
        if worker is not None: stop_worker(worker)
        listener.close()


if __name__ == '__main__':
    sys.exit(main())
