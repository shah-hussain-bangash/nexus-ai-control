# Customer HTTP compatibility adapter — 0.12.0

This source implements one fixed protocol, NEXUS Business v1, not arbitrary ERP/MCP mapping. Implement/review the customer-side gateway described in contracts/nexus-business-v1.openapi.json. Tests use httpx.MockTransport; no customer service has been accepted by this package.

## Operator setup

Keep NEXUS_BUSINESS_CONNECTOR=synthetic for ordinary local demonstrations. For an approved sandbox only, configure server-side environment values:

```text
NEXUS_BUSINESS_CONNECTOR=http
NEXUS_BUSINESS_BASE_URL=https://sandbox.customer.invalid/api/v1
NEXUS_BUSINESS_HOST=sandbox.customer.invalid
NEXUS_BUSINESS_TENANT=reviewed-sandbox
NEXUS_BUSINESS_TOKEN_ENV=NEXUS_BUSINESS_API_KEY
NEXUS_BUSINESS_TIMEOUT_SECONDS=10
NEXUS_BUSINESS_RESPONSE_BYTES=262144
```

The hostname above is intentionally invalid; replace it with the reviewed customer sandbox. Inject the real credential as NEXUS_BUSINESS_API_KEY via the secret manager. Do not paste it into the dashboard, URLs, ZIP, screenshots or Git. Optionally configure NEXUS_BUSINESS_CA_BUNDLE for a trusted enterprise CA. TLS verification cannot be disabled. Provision network egress to only the reviewed destination; the adapter does not inherit environment proxies or configure firewall policy.

Stop all workers/API before changing configuration, review queued/unknown operations, then restart them with the same intended binding. Changes in base URL or remote tenant change the destination fingerprint and block old queued dispatch. Do not bypass this by editing stored envelopes or fingerprints. Restore the old reviewed binding to reconcile an old unknown effect, or investigate with the customer system owner. Key rotation for the same destination/tenant does not alter the binding.

## Required customer behavior

- Authenticate the bearer credential and authorize the remote tenant plus local organization. Never trust a supplied organization header without checking it against the credential.
- Accept X-Nexus-Contract=nexus-business-v1, X-Nexus-Tenant, X-Nexus-Organization and Idempotency-Key. The idempotency key is the persisted local operation ID.
- GET /suppliers/{supplier_id}: return state `found`, matching supplier reference and external_ref. Keep an authoritative operation result for reconciliation.
- POST /purchase-requests: atomically deduplicate by operation/tenant/organization and bind that key to the immutable arguments. The same key/body returns the same effect; a different body under that key must be rejected without another effect. Return state `created`, external_ref and the original supplier_id, amount, currency and purpose.
- GET /operations/{operation_id}: read an authoritative result without creating or retrying an effect. Scope the lookup to the authenticated remote tenant and local organization. A missing result is inconclusive.

Successful JSON is wrapped as operation_id, organization_id, tenant_id and result. Amount uses two-decimal string form and USD; supplier references are bounded to 64 safe identifier characters. The control plane still enforces registered tools, workload generation, grants, policy decisions, exact payload review and independent human approval. Customer-side authorization and deduplication need independent sandbox evidence.

## Acceptance sequence

Verify credential scope/TLS, supplier-read isolation, duplicate requests, mismatched key/body rejection, independent purchase approval, timeout-after-commit reconciliation, unavailable lookup, wrong tenant result, oversized response and destination change. Begin with synthetic test records in a customer-approved sandbox. There are no automatic HTTP retries. Unknown outcomes remain unknown until authoritative evidence matches; repeated submission is not a recovery procedure.

The dashboard displays HTTP BUSINESS and an external-effects banner when configured. Review Release readiness → Runtime signals before submission. Do not use local demonstration accounts/data policy as proof of enterprise identity acceptance.
