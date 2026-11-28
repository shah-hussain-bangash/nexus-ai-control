# Pause model routes on recorded unknown outcomes

Models/Usage includes an optional **Pause routes on recorded unknown outcomes**
panel. Owners can set per-route unknown-outcome limits; users with `export`
permission can inspect current counts and policy history. No policy is created by
default. Blank/unassigned routes retain existing runtime, traffic and budget controls.

A rule blocks a new inference admission when that model route has **at least** the
chosen number (1–100) of stored `unknown` outcomes in the current workspace and
environment. Counts include all authors, months and asset versions of the same
stable model ID. Replacing a route's configuration does not reset its unknown
history. A newly created route ID is unguarded until explicitly configured.

## Behavior and resolution

- A denied admission sends no provider request, creates no new inference receipt
  and commits no new budget reservation. Existing outcomes and held reservations
  remain intact. Existing concurrency, spending caps and server execution opt-ins
  still apply.
- Retrying an already committed inference intent returns its original outcome;
  it never dispatches again or gets blocked from receipt recovery by a newer rule.
- Owners can inspect and reconcile the original outcomes through the existing
  usage workflow. Reconciled calls stop contributing to the unknown count. If it
  falls below the threshold, a subsequent explicit request can be admitted.
- Owners can also explicitly change or remove a rule with a reason. This does not
  reconcile a call, settle charges, release reservations or change provider state.
- Only recorded `unknown` statuses count. Pending requests, including requests
  affected by a process interruption, retain the existing concurrency/reservation
  and reconciliation behavior. Completed/reconciled calls do not count.
- Already admitted calls may still finish or fail. This admission snapshot is not
  an atomic guarantee against overlapping provider failures. There are no automatic
  retries, fallback requests, cooldown probes, provider health checks, failover or
  cancellation of in-flight work.

The guard runs inside the existing workspace admission transaction. Denial rolls
back the new pending row and reservation. An admitted guarded call stores the
policy ID/version, limit and unknown count observed at admission. That context is
preserved alongside existing spending-control metadata through completion,
uncertain outcomes and owner reconciliation. Historical calls are not rewritten.

## Policy review and APIs

- `GET /v1/model-uncertainty-controls`: effective policy, current model metadata,
  unknown counts and blocked states. No answers, provider endpoints, credentials,
  pricing or private call IDs are returned.
- `PUT /v1/model-uncertainty-controls`: owner `members` permission, CSRF and an
  `Idempotency-Key`; body contains `expected_version`, `rules` and a visible
  10–1000 character `note`. Each rule pins `model_id`, current
  `expected_model_version` and strict integer `unknown_limit`. At most 100 unique
  routes can be configured. Remove archived/unavailable routes from a new policy.
- `GET /v1/model-uncertainty-controls/history`: `offset` and `limit` (default 20,
  maximum 50), with current export permission and environment membership.
- `POST /v1/model-uncertainty-controls/recover`: CSRF-protected own receipt lookup
  with `{ "key": "..." }`, using export permission.

All queries are scoped to the current workspace/environment. Model metadata and
policy versions are rechecked on save. A conflicting intent body fails. Exact
retries and recovery return their original policy receipt; a superseded revision
is never reactivated. Browser recovery stores only key/hash/timing, in a namespace
separate from spending controls and other users/environments.

Policy history is bounded to 200 revisions per environment. The final slot is
reserved for clearing all rules, so an enabled policy can still be turned off at
history saturation. Existing receipts are never silently deleted to make space.
The view supports up to 500 model records, including archived routes. Multiple
active policy records fail closed and require private operator integrity review.
The dashboard reloads current state explicitly; it does not claim continuous
provider monitoring.

Uses existing schema 12 storage; no migration, dependency, environment variable
or background worker is added. Limits attach to stable route IDs across versions;
re-review the route and limit when its purpose or provider configuration changes.

## Verification and remaining scope

Focused checks use disposable accounting rows and mock HTTP transport. They cover
blocked new requests without dispatch/reservation, retained inference replay,
reconciliation reopening, preservation of both control contexts, historical-period
counts, unrelated scopes/statuses/routes, stale models/policies, owner/CSRF rules,
receipt recovery and final-slot clearing. Existing inference, model spending and
runtime-environment checks remain part of focused validation.

This is operator-controlled containment of recorded uncertainty. It is not live
provider acceptance, provider-account reconciliation, automatic remediation,
streaming/failover acceptance or production certification. No actual provider call,
account, existing record, secret, live policy or running application is changed
by this development increment.
