"""Run the actual acceptance suite against an isolated, disposable PostgreSQL cluster.
Optional test dependency: pip install pgserver==0.1.4.
No Docker, privileged installer, production database URL or customer credentials are used.
"""
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    import pgserver
    binaries = Path(pgserver.__file__).parent / 'pginstall/bin'
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='nexus-pg-') as folder:
        folder = Path(folder); data = folder / 'data'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        subprocess.run([str(binaries/'initdb'), '-D', str(data), '-U', 'nexus_test', '-A', 'trust', '--no-locale', '--encoding=UTF8'], check=True, stdout=subprocess.DEVNULL)
        options = f"-h 127.0.0.1 -p {port} -c unix_socket_directories='' -F"
        started = subprocess.run([str(binaries/'pg_ctl'), '-D', str(data), '-l', str(folder/'postgres.log'), '-o', options, '-w', 'start'], stdout=subprocess.DEVNULL)
        if started.returncode:
            print((folder/'postgres.log').read_text()[-4000:], file=sys.stderr)
            raise RuntimeError('Disposable PostgreSQL startup failed; inspect the startup diagnostic above.')
        try:
            version = subprocess.check_output([str(binaries/'postgres'), '--version'], text=True).strip()
            print('Disposable test server:', version, flush=True)
            env = dict(os.environ, NEXUS_TEST_DATABASE_URL=f'postgresql+psycopg://nexus_test@127.0.0.1:{port}/postgres', NEXUS_TEST_ALLOW_SCHEMA_CREATE='1')
            command = [sys.executable, '-m', 'pytest', '--junitxml=../docs/postgresql-test-results.xml', *sys.argv[1:]]
            result = subprocess.run(command, cwd=root/'backend', env=env)
            return result.returncode
        finally:
            subprocess.run([str(binaries/'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'], check=True, stdout=subprocess.DEVNULL)


if __name__ == '__main__': raise SystemExit(main())
