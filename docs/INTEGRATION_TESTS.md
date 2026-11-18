# Real-service integration tests

The default test suite uses SQLite. Optional tests explicitly skip when their service fixtures are not available; a skipped test is not a pass.

## PostgreSQL

`python scripts/test_postgresql.py` starts a real isolated PostgreSQL cluster using the optional `pgserver==0.1.4` package. Its bundled server used for this delivery is PostgreSQL 16.2. This is test tooling, not a production PostgreSQL deployment recommendation.

Install `backend/requirements-integration.txt` first. The script binds only a random loopback TCP port, disables Unix-domain sockets, uses disposable local test authentication, creates one randomly named schema per case and cleans up. No customer database credentials are used.

For an existing **disposable test-only** PostgreSQL database, set `NEXUS_TEST_DATABASE_URL` and explicitly opt into schema creation with `NEXUS_TEST_ALLOW_SCHEMA_CREATE=1`. The fixture drops only the random schemas it created. Never use a customer/production URL.

The tests exercise parallel workers, duplicate intent submission, policy-version compare-and-set, revocation, cross-tenant database constraints and simultaneous schema upgrades against the actual database engine.

## Keycloak

Download an official Keycloak distribution appropriate to your review policy. The compatibility fixture used in this delivery is Keycloak 26.0.7 on Java 21. A supported patched production version requires separate customer validation.

Set `NEXUS_KEYCLOAK_HOME` to the extracted distribution. The tests generate a private temporary CA, a localhost server certificate, a development realm, passwords and one TOTP seed. Keycloak runs over HTTPS with certificate verification enabled. The test CA is trusted only by that fixture; it is never added to system trust. Generated secrets and service binaries are excluded from the release.

The suite performs the authorization-code/PKCE flow through the real IdP, rejects unprovisioned and revoked local memberships, checks a configured TOTP factor with wrong and correct codes, rejects an untrusted TLS chain and rejects a wrong PKCE verifier. API callbacks run through the ASGI test client. These are protocol tests, not a production browser or organization-wide MFA certification.

The fixture creates a uniquely named realm-import file under Keycloak's `data/import` directory and removes it afterward. Use a dedicated test distribution, not a shared or production installation.

## OPA

Set `OPA_BIN` to a trusted OPA executable. The tests start a local OPA HTTP service for each integration case. Native Rego tests can also be run with `opa test policies -v`.

## Full local matrix

macOS/Linux, using the venv Python:

```sh
OPA_BIN=/trusted/path/opa \
NEXUS_KEYCLOAK_HOME=/trusted/path/keycloak \
.venv/bin/python scripts/test_postgresql.py
```

The complete real-service harness was verified on Linux. Windows users can run the full matrix under a reviewed WSL/Linux setup. Native Windows Keycloak launcher and bundled PostgreSQL test-tool support are not claimed; normal Windows application startup remains supported by the separate PowerShell script.

JUnit files record results and skips. Do not sum the SQLite and PostgreSQL runs as distinct product features; they repeat the same cases under different engines. No production credentials, generated test passwords, OTP seeds or authorization codes should be copied into reports.
