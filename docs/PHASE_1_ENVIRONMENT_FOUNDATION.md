# Phase 1, step 1 — workspace environment foundation

Candidate source: 0.16.1. Required schema: 9. This is the first Phase 1 increment,
not completion of workspace switching or a production release.

## Architecture decision

For this increment an existing organization is the workspace/tenant boundary.
The existing one-organization-per-user model is preserved. A separate nested
workspace/project hierarchy and cross-organization membership are deferred.

`workspace_environments` stores a name, immutable key, preparation/archive state,
version and timestamps under each organization. `environment_assignments` stores
initial member assignments, with database foreign keys that reject assignments
to a user from another organization. Existing user roles remain authoritative;
this increment does not introduce independent per-environment roles.

## Implemented

- Schema 8 → 9 migration creates the registry and assignments without changing
  existing users, passwords, sessions or business records.
- Each existing organization receives a protected active `staging` record. Existing
  environment keys found in scoped data are registered as `preparing`; their original
  data stays in place. Only staging assignments are backfilled for existing users.
- New local/bootstrap/admin-provisioned users receive their staging assignment.
- Owner-only API: list environment records, register a preparing environment,
  archive/restore unused preparing records, and inspect assignments.
- Keys are scoped to the authenticated organization. Writes require CSRF, are
  audited, use organization write locking and enforce optimistic record versions.
- Staging cannot be archived. An environment containing scoped business or audit
  records cannot be archived through this inventory. At most 20 records are allowed.

## API

- `GET /v1/workspace-environments`
- `POST /v1/workspace-environments`: `key`, `name`, `note`
- `POST /v1/workspace-environments/{key}/control`: `command` (`archive` or `restore`),
  `expected_version`, `note`
- `GET /v1/workspace-environments/{key}/assignments`

These APIs are available to the owner role after migration. The interface is not
extended in this increment. Responses explicitly report `switching_enabled: false`;
new preparing environments do not activate new data access or execution routes.
There is no runtime environment-selection endpoint or assignment-editing endpoint.

## Upgrade plan — perform only during a separate maintenance step

1. Review and approve this source change. Keep private `.env` files and databases.
2. Stop all NEXUS API and worker instances using the database. Preserve the runtime
   configuration and make a quiesced backup using the current source. Keep secrets
   and account databases outside GitHub; store backups privately.
3. Inspect the backup before updating the live working folder.
4. Update the source to 0.16.1. From `backend`, run the project virtual environment's
   `python -m nexus.cli migrate`. The migration refuses schemas newer than 9.
5. Start NEXUS, check readiness reports schema 9, sign in with the existing account,
   and verify the default staging registry and existing data.

Do not start 0.16.0 against schema 9. Rollback requires the old source plus a verified
pre-upgrade backup in an isolated restore procedure; copying old code alone is not
a database rollback. This implementation does not migrate the user's running database
as part of tests or PR preparation.

## Next Phase 1 increments

1. Define authenticated runtime context selection and membership lifecycle.
2. Replace fixed staging filters, propagate context through creation, audit, workers,
   cache/recovery keys, exports, approvals, inference and document search.
3. Add isolation and revocation regression tests for every resource and worker path.
4. Connect the owner controls and environment selector to the interface only after
   those server boundaries are enforced.

The complete workspace/environment lifecycle remains an open roadmap gate.

## Validation

The initial full Windows regression passed 303 tests with 18 service/platform skips.
After strengthening the migration fixture to also remove the new user/organization
index and adding capacity/concurrency cases, the targeted environment/PostgreSQL file
run passed 19 tests with 7 PostgreSQL-only skips. GitHub checks on this candidate are
the source of the final full-suite and PostgreSQL results.

Tests cover owner-only access, CSRF, tenant scoping, duplicate keys, stale versions,
archive/restore restrictions, capacity, cross-organization assignment rejection,
new-member staging assignment and preservation of accounts/sessions/legacy records.
The PostgreSQL suite adds simultaneous registration with exactly one winner.

The original `scripts/package_source.py` is an archived 0.16.0 release packager.
It now refuses to package this candidate against historical verification reports.
Use the reviewed GitHub source branch until release-specific packaging is prepared.
