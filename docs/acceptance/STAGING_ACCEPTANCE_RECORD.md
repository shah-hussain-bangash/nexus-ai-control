# NEXUS staging acceptance record

**Status** Open. Fill in this record for the approved live staging environment. The repository has a passing Chromium workflow, image smoke test, Docker Compose check, and disposable PostgreSQL recovery rehearsal. Those results support the release record. The live checks below still need target-environment evidence. [CI run](https://github.com/shah-hussain-bangash/nexus-ai-control/actions/runs/45921147780) · [Pilot runbook](../../infra/pilot/README.md#staging-verification) · [CI recovery rehearsal](../CI_POSTGRESQL_RECOVERY.md)

## Record before testing

| Item | Record privately |
| --- | --- |
| Release under test | Source commit, immutable registry digest, expected schema, and deployment time |
| Environment | Approved HTTPS origin, identity-provider tenant, database target, and test window |
| Owners | Deployment operator, identity/security reviewer, operations owner, and release approver |
| Success thresholds | Restore-time target, maximum data-loss window, alert delivery target, and log retention |

Keep secrets, private origins, tenant identifiers, and account details in the approved private release record. Link redacted receipts from this document or an internal copy as appropriate.

## Acceptance checks

| Check | Procedure and pass condition | Required evidence | Status |
| --- | --- | --- | --- |
| HTTPS and runtime readiness | Run `python scripts/check_staging.py APPROVED_HTTPS_ORIGIN --expected-schema 11` for the 0.16.2 candidate. Use the schema expected for the actual release. Require HTTPS, pilot mode, HSTS, OPA readiness, disabled local login, and anonymous access denial. | Preflight JSON and deployed image digest | Pending |
| SSO and MFA | Confirm a provisioned account signs in with the required MFA context. Password-only and unprovisioned sessions are denied. Verify access revocation for a disposable account. | Redacted IdP and NEXUS event references | Pending |
| Network and secret rotation | Confirm private database access and the approved service egress policy. Rotate a scoped staging credential under the approved procedure. Verify the replacement works and the previous credential is rejected. | Redacted secret version references, access policy and rotation result | Pending |
| Metrics and alert delivery | Verify the authenticated scrape using the approved metrics credential. Simulate a controlled readiness or scrape failure within the test window. Confirm delivery to the designated operator and recovery notification within the agreed target. | Scrape receipt with firing, delivery, and resolution timestamps | Pending |
| PostgreSQL recovery | Restore a representative encrypted snapshot into a new isolated target. Verify readiness, permissions, and a known test record. Measure restore time and the age of the latest recoverable record against the stated targets. | Backup/restore run ID, record checks, RTO/RPO measurements | Pending |
| Rollback and decision | Rehearse the approved rollback for the tested change. Record open findings, their dispositions, and the approver's decision on staging acceptance. | Rollback outcome and dated sign-off | Pending |

The preflight performs read-only endpoint checks. Use the documented `--check-metrics` option when an approved scrape credential is available. The remaining checks require separate live evidence. [Preflight script](../../scripts/check_staging.py) · [Image vulnerability triage](IMAGE_VULNERABILITY_TRIAGE.md) · [External sandbox verification](EXTERNAL_SANDBOX_VERIFICATION.md)
