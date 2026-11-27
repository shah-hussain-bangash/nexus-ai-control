"""Shared workspace admission for direct search, stored-index build and query."""
from sqlalchemy import select
from .db import WorkbenchRun,now
from .runtime_context import runtime_environment
from .security import fail

BUILD_KIND='neural_index_build'
JOB_KIND='neural_index_job'
COLLECTION_KIND='neural_index_collection'
KINDS=('hybrid_search',BUILD_KIND,JOB_KIND,COLLECTION_KIND)


def admit(db,user):
    # Caller holds the same Organization row lock as receipt reservation.
    rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.org_id==user.org_id,
        WorkbenchRun.env==runtime_environment(db,user.org_id),WorkbenchRun.kind.in_(KINDS))).all()
    stamp=now()
    if len(rows)>=1000:fail(429,'SEARCH_HISTORY_CAPACITY','The workspace reached its bounded retrieval receipt limit.')
    if sum(r.created>stamp-60 for r in rows)>=30:fail(429,'SEARCH_RATE_LIMIT','The workspace reached 30 retrieval requests per minute.')
    for row in rows:
        if row.kind!=JOB_KIND and row.status=='processing' and row.created<stamp-120:
            row.status='interrupted';row.result={**row.result,'error_code':'SEARCH_INTERRUPTED'}
    if sum(r.status=='processing' for r in rows)>=2:fail(429,'SEARCH_CONCURRENCY_LIMIT','Two retrieval operations are already running.')
