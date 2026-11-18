# NEXUS implementation and remaining phases

Release 0.2.0 | 13 November 2026 | Continuation: PostgreSQL, organization identity and schema upgrades

## Outcome

The governed-action prototype now has verified real PostgreSQL and Keycloak integration paths. The complete integration run passed **88 tests with zero failures and zero skips**. It used a real PostgreSQL 16.2 server, OPA 1.0.1 and Keycloak 26.0.7 over certificate-verified HTTPS. These were isolated synthetic test services, not customer or production deployments.

The professional sign-in and portal remain included. The settings panel now exposes SSO configuration, schema version and the server-side PKCE design. The production frontend build passes. This release is a tested integration prototype, not a claim that every enterprise requirement is finished.

## What changed in 0.2.0

- Moved OIDC state and PKCE verifiers from a signed client cookie to server-side transactions. The browser receives only an opaque binding token. Verifiers are encrypted with AES-GCM using a purpose-derived key.
- Made each sign-in transaction single-use with an atomic consumption update, browser binding and a five-minute expiry.
- Added issuer, audience, signature, key ID, nonce, authorized-party, verified-email and optional authentication-context checks. Discovery must match the configured issuer and its endpoints must share that origin and support S256.
- Added optional enterprise/private CA trust without disabling TLS verification. The real Keycloak fixture uses its own temporary CA; system trust is unchanged.
- Added a configurable required ACR context. Pilot mode requires an explicit context; the customer must map that context to a real MFA flow in the IdP.
- Added schema version 2 and forward-only migration logic. Version-1 accounts and existing business records are preserved. PostgreSQL migrations serialize through a transaction advisory lock; unknown newer schemas are rejected.
- Added startup and readiness guards for schema compatibility. Added optional trusted IdP subject binding during local user provisioning.
- Fixed policy-version activation under concurrent PostgreSQL updates and added actual race tests.
- Added reusable PostgreSQL/Keycloak integration harnesses, a PostgreSQL CI job, current OpenAPI, schema-2 DDL, upgrade instructions and evidence records.

## Verification matrix

| Verification | Observed result | Meaning and boundary |
|---|---|---|
| Complete PostgreSQL integration run | 88 passed; 0 failed; 0 skipped | Full collected suite with real OPA and Keycloak services enabled |
| SQLite regression with OPA | 76 passed; 12 skipped | Same code; six Keycloak cases and six PostgreSQL-specific cases were not run in this matrix |
| Real Keycloak cases | 6 passed within the 88-test run | Authorization-code login; unprovisioned email; revoked local membership; wrong/correct TOTP; untrusted TLS; wrong PKCE verifier |
| PostgreSQL race/constraint cases | 6 passed within the 88-test run | Parallel workers, policy updates, identical intents, revocation, tenant constraints and schema upgrade |
| OIDC cryptographic and migration cases | Included in the 88-test run | Invalid claims/signatures, replay, expiry, context, discovery, data preservation and schema guards |
| Native Rego cases | 5 passed separately | Supported policy rules, not an additional customer adoption metric |
| Frontend | TypeScript and Vite build passed | Existing portal plus settings/release changes; no new comprehensive visual/accessibility audit |

The Keycloak and PostgreSQL subsets are already included in 88; do not add them again. The SQLite run repeats overlapping cases and is not 76 additional features. JUnit evidence is in `docs/postgresql-test-results.xml`, `docs/sqlite-test-results.xml` and the derived Keycloak subset file. The full run took approximately 92 seconds on this environment.

Two test-dependency deprecation warnings remain from AnyIO/pytest and Starlette/httpx. There were no test failures in the final matrices. GitHub Actions definitions were updated but were not executed remotely here.

## What the real-service tests prove

The PostgreSQL suite exercises the actual database schema, tenant-scoped APIs, approval compare-and-set, immutable actions, policy thresholds, workload tokens, execution/reconciliation and exports. Its additional concurrency cases confirm one external mock effect under parallel workers; one policy-change winner; one logical action for simultaneous identical requests; revocation before later dispatch; rejection of a cross-tenant foreign key; and simultaneous data-preserving schema upgrade.

The Keycloak protocol cases exercise the actual authorization-code exchange, S256 PKCE and JWKS verification. A configured reviewer TOTP factor rejects a wrong code and accepts a valid code. Verified IdP email alone cannot provision a local membership. Revoking the local membership prevents new SSO access. A wrong verifier or untrusted TLS certificate fails closed.

The application callback in these tests runs through the ASGI test client. This is not a full production browser SSO test, organization-wide MFA policy audit, back-channel logout implementation or proof of customer identity lifecycle synchronization. The fixture uses a dedicated development realm and generated identities; no real passwords, OTP seeds or customer data are distributed.

## Current phase status

