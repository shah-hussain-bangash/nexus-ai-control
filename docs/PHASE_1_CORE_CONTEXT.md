# Phase 1: core server context propagation

This increment prepares shared server helpers for environment-aware operation.
Public sign-in, session authentication and workload authorization still permit
only staging. It does not enable switching, activate a Preparing environment or
complete the workspace lifecycle gate. Source/schema remain 0.16.2/9.

## Implemented

- Internal context binding accepts a validated workspace/environment pair. An
  absent binding is distinct from corrupt metadata; invalid metadata fails closed
  in ORM query and unit-of-work hooks.
- Shared record lookup and active-policy lookup use the bound environment. An
  unbound caller must supply an explicit environment; a caller cannot override a
  bound workspace or environment through a helper argument.
- Audit events use the bound context or explicit source provenance. Action-backed
  events must match the action's workspace/environment. Unbound events no longer
  silently default to staging. Sign-in and local account maintenance explicitly
  identify their staging audit ledger; provider completion/unknown events use the
  stored call's environment, including after access revocation.
- Business dispatch, durable tool lookup and approval lookup pass their persisted
  record context explicitly. Action submission reloads its agent within that
  workspace/environment and obtains the matching policy. Existing dispatch access
  and external-effect cutoff checks are preserved.
- New scoped ORM entities inherit the bound environment if omitted. Existing
  entities cannot change workspace/environment through a bound unit of work, even
  if a cached foreign entity is relabelled before a write or deletion.
- Session/settings/context responses report the bound environment. Policy
  activation reads its current policy from that same context.
- Per-workspace operating signals use the bound or explicitly supplied environment.
  Global operator metrics retain their separate token-protected, unbound query
  path. A bound session cannot silently pose as a global metrics session.

## Internal contract

`bind_runtime_context(db, org_id, environment='staging')` is a propagation helper,
not authorization. It is called only after the appropriate request/worker checks.
`runtime_environment(db, org_id, environment=None)` resolves the binding or requires
an explicit environment for unbound background/operator calls. The `audit`,
`scoped` and `active_policy` helpers follow this contract.

Use fresh sessions for independent operations. Do not change context while rows
from another context are awaiting flush. Do not manually clear a binding by
assigning invalid metadata. Raw/Core SQL, ORM bulk update values, identity-map
reads and intentionally unbound maintenance still need explicit scope review;
these hooks are not database row-level security or a sandbox for arbitrary code.

## Remaining scope

Document/search/ingestion propagation is covered by the subsequent
`PHASE_1_DOCUMENT_CONTEXT.md` increment. Workbench and persistent workflow
propagation is covered by `PHASE_1_WORKBENCH_CONTEXT.md`.
Inference budgeting and admission need an explicit decision about workspace-wide
versus per-environment limits. Session selection, runtime activation, remaining
worker/resource propagation, root client caches and design handoffs must be
reviewed before any environment selector is enabled. Preparing assignments and
internal binding alone grant no new runtime access.

## Validation and application

- Final full Windows backend regression: 382 passed, 20 service/platform skips.
- New core cases cover bound versus explicit context, cached foreign lookups,
  environment-specific policies/audits/signals, corrupt context metadata, scope
  relabelling before writes/deletion, new-row defaults and retained public staging
  restrictions. Existing worker, durable, inference, membership and OIDC tests pass.
- PostgreSQL, frontend and policy checks run in GitHub CI. Local skips do not
  constitute PostgreSQL or production acceptance.

After review and successful checks, take a private backup, update source and
restart the API and worker. No schema migration or account/assignment edits are
required from schema 9. Validate readiness and the existing sign-in/context APIs
after restarting. Preserve private configuration and existing workspace records.
