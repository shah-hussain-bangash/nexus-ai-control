# Bounded supplier allowlist condition

In the durable execution form, choose **Supervised procurement**, enable
**Continue only for listed suppliers**, and enter one to ten unique supplier
references separated by commas. The condition and list become part of the
immutable run request. Changing the list under the same idempotency key is a
conflict; recovery returns the original run without a second submission.

After the supplier lookup is verified, a match continues to the existing
independent workflow review and governed purchase. Purchase policy and its
separate business approval remain required. A non-match skips all remaining
steps before the final output and records which condition skipped them. The
skipped path creates no purchase action or approval; earlier completed work is
not undone. A completed workflow with skipped purchase steps
is not an executed purchase; the dashboard explicitly shows this distinction.

This is a per-run routing rule chosen by its authorized author, not a global
supplier security policy. Omit it to retain the previous workflow behavior. It
does not replace policy evaluation, grants, current requester/agent access or
independent approvals. Every downstream purchase in a conditioned workflow must
refer to the same supplier as its source lookup.

The API step shape is:

```json
{
  "kind": "condition",
  "label": "Check supplier allowlist",
  "condition": {
    "kind": "supplier_allowlist",
    "source_step": 1,
    "supplier_ids": ["SUP-DEMO-104"]
  }
}
```

Positions are zero-based. The source must be an earlier governed supplier read
in the same run. Match continues to the next step; non-match jumps only to the
final output. There are no arbitrary targets, cycles, parallel execution, custom
expressions or model-generated decisions. Existing 12-step and admission bounds
remain. New optional fields are omitted from old definitions so immediate and
scheduled workflows retain their existing fingerprints.

At execution the worker checks the source's scope, run/actor/agent identity,
immutable request and result bindings, verified status and matching result. A
missing, changed or uncertain source stops progress rather than choosing a
route. An uncertain supplier effect must be reconciled through the original
action before the condition can advance. No automatic replay is introduced.
Non-match cannot skip a missing, submitted or previously processed step. Route,
skipped states and cursor are saved in one transaction, under the existing
worker claim/version controls. Pause, cancellation and scheduled-start behavior
are retained.

Unsigned run evidence includes the condition outcome, source/next positions and
skip origin, with consistency checks against the recorded source. It excludes
the allowlist and supplier values. Evidence remains an unsigned snapshot, not
authenticity, current server state, customer acceptance or production readiness.

This source builds on unmerged PR #76 and uses existing schema-11 JSON/status
fields; no migration or live configuration change is needed. Development checks
use disposable synthetic databases only. General workflow graphs, recurrence,
event triggers, autonomous planning and connector compensation remain future
work.
