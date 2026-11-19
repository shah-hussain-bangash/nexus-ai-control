# Phase 1: environment-specific runtime request keys

Schema 11 adds environment to the database-enforced request namespace for durable
runs, knowledge documents, document updates, retrieval checks, ingestion jobs and
inference calls. Source version remains 0.16.2 pending a formal release. Public
runtime access remains staging-only; this does not activate environments or
complete Phase 1.

## Key and accounting contract

- The first five tables use `(org_id, env, author_id, idem_key)`; inference calls
  use `(org_id, env, key_hash)`. Reusing a key within the same namespace still
  replays its existing receipt or conflicts when its request fingerprint differs.
  A different environment can store its own request without returning the first
  environment's receipt.
- Existing row identifiers, raw keys, hashes, fingerprints, JSON receipts, file
  bytes, relationships and session credentials are preserved. Existing recovery
  lookups continue to resolve the same acknowledged records.
- Inference budget uniqueness remains `(org_id, period)`. Spending, held
  reservations, request-rate and pending-call limits remain workspace-wide.
  Adding an environment cannot create another budget allowance.
- Existing action request keys already included environment. Parent/child scope
  foreign keys and document chunk/workflow step identities remain unchanged.
  Local hybrid-search admission and other non-table intent formats still need
  final acceptance; this is not a claim that every possible intent is covered.

## Migration contract

PostgreSQL changes the relevant unique constraints within the existing advisory-
locked transaction. Source table metadata stays usable for later fresh database
creation in the same process. Existing data and dependent relationships remain.

SQLite uses a dedicated checked-out connection and explicit `BEGIN IMMEDIATE` so
DDL and the schema marker commit together. Foreign-key enforcement is disabled
only on that migration connection before the transaction, checked before any
rebuild, and restored on success or failure. A complete foreign-key check precedes
commit. API and worker processes must be stopped for this maintenance operation.

The SQLite rebuild copies every column without key/value transformations and
checks row counts. Known column order/types/nullability, primary key, foreign keys
and unique constraints are preflighted before changing a table. Explicit indexes
and triggers are preserved verbatim and are not replayed during data copying.
Unsupported custom columns/defaults/checks/foreign keys/uniqueness or SQLite views
require operator review. A remaining custom old-scope unique index fails final
verification and rolls the entire upgrade back. Nothing is silently dropped to
force a customized schema through this migration.

Fresh databases receive the new constraints directly. Existing schema 10
databases receive constraint changes plus schema marker 11. A failed migration
keeps the previous schema/data; repeated successful migrations make no further
record changes. Unknown newer schemas remain rejected.

## Validation and application

- Full Windows backend regression: 446 passed, 20 service/platform skips.
- Six new populated schema-10 tests cover preserved tables/receipts/sessions,
  all six namespace constraints and unchanged budget uniqueness, interrupted
  migration rollback, retained SQLite index/trigger behavior, custom-layout
  rejection and rollback when an old custom unique index remains.
- Existing synthetic inference tests now confirm that the same key can create
  independent calls in different internal environments while recovery remains
  scoped. Public non-staging selection is still rejected.
- A read-only preflight confirmed the supported layout of the six request tables
  in the local project before application. It changed no live records.
- Require all four GitHub checks, including the populated PostgreSQL migration
  and rollback paths, before applying. SQLite-specific cases are skipped there.

Stop idle API/worker processes and take a private schema 10 backup. Update source,
run the configured backend's `python -m nexus.cli migrate`, verify all existing
table contents and configuration against the backup, and restart. Confirm schema
11 readiness and that recovery still uses original receipts. No password reset,
session revocation, membership edits or frontend rebuild are needed.

This is a forward-only upgrade. A source downgrade alone is not rollback; use a
compatible source and the complete private pre-upgrade backup after stopping the
application. Activation/provisioning, atomic revision-changing selection and final
service/worker/isolation acceptance remain prerequisites for public switching.
