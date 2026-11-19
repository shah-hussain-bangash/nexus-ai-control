# Phase 1: workbench and persistent workflow context

This increment propagates the bound workspace/environment through design assets,
local previews and persistent workflows. Public sign-in, requests and worker
authorization remain staging-only. It does not activate environments, add a
selector or complete Phase 1. Source/schema remain 0.16.2/9.

## Implemented

- Asset lookup, listing, creation, revisions, history, validation, editing,
  archiving, starter deduplication and preview receipts use the bound environment.
  The workbench reports the current schema constant instead of the old value 8.
- Preview and snapshot helpers reject cached assets outside the active user's
  workspace/environment. Workflow references retain their type/status/version
  checks within that context. Knowledge corpora, benchmarks and fallback guardrail
  sets use that same context; provider inference's existing retrieval caller
  inherits this shared helper change without enabling production inference.
- Unbound internal knowledge retrieval must supply an explicit environment.
  Context binding alone grants no asset or runtime authorization.
- Persistent workflow admission, quotas, idempotency lookup, listing, recovery,
  control and review use the bound environment. Runs and steps explicitly inherit
  it. Step lookup, serialization and cancellation check persisted provenance,
  including when invoked by an unbound background worker.
- Cancellation checks the linked action's workspace/environment before touching
  it or its approvals. A foreign or missing linked action returns ACTION_MISSING
  and leaves that action and the requesting run unchanged.
- Worker claim, continuation and error handling keep the claimed workspace and
  environment. Agent lookup uses the run context. Existing requester/agent-owner
  membership, generation, destination and governed dispatch checks stay in place.

## Boundaries and remaining work

Synthetic production contexts in isolated tests verify propagation only. Real
requests cannot select production, and workers cannot execute new production
steps. Already-submitted action reconciliation retains its existing behavior;
this update does not add arbitrary workflow effects or model planning.

Schema 9 still makes workflow keys unique by workspace/author/key, without an
environment component. Receipt lookups cannot expose another context, but key
collisions across contexts still require schema/admission review before switching.
Existing global worker maintenance remains intentionally unbound and uses stored
provenance. Raw SQL and maintenance fixtures are outside ORM context enforcement.

Inference accounting/admission is covered by `PHASE_1_INFERENCE_CONTEXT.md`.
Runtime activation/session selection, remaining resource paths and root client
caches need review before an environment selector.
Workbenches retain their existing workspace role model; this is not new per-asset
sharing or a new history-retention/erasure policy.

## Validation and application

Nine new cases cover internal production asset lifecycle/history, per-context
starter idempotency, references/retrieval/guardrails, cached foreign previews,
workflow creation/recovery/control, the worker production gate, cross-context
action cancellation, a relabelled claim, and retained public staging restrictions.
Existing workbench, persistent workflow and inference tests pass. Require full
backend regression and all four GitHub checks before merging/applying.

Stop idle API/worker processes, take a private backup, update reviewed source and
restart. Verify readiness, unchanged accounts/records/configuration and protected
routes. No migration, password reset or assignment edits are needed from schema 9.
