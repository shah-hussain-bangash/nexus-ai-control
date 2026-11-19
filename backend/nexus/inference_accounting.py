"""Explicit workspace-wide aggregates; never returns another environment's calls.

Schema 9 has one budget per organization/month. Core table queries intentionally
avoid scoped ORM filters for these shared limits. Each entry point validates the
caller's bound context or explicit persisted provenance first. The budget's env
column is legacy metadata, not a separate environment allowance.
"""
import time
from uuid import uuid4
from sqlalchemy import select, update, func
from .db import InferenceBudget, InferenceCall
from .runtime_context import runtime_environment, CURRENT_ENVIRONMENT
from .security import fail


def workspace_budget(db,org,environment,period):
    runtime_environment(db,org,environment)
    ledger=InferenceBudget.__table__
    return db.execute(select(ledger).where(ledger.c.org_id==org,ledger.c.period==period)).first()


def ensure_budget(db,org,environment,period):
    runtime_environment(db,org,environment)
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    insert=sqlite_insert if db.bind.dialect.name=='sqlite' else pg_insert
    ledger=InferenceBudget.__table__
    db.execute(insert(ledger).values(id=uuid4().hex,org_id=org,env=CURRENT_ENVIRONMENT,created=time.time(),period=period,held=0,spent=0).on_conflict_do_nothing(index_elements=['org_id','period']))
    db.execute(select(ledger.c.id).where(ledger.c.org_id==org,ledger.c.period==period).with_for_update()).first()


def admission_counts(db,org,environment):
    runtime_environment(db,org,environment)
    calls=InferenceCall.__table__;stamp=time.time()
    recent=db.scalar(select(func.count()).select_from(calls).where(calls.c.org_id==org,calls.c.created>stamp-60))
    pending=db.scalar(select(func.count()).select_from(calls).where(calls.c.org_id==org,calls.c.status=='pending',calls.c.created>stamp-300))
    return recent,pending


def reserve_budget(db,org,environment,period,reserved,limit):
    runtime_environment(db,org,environment)
    ledger=InferenceBudget.__table__
    changed=db.execute(update(ledger).where(ledger.c.org_id==org,ledger.c.period==period,ledger.c.held+ledger.c.spent+reserved<=limit).values(held=ledger.c.held+reserved))
    if changed.rowcount!=1:fail(429,'MONTHLY_BUDGET_EXCEEDED','The monthly operator-priced budget has insufficient unreserved capacity.')


def settle_budget(db,row,charged):
    runtime_environment(db,row.org_id,row.env)
    ledger=InferenceBudget.__table__
    changed=db.execute(update(ledger).where(ledger.c.org_id==row.org_id,ledger.c.period==row.period,ledger.c.held>=row.reserved).values(held=ledger.c.held-row.reserved,spent=ledger.c.spent+charged))
    if changed.rowcount!=1:fail(409,'BUDGET_LEDGER_INCONSISTENT','The workspace reservation ledger needs operator review; no settlement was committed.')
