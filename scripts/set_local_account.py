"""Change a local owner's login interactively without writing plaintext passwords."""
from getpass import getpass
from pathlib import Path
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from nexus.config import Settings
from nexus.db import SessionRecord, User, database
from nexus.security import password_hash
from nexus.service import audit


def update_owner(factory, settings, current_email, new_email, password=None):
    if settings.mode != 'local':
        raise ValueError('This command is for local development accounts only.')
    new_email = new_email.strip().lower()
    if not 5 <= len(new_email) <= 200 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', new_email):
        raise ValueError('Enter a valid email address of at most 200 characters.')
    if password is not None and not 12 <= len(password) <= 128:
        raise ValueError('Use a password of 12–128 characters.')
    try:
        with factory.begin() as db:
            user = db.scalar(select(User).where(User.email == current_email.strip().lower()).with_for_update())
            if not user or not user.active or user.role != 'owner':
                raise ValueError('The current email must belong to an active owner account.')
            if user.oidc_subject:
                raise ValueError('This account uses organization sign-in; update it through your identity provider.')
            if db.scalar(select(User.id).where(User.email == new_email, User.id != user.id)):
                raise ValueError('That email is already used by another account.')
            user.email = new_email
            if password is not None:
                user.password_hash = password_hash(password)
            db.execute(delete(SessionRecord).where(SessionRecord.user_id == user.id))
            audit(db, user.org_id, 'local-console', 'member.local_credentials_updated', detail={'member_id': user.id})
    except IntegrityError as exc:
        raise ValueError('That email is already used by another account.') from exc
    return new_email


def main():
    os.chdir(ROOT / 'backend')
    settings = Settings.from_env()
    settings.validate()
    if settings.mode != 'local':
        raise ValueError('This command is for local development accounts only.')
    engine, factory = database(settings.database_url)
    try:
        with factory() as db:
            owners = db.scalars(select(User).where(User.role == 'owner', User.active == 1)).all()
            default_email = owners[0].email if len(owners) == 1 else ''
        current = input(f'Current owner email [{default_email}]: ').strip() or default_email
        email = input(f'Your login email [{current}]: ').strip() or current
        password = getpass('New password (12–128 characters; hidden): ')
        if password != getpass('Confirm new password (hidden): '):
            raise ValueError('Passwords do not match. Nothing changed.')
        email = update_owner(factory, settings, current, email, password)
    finally:
        engine.dispose()
    print(f'Owner login updated to {email}. Refresh the app and sign in with your new credentials.')
    print('Workspace records are preserved. Previous sessions have been signed out.')
    print('This is your local app login; no email is sent and your email-provider password is not changed.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, EOFError, KeyboardInterrupt) as exc:
        print(str(exc) or 'Cancelled. Nothing changed.', file=sys.stderr)
        sys.exit(1)
