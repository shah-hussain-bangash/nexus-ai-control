"""Create local Compose runtime secrets once. Never overwrite existing environment files."""
from pathlib import Path
import secrets
import os
root=Path(__file__).resolve().parent.parent
path=root/'.env'
if path.exists(): raise SystemExit('Root .env already exists; review it instead of overwriting it.')
path.write_text('\n'.join(f'{k}={secrets.token_urlsafe(48)}' for k in ['POSTGRES_PASSWORD','NEXUS_SECRET','NEXUS_AGENT_SECRET'])+'\n')
if os.name!='nt': os.chmod(path,0o600)
print('Local Compose secrets created. Run docker compose up --build. Initial development credentials appear in the init service log.')