| Phase | Current state | Still remaining |
|---|---|---|
| Product/design baseline | Supplied documents and implemented local workflow | Resolve customer deployment/data/retention/recovery decisions |
| R1 identity/database core | Implemented and verified for this release scope | Multi-membership and environment switching; finer assigned-object access; workload federation; production MFA/context and recovery policy review |
| Action enforcement/review | Local core plus real OPA path verified | General tool onboarding and custom resource-level constraints |
| Execution/outcome evidence | Mock connector and unknown-outcome recovery verified | One real approved business connector, managed secrets, egress isolation, vendor-specific timeouts/idempotency/heartbeat/reconciliation |
| Operations/assurance | Dashboard, audit, JSON export, evaluations and containment implemented | OpenTelemetry/Langfuse, real alerts, usage/billing, budget reservations, retention jobs, hardened audit storage and restore drill |
| Deployment/customer pilot | Local source and Compose/CI configuration supplied | Actual Compose validation, reviewed cloud IaC/TLS/private network, independent security/load/accessibility review and authorized customer pilot |

R1 is not labelled complete for every original enterprise feature. This release closes its real-service verification and schema-upgrade lane while the listed access-model expansions remain open. No overall completion percentage is used.

## Upgrade and run

For a new installation, follow README.md: Windows `scripts/start.ps1`, or macOS/Linux `bash scripts/start.sh`. Initialization creates schema version 2 and prints randomly generated local development credentials. The API and separate worker both need to run.

For an existing 0.1.0 installation, stop API/worker, back up both databases and retain the private `.env`. Extract the new source to a new directory, securely transfer your existing configuration/data, install dependencies, then run `python -m nexus.cli migrate` with the virtual environment Python from `backend`. Restart only after migration succeeds and `/health/ready` reports `schema_version: 2`. Do not delete data or reset user passwords to upgrade. Full steps are in `docs/UPGRADE_0_2_0.md`.

The normal local sign-in remains available in local mode. Organization SSO requires a trusted issuer/client and preprovisioned membership. Optional `NEXUS_OIDC_CA_BUNDLE` selects private CA trust; optional `NEXUS_OIDC_REQUIRED_ACR` constrains the signed authentication-context claim and is mandatory in pilot mode. Configure the IdP policy to make that claim meaningful. No local password-based MFA or automatic SCIM provisioning is asserted.

The complete real-service harness was verified on Linux/Java 21. Native Windows application startup is supplied, but the Keycloak test launcher currently uses `kc.sh`; native Windows execution of that entire test matrix is not claimed. See `docs/INTEGRATION_TESTS.md` for reproducible commands and optional dependency requirements.

## Next implementation phases

### R2 - Real connector and secret boundary

Choose one authorized customer test API. Implement endpoint allowlisting, managed secret retrieval, connector-specific idempotency, bounded timeouts/worker leases and authoritative outcome lookup. Prove that agent/browser identities cannot retrieve credentials or bypass the gateway. Keep critical money movement and production deletion out of the initial scope.

Exit evidence: allowed/denied/approved/timeout paths against that permitted test system, with no leaked secrets or duplicate side effects.

### R3 - Operational assurance

Integrate redacted telemetry and alerts, actual provider usage and billing attribution, atomic spend reservations, retention/deletion and richer exports/pagination. Tighten real-data payload visibility and database audit privileges. Rehearse backup/restore with dispatch disabled and external-effect reconciliation. Measure recovery results before claiming an RPO/RTO.

Exit evidence: correlated monitored actions, honest usage labels, controlled retention and a demonstrated safe restore.

### R4 - Cloud and authorized customer pilot

Build reviewed infrastructure for the chosen account/region, TLS ingress, private data tiers, managed secrets, image/security scanning and safe rollout/rollback. Agree customer data scope, identity policy, support ownership and acceptance. Complete independent security review and representative load/mobile/accessibility testing.

Exit evidence: a restricted customer pilot with measured outcomes and documented limitations. No enterprise production readiness is claimed before those gates.

## Operational boundaries

The business connector is still synthetic and stores effects in a separate SQLite mock database, even when the control plane uses PostgreSQL. No real payments or customer records are changed. The Docker Compose files, cloud topology, managed secret service and production network isolation have not been verified by this work.

Local sessions and signing-key management remain a development design. Local membership revocation is checked; external IdP deactivation does not automatically invalidate every existing application session. Back-channel logout and customer offboarding need further implementation. Process-local rate limits and the header size check are not distributed edge controls. Audit records are durable application evidence, not certified immutable storage.

This release adds an OIDC transaction table but not scheduled transaction cleanup. Retention jobs, denied-login abuse controls, production key rotation and support procedures remain operational work. The chosen PostgreSQL/Keycloak versions are compatibility fixtures; selecting and validating supported production versions remains part of deployment review.

## Package and references

The ZIP contains the implemented source, built portal, JS lockfile, Python requirements, schema DDL, current OpenAPI, SDK examples, tests/evidence, startup/upgrade scripts, Compose/CI definitions and reference design PDFs. Version-0.1 report history is retained under `docs/archive/0.1.0`. Databases, runtime secrets, service binaries, virtual environments, node_modules, temporary certificates and generated IdP credentials are excluded.

Technical references used for the integration work: Keycloak OIDC endpoint documentation (`https://www.keycloak.org/securing-apps/oidc-layers`), Keycloak hostname configuration (`https://www.keycloak.org/server/hostname`), PostgreSQL row-lock documentation (`https://www.postgresql.org/docs/16/explicit-locking.html`) and the `pgserver` project (`https://github.com/orm011/pgserver`). The supplied NEXUS design PDFs remain the product baseline; this report is the current implementation status.
