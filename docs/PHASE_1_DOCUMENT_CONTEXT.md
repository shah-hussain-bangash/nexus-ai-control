# Phase 1: document, search and ingestion context

This increment propagates the internal workspace/environment context through
document lifecycle, lexical and hybrid search, retrieval evidence, and file
intake. Public authentication and worker authorization still allow staging only.
There is no environment selector, runtime activation, schema migration or version
bump: source/schema remain 0.16.2/9. Phase 1 remains incomplete.

## Implemented

- Document reads, creation, replacement receipts, deletion, citations, provenance,
  capacity counts and recovery use the bound environment. Indexing copies the
  document environment explicitly into its chunks, including unbound internal
  calls with persisted provenance.
- ACL predicates check active user, workspace and environment before role/author
  permissions. Owner privileges cannot bypass the context check on cached rows.
- Lexical ranking excludes chunks from an obsolete document revision before
  scoring. Hybrid ranking retains its existing revision checks, uses the current
  context for admission/history/recovery, and revalidates actor, workspace and
  environment after computation before loading or delivering its result.
- Retrieval checks use the same corpus and context. Saved evidence revalidates
  its own context and every referenced source before returning queries/results.
- Intake listing, admission, recovery, control, publication and counts use the
  context. Publication explicitly copies the job environment into the source.
  Worker claim and completion match the persisted workspace/environment as well
  as the job and lease, preventing a late result from following a relabelled job.
  Existing requester/member authorization and expiry checks remain in place.

## Boundaries and remaining work

Internal context binding is propagation, not permission. Synthetic production
fixtures in tests do not enable production requests, membership or extraction.
ACL sharing still validates active organization users; sharing a source does not
grant environment membership or bypass request authorization.

Schema 9 document, update, retrieval-check and intake idempotency constraints are
still unique by workspace/author/key, without environment. Lookups cannot return
another environment's receipt; identical keys across environments can still hit
the existing database uniqueness constraint. Review/migrate these constraints
and concurrent admission handling before enabling switching. Do not claim
independent cross-environment idempotency namespaces yet.

Other workbench resources, inference budgets/admission, session activation,
remaining workers and root client caches still need review. A withheld late
search result leaves its original processing receipt for operator recovery; this
is not cancellation of already completed computation. Raw SQL and unbound
maintenance remain outside the ORM context guarantee.

## Validation and application

Eight focused tests cover synthetic production corpus/chunks, stale lexical
chunks, cached foreign rows, historical evidence/source checks, a context change
during hybrid computation, late intake completion, document lifecycle/recovery,
and the retained public staging restriction. Existing document, lifecycle,
hybrid and ingestion tests also pass. Full backend regression and PostgreSQL,
frontend and policy CI must pass before applying.

After successful checks, stop idle API/worker processes, take a private backup,
update source and restart. Verify readiness and preserved records/configuration.
No account, password or assignment changes are required.
