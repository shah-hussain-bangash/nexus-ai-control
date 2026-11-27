# Owner-entered billing statement comparison

This development increment adds a bounded comparison between manually entered USD
statement lines and recorded inference-call accounting. It builds on PR #93,
uses existing schema-12 workbench receipts and adds no migration. It does not
change provider pricing, recorded charges, budget reservations or running processes.

## Dashboard flow

Open **Compare a billing statement** in the live inference/AI FinOps console.
An owner supplies a reference, accounting month, evidence note and 1–50 selected
lines. Each line maps to one distinct local inference-call ID in the current
workspace/environment and UTC accounting month. Enter the statement's nonnegative
USD charge independently; optional input/output token counts and provider request
IDs are compared only when supplied. Do not enter API keys, credentials, prompts
or answers in references/notes.

The client converts decimal USD strings to integer micro-USD without floating-point
amount parsing. Up to six fractional digits and 1,000,000 USD per line are supported.
The server requires bounded integer micro-USD and token values and rejects duplicate
local-call mappings/line references, unsupported currencies and invalid months.
Charges split across multiple provider lines must be combined into one selected
call line before comparison. Credits, taxes, discounts, unlinked provider charges,
provider-account matching and complete-invoice/account totals are outside scope.

For completed or operator-reconciled calls, the result reports statement-minus-
recorded amount/token differences and optional request-ID equality. **Matched**
means only the explicitly checked fields match. Missing optional fields remain
unchecked. A supplied request ID cannot match an absent/unavailable local ID.
Pending/unknown calls are **unresolved**, never zero-cost matches, and are excluded
from the settled-charge difference. Totals separately identify all selected billed
lines, billed amounts for comparable settled calls, and recorded settled charges.

No provider is contacted or authenticated. Recorded charges are the application's
operator-priced accounting, not proof of what a provider actually invoiced. Local
Ollama zero provider-token cost does not include hardware/electricity. This is not
a complete invoice reconciliation, financial settlement or billing verification.

## Saved reviews and access

Owner creation requires `members` permission. Reading saved cost-only metadata
requires `export` permission, allowing owner/security/auditor roles in the current
workspace/environment. Engineering/approval access alone does not authorize it.
Cross-environment references are rejected even though the underlying inference
budget is workspace-wide. No other environment's calls or totals are returned.

Reviews capture bounded statement fields, selected local cost/token/model-asset
metadata and comparison results. They do not copy answers, source excerpts,
provider credentials, request headers or the full inference result. Provider request
IDs use a restricted bounded reference format. Reviews are excluded from generic
workbench responses and are capped at 200 per environment, with paginated summary
listing and detail inspection.

An intent key recovers the original snapshot rather than comparing again. Changed
input under that key conflicts. If relevant local usage/status/reference metadata
changes or disappears later, detail/recovery marks the saved review stale without
rewriting its original measurements. Submit a new explicit intent to capture a new
comparison; separate reviews are not additive account totals. An existing separate
usage-settlement operation remains the only way to settle an unresolved call; this
feature never invokes it or releases held budget.

Browser recovery stores only a scoped key/fingerprint/timestamp, not statement
fields. Stored notes/reference labels remain owner-supplied data. These unsigned
application receipts do not provide authenticated invoice evidence, a retention
schedule, immutable off-host storage or production acceptance.

## API

- `POST /v1/billing-reviews` — owner creates a selected-call comparison with an
  intent key; returns the saved outcome and snapshot.
- `GET /v1/billing-reviews` — finance-authorized paginated recorded summaries.
- `GET /v1/billing-reviews/{id}` — current staleness plus unchanged saved results.
- `POST /v1/billing-reviews/recover` — author's original intent-key outcome.

All write-shaped requests require the normal session/CSRF/runtime context. The
review does not enable inference or introduce provider/network configuration.

## Focused development checks

Disposable normal-API checks use the existing synthetic inference HTTP transport
and verify matching fields, signed discrepancies, optional coverage, unresolved
reservations, stale snapshots after usage settlement, replay/recovery, strict money
and duplicate validation, period/capacity limits, read/write role gates and tenant/
environment isolation. They confirm no added provider requests or accounting-ledger
mutations from review operations. Frontend checks cover exact micro-unit conversion,
copied rows, optional fields and isolated lost-reply recovery; the build is checked.

Provider-verified invoice/account reconciliation, retention policies, account-level
cost controls, full acceptance testing, merging and deployment remain later work.
