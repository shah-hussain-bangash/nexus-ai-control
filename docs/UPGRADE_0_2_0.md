# Upgrade from 0.1.0 to 0.2.0

This upgrade preserves the existing user accounts, agent grants, actions, approvals and runtime secrets. Schema version 2 adds a table for single-use OIDC transactions with encrypted PKCE verifiers. It does not require deleting your database or resetting passwords.

1. Stop your NEXUS API and worker. Keep your old source ZIP and create a backup of the control database and mock business database. Copy the existing private `backend/.env` securely; do not send it in chat.
2. Extract the updated source into a new directory. Copy your old `backend/.env` and `backend/data` into the corresponding new directories. Do not overwrite them with example files. For PostgreSQL, retain the same private connection settings and use your reviewed backup procedure.
3. Install dependencies and build the portal using README.md. The main runtime dependency set is unchanged; integration-test dependencies are separate.
4. From the new `backend` directory run `python -m nexus.cli migrate` using your virtual environment's Python. On Windows: `..\.venv\Scripts\python.exe -m nexus.cli migrate`. On macOS/Linux: `../.venv/bin/python -m nexus.cli migrate`.
5. Confirm the command reports schema version 2, then restart the worker and API. `/health/ready` must return `schema_version: 2`. Startup refuses an uninitialized or outdated schema.
6. Discard pending SSO attempts from the old release and start a fresh sign-in. Existing ordinary application sessions and local accounts retain their original schema fields. Rehearse restore before applying the upgrade to valuable data.

## SSO configuration

Use the same issuer and client ID as before. `NEXUS_OIDC_REQUIRED_ACR` optionally constrains the signed authentication-context claim; it is mandatory for pilot mode. Configure the IdP so the chosen context actually represents the required MFA flow. A claim name alone does not establish that MFA occurred.

`NEXUS_OIDC_CA_BUNDLE` optionally selects a private CA PEM bundle for enterprise identity-provider TLS. Leave it empty to use normal system trust. Never disable certificate verification. Discovery requires an exact issuer and same-origin authorization, token and JWKS endpoints supporting S256 PKCE.

Provision users before SSO. You can pin a trusted subject at provisioning time:

```sh
python -m nexus.cli create-user --email person@company.example --name "Workspace User" --role engineer --oidc-subject "trusted-idp-subject"
```

Configure the trusted issuer first. When no subject is prebound, the existing trusted-issuer + verified-email first-binding workflow applies; later subject changes are rejected. This is not SCIM or automatic membership synchronization.

## Reproduce verification

Core tests (SQLite):

```sh
cd backend
python -m pytest --junitxml=../docs/sqlite-test-results.xml
```

Disposable real PostgreSQL cluster, from the root with your venv Python:

```sh
python -m pip install -r backend/requirements-integration.txt
python scripts/test_postgresql.py
```

To include real OPA and Keycloak tests, set `OPA_BIN` to a trusted OPA executable and `NEXUS_KEYCLOAK_HOME` to a trusted extracted Keycloak distribution, then run the same harness. See `docs/INTEGRATION_TESTS.md`. The harness uses a random loopback TCP port and no Unix socket. It creates, then removes, its own disposable test cluster and per-test schemas. Do not point its tests at a production database.

No downgrade script is supplied. Do not drop tables or restore an old backup while a worker is running. Restore the entire reviewed backup set with dispatch disabled and reconcile possible external side effects before resuming.
