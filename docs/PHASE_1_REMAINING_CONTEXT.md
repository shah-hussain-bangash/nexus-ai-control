# Phase 1: readiness, interface examples and identity context integrity

This increment propagates the bound context through the remaining fixed-staging
readiness/interface queries and prevents authentication from silently retargeting
an already-bound operation. Public runtime access remains staging-only; it does
not add session selection or activate another environment. Source/schema remain
0.16.2/9, and Phase 1 remains incomplete.

## Implemented

- Readiness evidence lookup, creation and versioned update use the bound
  workspace/environment. The report helper requires either a binding or an
  explicit environment; an argument cannot override an existing binding. Evidence
  and accepted counts from one context do not certify another context.
- Source-defined delivery gates are unchanged. An attestation still cannot mark
  missing workspace lifecycle software as implemented or certify production.
- Interface example creation and deduplication use the current context. Example
  assets and revision snapshots explicitly copy that environment, so starter
  examples and subsequent workbench history/editing remain independent.
  The static interface catalog remains shared source metadata behind sign-in.
- Human session authentication, session issuance and workload authentication check
  an existing internal binding against the authenticated identity before issuing
  credentials or replacing that binding. A mismatch returns
  `IDENTITY_CONTEXT_CHANGED` without retargeting the operation. Missing/invalid
  credentials, CSRF and membership checks retain their existing behavior.
- Fresh operations and matching staging bindings continue to work. Current
  sessions are neither revoked nor changed by deployment of this increment.

## Boundaries and next work

Internal context binding is propagation, not runtime authorization. Synthetic
production tests do not grant production access or bypass the staging-only gate.
The absence of known literal staging resource queries does not prove every raw
query, cached result, export, client cache or external integration is isolated.

Schema 9 human sessions still identify a user and carry no selected environment
or context revision. A future selector needs an explicit server-side selection
contract, membership/active-state validation, stale request and response handling,
CSRF protection, session/worker checks and client cache resets. Request headers
must not become a substitute for that contract. Cross-environment runtime key
constraints still require review/migration before switching. Shared inference
spending/admission limits must remain shared as documented in
`PHASE_1_INFERENCE_CONTEXT.md`.

Client design handoffs and root caches, activation/provisioning, remaining raw SQL
and service paths, and schema changes remain separate increments. No environment
selector or preparing-to-active operation is introduced here.

## Validation and application

Twelve new cases cover readiness evidence/version isolation, explicit helper
context, independent interface examples/revisions/edits, conflicting human,
issuance and workload bindings, compatible current sessions, and retained public
staging restrictions. Existing interface, readiness, runtime access and OIDC
security tests pass. Require the full backend regression and all four GitHub
checks before applying.

Stop idle API/worker processes, take a private backup, update source and restart.
No frontend rebuild, migration, password reset or assignment edits are needed.
Verify readiness, protected endpoints and preserved accounts, sessions, records
and private configuration after restart.
