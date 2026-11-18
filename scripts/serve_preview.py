"""Optional managed preview entrypoint; normal users should use start.sh/start.ps1."""
import os
import argparse
from pathlib import Path
root = Path(__file__).resolve().parent.parent
python = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
os.chdir(root / 'backend')
parser = argparse.ArgumentParser(); parser.add_argument('--port', default=os.getenv('PORT', '3000')); parser.add_argument('--host', default='0.0.0.0')
args, _ = parser.parse_known_args()
os.environ["NEXUS_ORIGIN"] = "http://127.0.0.1:" + str(args.port)
os.execv(str(python), [str(python), '-m', 'uvicorn', 'nexus.main:app', '--host', args.host, '--port', args.port])
