# Phase 1: inference context and shared workspace accounting

This increment separates runtime call records by environment while preserving
one workspace-wide spending allowance and admission limit. Public authentication
still permits staging only. It does not enable switching, connect a provider,
change configured limits, or complete Phase 1. Source/schema remain 0.16.2/9.

## Budget and admission contract

Schema 9 has one budget row per workspace/month. Its `env` column is legacy
metadata, not an independent allowance. Budget creation keeps staging metadata
for compatibility; existing rows are neither moved nor rewritten. Held and spent
amounts remain shared across all environments of the same workspace. Rate and
pending-dispatch limits likewise aggregate across that workspace. Environment
creation must not multiply these caps.

`inference_accounting.py` uses explicit Core table queries for these intentional
workspace-wide aggregates. Every helper first validates the bound context or
explicit persisted provenance. Every aggregate/update includes the workspace;
budget operations also include the month. These paths return no other
environment's call results. Do not replace them with bound ORM queries, which
would silently filter the shared ledger/counts by runtime environment.

Organization admission retains its transaction lock and atomic conditional budget
reservation. Settlement updates only the captured call's workspace/environment
and releases its recorded reservation from the shared ledger once. A missing or
insufficient held balance rejects settlement and rolls back both changes, rather
than creating a negative ledger. Ambiguous provider outcomes retain reservations
and are never automatically retried. Recorded prices remain operator estimates,
not a provider invoice or a provider-account spending cap.

## Runtime record and delivery contract

- Status reports shared budget/admission scope explicitly; call counts, records,
  history, recovery, replay and reconciliation use the current environment.
  Console labels identify workspace spending/limits as shared across environments.
- Model checks, current evidence retrieval and guardrails run in admission's
  context. Access is checked again after preparation before reserving/dispatching.
  A changed identity or environment blocks admission. This is a bounded admission
  cutoff, not a claim that authorization can undo an outbound provider request.
- Calls explicitly store their environment. Completion/uncertainty use captured
  workspace/environment and committed accounting precedes delivery authorization.
  A late context change withholds the answer without undoing incurred usage.
  A relabelled record cannot receive the captured result. Uncertainty cannot
  overwrite an independently reconciled record.
- Signed history cursors include environment alongside workspace/search/status.
  Old cursors without an environment remain valid only for staging until their
  existing expiration. Model-name searches use the same scoped asset corpus.

## Remaining scope

The schema 9 call key remains unique by workspace/key, without environment.
Scoped lookups do not return another context's receipt; cross-environment reuse
can still conflict at the database constraint. Review this and other runtime
idempotency constraints before switching; do not promise independent namespaces.

Activation/session selection, remaining resource paths, client root caches and
design handoffs still need review. The deliberate Core accounting paths do not
make arbitrary Core SQL safe; raw SQL and maintenance remain trusted operations.
Existing provider allowlists, secret references and output limits remain in force.

## Validation and application

Fifteen new cases cover shared spending under competing contexts, shared request
rate/concurrency counts, isolated receipts/reconciliation/history/model search,
legacy cursor compatibility, late delivery access, changed admission inputs,
inconsistent ledger rollback, retained reconciliation, separate organizations,
relabelled completion and public staging restrictions. All provider tests use
MockTransport; no paid request or live credential is needed.

Existing inference/history/access-revocation tests, frontend tests and build pass.
Require the full backend regression plus backend, PostgreSQL, frontend and policy
GitHub checks before applying. Stop idle processes, take a private backup, update
source and rebuild the frontend, then restart and verify readiness, protected
routes and preserved records/configuration. No migration or account changes are
needed from schema 9; live inference remains at the operator's existing setting.
