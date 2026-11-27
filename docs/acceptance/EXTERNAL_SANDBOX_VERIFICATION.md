# External sandbox verification

**Status** Open. A disposable local HTTPS rehearsal has passed. It exercised denial, independent approval, one committed synthetic purchase, and reconciliation after a lost response. This plan repeats the flow against an approved external sandbox using the [NEXUS Business v1 contract](../../contracts/nexus-business-v1.openapi.json). [Existing loopback acceptance test](../BUSINESS_CONNECTOR_0_12_0.md#loopback-https-acceptance-test) · [Test source](../../backend/tests/test_business_sandbox.py)

## Setup

- Select one synthetic purchase workflow, an approved HTTPS sandbox, and a sandbox owner who can verify its records. Use sandbox-only data and credentials.
- Provision requester and independent reviewer accounts. Have the sandbox owner record approved tenant/organization scope and the baseline downstream record count.
- Configure the hostname, tenant, server-side secret reference, and trusted CA as required by the adapter. Review the fixed destination and egress rules. Use the approved binding through reconciliation. [HTTP adapter setup](../BUSINESS_CONNECTOR_0_12_0.md#operator-setup)
- Agree how the sandbox will simulate a lost response **after** committing. Use a sandbox-supported test control and obtain authoritative downstream evidence for the submitted operation. A client timeout alone leaves the business effect unknown.

## Verification matrix

| Case | Action | Pass condition and evidence |
| --- | --- | --- |
| Policy denial | Submit a synthetic request outside the allowed threshold or grant. | NEXUS records denial and the sandbox records no dispatch or business effect. |
| Independent review | Submit an approval-required request. Check requester self-approval is denied. Have the separate reviewer approve the original payload. | The ledger links the request, reviewed payload fingerprint, reviewer decision, and policy version. No purchase is sent before approval. |
| Confirmed success | Execute a separate approved synthetic request normally. | The ledger records a verified result and the sandbox contains exactly one matching record for its operation ID. |
| Response lost after commit | Use the pre-agreed sandbox test control on a fresh approved request. | The sandbox shows one committed effect and NEXUS records `outcome_unknown`. The worker sends no second purchase request. |
| Idempotency and reconciliation | Repeat admission with the same intent key and payload, then check that a changed payload with that key is rejected. Reconcile the original operation through the contract lookup. | NEXUS returns the original admissible operation, rejects the changed intent, and verifies the original effect. Sandbox record count for the operation remains exactly one. |
| Tenant isolation | Ask the sandbox owner to verify denial for a second authorized test fixture that lacks access to the original operation. | The wrong tenant receives no authoritative result for the original operation. Record a redacted decision reference and effect count. |

## Closeout

Retain the source revision and image digest, time window, non-sensitive request IDs, approval states, downstream effect counts, and authoritative reconciliation result. Record case status, owner, and open findings in the private release record. If the outcome is still unknown or the returned record differs, keep it open for review with the sandbox owner before creating another intent. [Staging acceptance record](STAGING_ACCEPTANCE_RECORD.md)
