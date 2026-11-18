import argparse
import secrets
import os
from pathlib import Path
from sqlalchemy import select
from .config import Settings
from .db import database, migrate, Organization, User, Agent, Tool, Grant, Policy, uid, CURRENT_SCHEMA
from .environments import assign_staging
from .security import password_hash
from .schemas import SupplierArguments, PurchaseArguments


def seed(factory, password):
    with factory.begin() as db:
        if db.scalar(select(User).limit(1)): return False
        db.add(Organization(id='northstar', name='Northstar Operations'))
        people = [('owner', 'Alex Morgan', 'owner@nexus.local'), ('approver', 'Sam Taylor', 'reviewer@nexus.local'), ('auditor', 'Jordan Lee', 'auditor@nexus.local')]
        owner = None
        users = []
        hashed = password_hash(password)
        for role, name, email in people:
            u = User(id=uid(), org_id='northstar', name=name, email=email, role=role, password_hash=hashed); db.add(u)
            users.append(u)
            if role == 'owner': owner = u
        db.add(Policy(org_id='northstar', version=1))
        supplier = Tool(id=uid(), org_id='northstar', name='Supplier directory', kind='supplier', risk='low', schema_json=SupplierArguments.model_json_schema())
        purchase = Tool(id=uid(), org_id='northstar', name='Purchase requests', kind='purchase', risk='high', schema_json=PurchaseArguments.model_json_schema())
        db.add_all([supplier, purchase]); db.flush()
        agents = [Agent(id=uid(), org_id='northstar', name='Procurement Atlas', owner_id=owner.id, framework='Python SDK', risk='high', status='active'),
                  Agent(id=uid(), org_id='northstar', name='Supplier Scout', owner_id=owner.id, framework='Python SDK', risk='low', status='active'),
                  Agent(id=uid(), org_id='northstar', name='Operations Copilot', owner_id=owner.id, framework='Custom adapter', risk='medium', status='draft')]
        db.add_all(agents); db.flush()
        for a, t, scope in [(agents[0], supplier, 'supplier:read'), (agents[0], purchase, 'purchase:create'), (agents[1], supplier, 'supplier:read')]:
            db.add(Grant(org_id='northstar', agent_id=a.id, tool_id=t.id, scope=scope))
        for user in users:assign_staging(db,user)
    return True


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('operation', choices=['init', 'migrate', 'create-user', 'maintenance', 'backup', 'inspect-backup', 'backup-encrypted', 'inspect-encrypted-backup', 'bootstrap', 'set-local-password'])
    parser.add_argument('--oidc-subject', help='Optional trusted IdP subject to bind before first SSO login')
    parser.add_argument('--apply', action='store_true', help='Apply expired-record cleanup; maintenance defaults to dry-run')
    parser.add_argument('--destination')
    parser.add_argument('--quiesced', action='store_true')
    parser.add_argument('--organization', default='Enterprise workspace')
    parser.add_argument('--email'); parser.add_argument('--name', default='Workspace member')
    parser.add_argument('--role', choices=['owner', 'approver', 'security', 'engineer', 'auditor'], default='engineer')
    args = parser.parse_args()
    if args.operation == 'init' and os.getenv('NEXUS_MODE', 'local') != 'local': parser.error('Synthetic init is local-only. Use migrate then bootstrap for pilot deployments.')
    if args.operation == 'init' and not Path('.env').exists():
        content = f'NEXUS_SECRET={secrets.token_urlsafe(48)}\nNEXUS_AGENT_SECRET={secrets.token_urlsafe(48)}\nNEXUS_MODE=local\nNEXUS_POLICY_MODE=reference\n'
        Path('.env').write_text(content)
        if os.name != 'nt': os.chmod('.env', 0o600)
    settings = Settings.from_env(); settings.validate()
    if args.operation in ('backup-encrypted','inspect-encrypted-backup'):
        import json
        from .encrypted_backup import encrypted_backup,inspect_encrypted_backup
        if not args.destination:parser.error('--destination is required')
        print(json.dumps(encrypted_backup(settings,args.destination,args.quiesced) if args.operation=='backup-encrypted' else inspect_encrypted_backup(args.destination),indent=2))
        return
    if args.operation in ('backup', 'inspect-backup'):
        import json
        from .backup import backup, inspect_backup
        if not args.destination: parser.error('--destination is required')
        print(json.dumps(backup(settings,args.destination,args.quiesced) if args.operation=='backup' else inspect_backup(args.destination),indent=2))
        return
    if settings.database_url.startswith('sqlite:///'): Path(settings.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
    engine, factory = database(settings.database_url); migrate(engine, factory)
    if args.operation == 'maintenance':
        import json
        from .operations import housekeeping
        print(json.dumps(housekeeping(factory, apply=args.apply), indent=2))
    elif args.operation == 'init':
        password = secrets.token_urlsafe(16)
        if seed(factory, password):
            print('Local synthetic workspace initialized. Save these temporary development credentials privately:')
            print('Users: owner@nexus.local | reviewer@nexus.local | auditor@nexus.local')
            print('Generated development password: ' + password)
        else: print('Workspace already initialized. Existing accounts were not changed.')
    elif args.operation == 'bootstrap':
        if not args.email or not args.oidc_subject or not settings.oidc_issuer: parser.error('Bootstrap requires --email, --oidc-subject and configured OIDC issuer.')
        with factory.begin() as db:
            if db.scalar(select(Organization).limit(1)) or db.scalar(select(User).limit(1)): parser.error('Bootstrap requires an empty database; existing organizations are preserved.')
            db.add(Organization(id='northstar',name=args.organization));db.flush()
            user=User(org_id='northstar',email=args.email.lower(),name=args.name,role='owner',password_hash=password_hash(secrets.token_urlsafe(48)),oidc_subject=settings.oidc_issuer.rstrip('/')+'|'+args.oidc_subject)
            db.add(user);db.flush();assign_staging(db,user)
            db.add(Policy(org_id='northstar',version=1))
        print('Organization and OIDC-bound owner provisioned. No synthetic tools, agents or shared passwords were created.')
    elif args.operation == 'set-local-password':
        from getpass import getpass
        from .membership import reset_local
        if settings.mode!='local' or not args.email:parser.error('Use --email and local development mode only.')
        password=getpass('New local password (12–128 characters): ')
        if password!=getpass('Confirm password: '):parser.error('Passwords do not match.')
        try:reset_local(factory,settings,args.email,password)
        except ValueError as exc:parser.error(str(exc))
        print('Local password updated; prior sessions revoked. Records preserved.')
    elif args.operation == 'create-user':
        if not args.email: parser.error('--email is required')
        password = secrets.token_urlsafe(16)
        with factory.begin() as db:
            if args.oidc_subject and not settings.oidc_issuer: parser.error('Configure NEXUS_OIDC_ISSUER before binding a subject')
            subject = settings.oidc_issuer.rstrip('/') + '|' + args.oidc_subject if args.oidc_subject else None
            user=User(org_id='northstar', email=args.email.lower(), name=args.name, role=args.role,
                        password_hash=password_hash(password), oidc_subject=subject)
            db.add(user);db.flush();assign_staging(db,user)
        print('User provisioned. Temporary local password: ' + password)
    else: print(f'Schema is at version {CURRENT_SCHEMA}.')


if __name__ == '__main__': main()
