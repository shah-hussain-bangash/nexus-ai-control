# Phase 1: persisted session context and client reset foundation

This increment adds schema 10 session context metadata and client stale-response
protection. Source version remains 0.16.2 pending a formal release. It does not
enable production selection, environment activation or complete Phase 1.

## Server contract

`session_runtime_contexts` is an additive table keyed to the existing session,
with user/workspace, environment, positive revision and a separate public binding
identifier. The identifier is not a credential or the session-cookie hash.
Deleting a session cascades to its context. Session issuance creates both records.

Migration 9 to 10 preserves all existing tables and credentials. Existing sessions
whose user exists receive staging metadata at revision 1; no user, membership,
password, CSRF value or expiry is rewritten, and no membership is granted.
Orphan sessions remain invalid. Missing, malformed or non-staging stored context
fails closed; authentication never silently recreates or downgrades it.

`GET /v1/me` adds `runtime_context`; `GET /v1/session-context` returns the same
public context after authentication and membership validation. The existing
`GET /v1/runtime-context` compatibility response is unchanged.

Runtime requests may supply both `X-Nexus-Context-ID` and
`X-Nexus-Context-Revision`. Malformed/partial/duplicate pairs are rejected;
mismatches return `STALE_SESSION_CONTEXT`. Existing clients without these headers
remain compatible with their stored staging context. Header selectors never
override server session state.

`POST /v1/session-context/select` requires CSRF, workspace/environment and expected
binding/revision. It acknowledges the current staging context without changing its
revision. A stale expectation, other workspace or non-staging target is rejected,
even when the user has a Preparing assignment. This is a contract foundation,
not an activation/switching endpoint.

## Client contract

The API client pins runtime requests to the discovered environment, binding and
revision. Discovery remains unpinned so it can refresh stale session metadata.
An in-memory context epoch rejects a response from an earlier context. Certain
authentication, membership and stale-context errors invalidate the current context
and CSRF token; sign-out does likewise.

The entire workspace view is keyed by this epoch. A changed session binding,
identity, environment or revision remounts root and child state, clearing loaded
results, forms, selections, modal state and component caches. Repeated discovery
of the same context does not reset the view. Window focus/visibility discovers
session changes made in another tab. Server checks still enforce authorization;
this is not an instant cross-tab broadcast or cancellation of committed work.

Existing persistent recovery records remain untouched. Unacknowledged governed
action keys are retained in a separate in-memory registry keyed by
workspace/user/environment, so a context-driven view reset does not create a
duplicate intent on return to that scope. They are not shared with another actor
or environment. This registry does not add reload persistence or replay an action.

## Validation and deployment

- Full Windows backend regression: 440 passed, 20 service/platform skips.
- Fourteen new backend cases cover current/no-op selection, revision/header
  validation, blocked production selection, invalid stored state, logout cascade,
  migration preservation and retained revoked access.
- Seventy-one frontend cases pass, including epoch changes, invalid discovery,
  pinned requests, late responses and scoped uncertain-action keys; build passes.
- Disposable browser QA verified sign-in, reload, workspace refresh and sign-out.
  Live accounts, data and credentials were not used for QA.
- Require backend, PostgreSQL, frontend and policy GitHub checks before applying.

Stop idle API/worker processes and take a private schema 9 backup first. Update
source, run `python -m nexus.cli migrate` from the backend with its configured
environment, rebuild the frontend, and restart. Verify schema 10 readiness,
preserved legacy tables/configuration and matching staging metadata for existing
sessions. The migration is forward-only; rollback needs a compatible source and
the private pre-upgrade backup, not just a source downgrade.

## Remaining prerequisites

Design handoffs and other persistent client namespaces still need environment
review. Cross-environment idempotency constraints, activation/provisioning,
revision-changing selection with atomic concurrency rules, workers and remaining
service/raw-query paths need final acceptance before public switching. Preserve
the shared inference budget/admission contract. Preparing environments still
provide no runtime access, and the workspace lifecycle delivery gate stays open.
