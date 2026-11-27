# Explicit retention of expired signed-audit payloads

Audit explorer has an owner-only **Expired signed-evidence payload retention**
panel. Its policy is off by default. This feature removes only saved Ed25519 audit
snapshot payloads introduced in `SIGNED_AUDIT_EVIDENCE.md`. It does not delete
original audit events, business records, policies, signing keys or downloaded files.
It is not a retention mechanism for unsigned exports, inference, source documents
or backups. No background deletion job is introduced.

## Workflow

1. An owner saves a versioned policy with explicit enablement, a minimum snapshot
   age of 7–3650 days (default 30) and a visible reason. A policy change does not
   remove anything. Prior policy revisions remain available.
2. Review retained snapshot IDs and their ages/expiry in the current environment.
   Place a hold on any snapshot that must be protected from this tool. Releasing
   a hold requires the current hold version and a reason; it does not remove data.
3. Save a preview. It lists the exact eligible IDs, payload fingerprints and hold
   versions, pinned to the effective policy version. Eligibility requires both
   the stored record and signed creation timestamp to meet the minimum age, an
   expired download, correct payload scope, retained status and no active hold.
4. Review that preview and type `PURGE EXPIRED SIGNED AUDIT PAYLOADS`. Apply it with
   a visible reason within 15 minutes. The server rechecks every target and applies
   the entire list in one transaction or removes nothing.
5. Inspect the saved removal receipt. On a lost response, reload the saved plan;
   an applied plan is already complete. It cannot acquire new targets or run again.

A changed policy, payload, hold or download expiry invalidates the preview. Even a
hold added and then released changes its version and requires a new preview. A
snapshot that becomes eligible later is never added to an existing plan. New
plans can be created after reviewing the latest state.

## Preserved receipts and limits

Removal replaces the stored envelope with a small tombstone containing its intent
key hash/request fingerprint, expiry, signing fingerprint, original record count,
truncation flag, envelope hash, removal time and plan ID. No event list, signature,
snapshot note or full signed envelope remains in that row. The original audit
events and retention operations' audit events are preserved.

Export intent retries and recovery continue returning the same snapshot ID with
`status: purged`; they never sign a replacement. Own purged downloads return HTTP
410. Saved files outside the database are unaffected and can still be verified
with the appropriate trusted public key.

Removing a payload frees a slot under the 100 retained-payload limit. Tombstones
still count toward a lifetime bound of 5000 snapshot receipts per environment.
At that bound new exports fail rather than removing receipts. Retention policy
and preview histories are each bounded to 200 per environment. The final policy revision slot is reserved
for disabling, so history saturation cannot leave an enabled policy without a
disable path. Holds are attached only to existing retained snapshots, with versioned changes recorded in the audit
log. The dashboard shows the latest 20 policy and plan receipts and up to 100
retained payloads. No old operation receipt is silently erased to make space.

## Supported APIs

All retention endpoints require owner `members` permission and current environment
membership. Every write and receipt-recovery request requires CSRF. Every query is
scoped to the current workspace/environment; owners can manage snapshot payloads
created by any exporter in that environment without downloading their contents.

- `GET /v1/audit-retention`: effective policy, inventory, holds, recent policies
  and saved preview/removal receipts. This is read-only.
- `PUT /v1/audit-retention/policy`: `expected_version`, strict boolean `enabled`,
  integer `minimum_age_days`, `note`, and `Idempotency-Key`.
- `PUT /v1/audit-retention/holds/{snapshot_id}`: `expected_version`, strict boolean
  `held` and `note`. After an uncertain response, reload and inspect the hold;
  retrying its old version cannot change it twice.
- `POST /v1/audit-retention/plans`: current policy `expected_version`, `note` and
  `Idempotency-Key`. Saves a preview only.
- `POST /v1/audit-retention/policy/recover` or `/plan/recover`: `{ "key": "..." }`.
  Looks up the current account's original receipt; it never activates an old
  policy, refreshes a preview or applies removal.
- `POST /v1/audit-retention/plans/{plan_id}/apply`: policy `expected_version`, exact
  `confirmation` and `note`. The saved plan ID is the operation identity. A repeat
  with the same confirmation body returns its existing applied receipt, including
  after a later policy change. A different body conflicts. Any authorized current
  owner can review and apply a saved plan in the same environment.

Visible reasons must contain 10–500 characters and no control characters. Avoid
credentials or personal information in notes. Browser recovery uses separate
account/environment namespaces for policy and preview operations and stores no
notes, snapshot payloads or target lists.

## Boundaries

This is logical removal through the application, not guaranteed secure erasure
from database pages, transaction logs, replicas or existing backups. A hold protects
against this tool only; it is not an externally enforced legal hold or immutable
archive. It does not establish legal retention compliance. Off-host archival,
organization-wide lifecycle/retention, key custody, secure erasure and deployment
acceptance remain separate work.

Uses existing schema 12 storage, with no new migration or environment setting.
Development checks use disposable databases and ephemeral keys. No active database
is changed and no production removal is run by this development increment.

Focused checks from `backend`:

```text
python -m pytest tests/test_audit_retention.py tests/test_signed_audit.py tests/test_maintenance_schema_guard.py tests/test_runtime_context.py -q
```
