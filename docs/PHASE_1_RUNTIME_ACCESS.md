# Phase 1, step 2 — current-environment access enforcement

Candidate: 0.16.2. Schema stays 9. This increment enforces the existing staging
boundary; it does not enable switching into preparing environments.

## Implemented boundaries

- Local/OIDC session issuance and authenticated requests require an active user,
  an active staging environment, and an explicit same-organization staging assignment.
  Login never recreates a removed assignment. Existing migrated members already have
  staging assignments from schema 9.
- Workload token authentication rechecks the workload owner's environment access.
- Authenticated sessions bind a workspace/staging context to ORM reads, ORM bulk
  updates/deletes and unit-of-work writes involving `Scoped` entities. Collection
  views and counts now exclude records in other environments even where an older
  endpoint had only an organization filter.
- Supported explicit context selectors are `X-Nexus-Workspace` and
  `X-Nexus-Environment`; query aliases are `workspace` / `org_id` and
  `environment` / `env`. They may only match the current identity's organization
  and `staging`. Conflicting selectors fail with 400, a foreign workspace with 403,
  and a non-staging environment with 409. Omitted selectors keep existing clients
  compatible. No selector is persisted as a session switch.
- `GET /v1/runtime-context` reports the authorized current context and
  `switching_enabled: false`.
- Business dispatch rechecks requester/workload-owner access and current requester
  operation permissions. Revoked access blocks new effects before connector invocation.
- Background audit events inherit their action/run/intake environment. A saved audit
  export with historical mixed-environment records is refused and must be regenerated.
  Durable reconciliation rejects links to an action in a different environment.
- Durable runs recheck author/owner access before advancing new steps. Existing action
  outcomes may still be reconciled; reconciliation does not authorize another effect.
- Intake checks requesting-author access before extraction and again before retaining
  an extraction result or publishing it. Late results after revocation are discarded.
- Hybrid search's existing post-compute authentication now includes environment access.
- Inference rechecks access at admission and before delivering its response. Completed
  provider usage is accounted for even if access is revoked during the call. Unknown
  provider outcomes retain their reservation; revocation never authorizes blind retries.

## Limits and dispatch cutoff

These guards are application authorization, not PostgreSQL row-level security. ORM
guards apply only after an authenticated context is bound; batch workers intentionally
start unbound and perform per-record authorization. Core/raw SQL requires explicit
organization/environment predicates. The owner's environment-inventory archive check
intentionally inspects whether another environment contains records without returning
those business records.

Revocation cannot undo data already delivered or an external request already dispatched.
Checks fence new work and response delivery at their documented boundaries, rather than
claiming cancellation of an external side effect. Keep the existing reconciliation flow
for uncertain outcomes.

The subsequent assignment-management increment is documented in
`PHASE_1_ENVIRONMENT_MEMBERSHIP.md`. Environment switching, per-environment roles, cross-workspace
membership, promotion and the environment selector remain future increments. Assignment
or environment corruption fails closed; use reviewed operator maintenance for repair,
never automatic enrollment on login. Do not remove the current owner's assignment as
an interactive test on the live workspace.

## Validation

- Initial full local Windows regression: 336 passed, 19 service/platform skips.
- After the audit-environment and historical-export fixes, the affected runtime,
  durable execution, intake and control-plane files passed 116 tests with 1 OCR skip.
- The expanded focused runtime-context suite includes collection/aggregate isolation,
  context conflicts, scoped ORM bulk writes, blocked cross-context inserts, session and
  workload revocation, business/durable dispatch fences, intake/search revocation, and
  provider-accounting behavior after successful or uncertain calls.
- Existing document and identity tests now explicitly provision staging assignments
  when constructing additional synthetic users directly in the database.
- Consult this candidate's GitHub checks for the final full-suite/PostgreSQL evidence.
  Local tests use disposable data; the running application's database is unchanged.

## Update from 0.16.1

After source merge approval, stop the current API/worker, update the working source,
and restart. No schema migration or account/password reset is required from schema 9.
Earlier schema-8 installations must first follow `PHASE_1_ENVIRONMENT_FOUNDATION.md`.
