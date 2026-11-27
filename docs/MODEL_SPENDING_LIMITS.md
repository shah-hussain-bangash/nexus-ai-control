# Owner-managed model-route spending ceilings

This development increment adds enforced monthly model-route ceilings to normal
inference admission and the AI FinOps dashboard. It builds on PR #94, reuses
schema-12 records and adds no migration. Existing installations have no new
restriction until an owner saves a policy. This change does not enable inference,
raise an operator budget, provision credentials or alter the running application.

## Scope and enforcement

A policy applies to one workspace/environment. It may assign integer micro-USD
ceilings to up to 100 model asset IDs. Each ceiling is monthly, supports 0–1,000,000
USD, and continues across versions/configuration changes of that asset. It does
not aggregate separate assets merely because they share a physical provider account.

Optional **Require an assigned cap for every new model request** blocks unassigned
routes, including newly created/cloned model assets. Without this option, routes
without caps retain the existing server/workspace controls. Zero is an explicit
cap rather than an unassigned field. It permits zero-reservation local calls when
recorded spend/holds are also zero; it is not a model execution off switch.

The existing admission transaction already locks the organization and workspace
budget. After flushing the new pending call, the model gate counts that period's
completed/reconciled charges plus pending/unknown reservations, including the new
row. If the route ceiling would be exceeded, the whole transaction rolls back
before provider dispatch, including the new call and reservation. Existing
workspace-wide budget, traffic, model validation, guardrail, source-access and
operator execution gates continue to apply. A larger route cap cannot raise the
server/workspace limit. Spending from another environment does not enter a route
ceiling, while the underlying workspace budget remains shared across environments.

Ceilings govern new admissions at the existing dispatch cutoff. Lowering a limit
does not cancel already admitted work, rewrite charges or release holds. Settlement
records actual reported token usage using its captured operator rates, even when
that exceeds an estimate/ceiling; future admissions then see the overrun. This is
not a hard guarantee about provider invoices or actual external spend. Hardware,
electricity and local embedding/reranking HTTP activity are not metered by this
InferenceCall-based control.

## Dashboard, versions and evidence

**Model-route monthly spending limits** shows current UTC accounting-month spend,
unresolved reservations, available route capacity and over-limit state. Aggregate
spent/held amounts are returned as decimal integer strings and formatted without
losing micro-units. Owner input uses exact decimal-to-micro-unit conversion.

Owners can save a complete reviewed policy with a reason and current policy/model
versions. Blank removes a cap; with required-cap mode enabled it blocks that route.
Archived routes cannot receive a new assignment; remove their cap explicitly from
the next revision. Current model versions must match at save time, but existing
caps remain attached across later versions. The owner can intentionally tighten or
remove limits without changing historical accounting.

Each save creates a versioned receipt and supersedes the previous effective
revision. The original policy payload is retained. Exact intent replay/recovery
returns that receipt, including a superseded revision, without reactivating it.
The dashboard reloads the current effective revision after recovery. Changed
payloads conflict; stale policy/model versions cannot overwrite newer choices.
History is bounded at 200 revisions per environment; further saves are rejected
without changing the current policy. No automatic deletion/retention policy is
introduced by this increment.

Creation requires owner `members` permission. Reading policy/usage/history requires
`export` permission, allowing authorized owner/security/auditor roles. Other roles
cannot edit policy through generic workbench routes; policy receipts are excluded
from generic workbench listings. The overview returns model identity/version and
cost metadata without model credentials, endpoint configuration, prompts, answers
or source text. A call's saved result retains the policy ID/version and applied
route-cap evidence through successful or uncertain completion and usage settlement.

## API

- `GET /v1/inference-spend-controls` — effective policy and current-environment
  monthly model-route usage; version zero means no policy is configured.
- `PUT /v1/inference-spend-controls` — owner saves a reviewed complete revision
  with an intent key, expected policy/model versions and note.
- `GET /v1/inference-spend-controls/history` — paginated scoped policy receipts.
- `POST /v1/inference-spend-controls/recover` — author's original change receipt.

Only policy/audit records are changed by these endpoints. Neither spending-control reads
nor policy saves invoke a provider, settle usage, modify an existing call charge,
or adjust the workspace budget ledger. Normal session/CSRF/runtime gates apply.

## Focused development checks

Disposable synthetic inference checks cover default compatibility, projected-cap
rejection before dispatch, rollback of attempted reservations, pending/uncertain
holds, overlapping admission, cap evidence through settlement, required unassigned
routes, model-version changes, lowering below usage, idempotent superseded receipt
recovery, owner/export permissions, tenant/environment isolation and precedence of
the workspace budget. Zero-dollar local Ollama behavior uses mock HTTP transport.
Frontend checks cover exact cap inputs, version pins, unassigned/zero semantics,
large aggregate formatting and isolated recovery scopes; the build is checked.

Full acceptance, physical provider-account aggregation, provider-verified billing,
retention policy, merging and deployment remain separate work. No active data,
credentials, runtime configuration or live provider/customer system was changed.
