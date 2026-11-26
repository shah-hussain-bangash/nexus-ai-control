# Phase 1 development: Business v1 reference gateway

Selected scope: a local developer reference using synthetic suppliers and
purchases. No customer system has been selected or approved. Formal customer
acceptance and deployment testing follow development; focused source checks are
still required while building the gateway.

## Implemented development foundation

`backend/nexus/business_reference.py` implements the customer-side shape of the
existing [Business v1 contract](../contracts/nexus-business-v1.openapi.json).
It is a separate, unmounted ASGI factory, not a new control-plane API or an ERP.
Importing it starts no server, creates no workspace and loads no operator
settings, `.env` or credentials.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/suppliers/{supplier_id}` | Return and persist an idempotent synthetic supplier-read receipt. |
| `POST /api/v1/purchase-requests` | Atomically create one synthetic purchase and its operation receipt. Exact duplicate requests return the stored receipt; changed arguments or action under the same scoped key return 409. |
| `GET /api/v1/operations/{operation_id}` | Read a scoped authoritative receipt without creating or retrying an effect. A missing receipt returns 404 and remains inconclusive to the NEXUS client. |

Each developer-supplied credential is bound to exactly one remote tenant and
local organization. The bearer credential is authenticated before those headers
are accepted. Body tenant, organization and operation must match the bound
headers. The operation key is scoped by tenant and organization; another
credential cannot read that scope's receipts by changing headers. Stored
credential bindings use token hashes in memory; raw tokens are not stored in the
SQLite workspace or included in reports.

The fresh reference workspace has separate `operations` and
`synthetic_purchases` tables. The key lookup, purchase and receipt share one
`BEGIN IMMEDIATE` SQLite transaction. Concurrent duplicates serialize to one
synthetic purchase. A failed effect insert rolls back its receipt. Receipts
survive explicit workspace reopening and app recreation. Wire arguments are
preserved exactly, including amount strings, so changing a body cannot silently
reuse an existing fingerprint.

Only `SUP-DEMO-104` and `SUP-DEMO-105` are synthetic suppliers. Unsupported
suppliers return 404. The workspace has a 1,000-operation development capacity;
requests have an 8 KiB body limit. Duplicate security headers, unexpected body
fields, invalid scopes and unsupported contract versions are rejected. Errors
omit submitted values, credentials, SQLite details and raw exception text.

## Developer entry point

After this source is integrated and the project's existing environment is set
up, run from the project root:

```powershell
npm.cmd run dev:business-reference
```

The portable entry point is `python scripts/run_business_reference_example.py`.
It creates a fresh temporary reference database and random in-memory credential,
uses the three HTTP-shaped endpoints through FastAPI's in-process client, reopens
the store, and writes a small unsigned JSON development receipt under
`backend/data/drills`. Temporary databases are removed before success is reported.
No port is opened and no credential is printed or saved in the receipt. Existing
directories are not reused by `ReferenceBusinessStore.create`; reopening is an
explicit operation that checks the reference application ID and store version.
These markers detect accidental workspace mix-ups, not tampering or authenticity.

The existing NEXUS `HTTPBusiness` adapter also works against this factory through
a development-only transport. Its operator host, HTTPS/TLS, credential, immutable
destination, policy, approval and worker controls are not weakened. The focused
development checks cover a purchase waiting for independent approval, a simulated
timeout after the reference purchase commits, no automatic replay, and recovery
through the authoritative operation lookup.

## Work deliberately left for the next stage

- Select a customer system and implement its resource and authorization mapping.
- Provision an approved TLS endpoint, credential lifecycle, egress policy,
  persistent hosting, backup, retention and resource controls.
- Perform formal contract, tenant-isolation, fault, load and operator acceptance
  tests against the selected customer sandbox.

Keep the running app's connector in `synthetic` mode. This reference does not
provision HTTPS or provide a production service launcher; do not expose it on a
network or point real credentials, purchases or customer data at it. Do not relax
the real adapter's HTTPS/host checks to make a local demo appear connected.

No NEXUS database schema, active configuration, account or production-readiness
state is changed by this development increment.
