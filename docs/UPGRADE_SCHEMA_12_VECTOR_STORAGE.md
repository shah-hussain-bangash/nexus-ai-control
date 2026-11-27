# Schema-12 upgrade boundary

This source requires database schema **12**. The running local pilot currently
uses schema 11; this PR does not update its source, database, credentials or
processes. Merging, migration and restart are separate maintenance decisions.
Development migration/recovery checks use disposable synthetic databases only.

Schema 12 adds `neural_indexes` and `neural_vectors`, including scoped owner,
document and snapshot constraints. No existing account, password, source or
business record is rewritten. Source edits/reader changes/deletion gain an atomic
active-vector invalidation hook. A current application must refuse older schema
startup until the explicit migration completes; it must not auto-seed a replacement
database to bypass that refusal.

For a later approved upgrade, review the combined source and CI first, then plan
a stopped API/worker window and a suitable recoverable backup under the approved
data/key scope. With the reviewed source and intended database explicitly selected,
the existing backend migration command is `python -m nexus.cli migrate` from the
backend directory. Use migration, not synthetic `init`, to preserve existing users.
Verify schema readiness and known records before restarting normal operation.
No command in this document has been run against the active pilot.

Tests verify a populated schema-11 upgrade, repeated migration, and rollback/retry
after an injected schema-12 failure. Failure rollback is not a schema downgrade.
After a successful upgrade, older schema-11 source will refuse the newer database;
simply switching source branches is not a recovery plan. Real backup/restore and
cutover remain outside the currently selected synthetic-only recovery scope.

Historical schema-11 reports remain historical evidence. Current workflow exports
and readiness checks report the current schema; offline file integrity checks do
not establish that a restored application or stored index functions correctly.
