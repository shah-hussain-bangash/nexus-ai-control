# Local operational alert thresholds

Operations → Signals contains a **Local operational alert thresholds** panel.
Owners configure up to seven fixed database signals per workspace/environment.
Users with `operate` permission can record a manual check. All authenticated
environment members can inspect the same coarse signal counts and saved receipts.

The signals are oldest queued action age in seconds, unknown action outcomes,
unknown inference outcomes, inference pending for at least 300 seconds, and expired
processing leases for ingestion, index construction and durable agent runs.
Counts include all matching rows in the selected environment; no record contents,
prompts, identifiers, source titles, URLs or credentials are included. Leases at
the sampling time count as expired. Future queue timestamps clamp to zero age.
Each refresh reads all seven signals in one database statement.

Rules fire when the value is **greater than or equal to** the positive integer
threshold. Queue age is bounded to seven days (604800 seconds); count thresholds
are bounded to 1000000. Severity is a label (`warning` or `critical`). Disabled
rules never fire. With no enabled rules the overall result is `disabled`, not
`clear`. A configured rule may cover only one signal; unrelated signals do not
change its result.

Supported authenticated APIs:

- `GET /v1/operational-alerts`: current policy and unsaved point-in-time readings.
- `PUT /v1/operational-alerts/policy`: owner change with `expected_version`,
  `rules`, a visible 10–1000 character `note`, CSRF and `Idempotency-Key`.
- `POST /v1/operational-alerts/sample`: operator check with `expected_version`,
  `note`, CSRF and `Idempotency-Key`. No enabled rules produces a disabled receipt.
- `GET /v1/operational-alerts/history?kind=sample`: newest first, `offset` and
  `limit` (default 20, maximum 50). `kind=policy` returns policy revisions.
- `POST /v1/operational-alerts/policy/recover` and `/sample/recover`: CSRF-protected
  lookup of the current account's original receipt using `{ "key": "..." }`.

Policy changes serialize per workspace, reject stale versions, supersede the
previous active revision, and preserve its payload. Samples store their policy
version, timestamp, seven values and evaluated rules. Earlier-policy samples are
marked `stale_policy`; they are never reinterpreted using new thresholds. Retrying
the same intent returns its original receipt, including after a policy change.
Changing the body with that key is rejected. Recovery cannot reactivate an old
policy, resample or run work. Browser recovery stores the key and request hash,
not notes or signal data, separately for policies/samples, account and environment.

History is bounded to 200 policy revisions and 500 checks per environment. At
capacity, new writes fail without removing existing records. The dashboard shows
the latest 20 of each; older receipts remain available through paginated APIs.
These records use existing schema 12 storage and are excluded from generic
workbench results. There is no new migration, environment variable or execution
flag for this feature. No rules are created by default.

This is **manual local evaluation**, not continuous monitoring. No background
sampler, alert delivery, automatic remediation, new worker, provider request,
webhook or global metrics label is introduced. A clear recorded check is valid
only for its sampled time and configured rules. It does not demonstrate worker
liveness, external notification delivery, service objectives or production readiness.

Focused disposable verification:

```text
python -m pytest tests/test_operational_alerts.py tests/test_runtime_operations.py tests/test_runtime_context.py -q
```

Run from `backend` in the review checkout with the test dependencies installed.
Full acceptance, alert delivery drills, merges and deployment are separate work.
