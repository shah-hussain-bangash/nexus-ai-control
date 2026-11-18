# Deployment boundaries

The root Compose file provides local PostgreSQL, OPA, API, initialization and a worker. It is a development topology, not a production release. No cloud infrastructure was provisioned or verified for this delivery.

Before a real pilot, implement reviewed infrastructure as code for the selected account and region, TLS ingress, private networking, managed secrets, backups/PITR, monitoring, retention and restore/reconciliation. Do not treat this folder as working AWS Terraform: no Terraform has been fabricated.

## Optional local Keycloak fixture

Set `KEYCLOAK_ADMIN_PASSWORD` privately, then run from the repository root:

```sh
docker compose -f infra/keycloak.compose.yaml up -d
```

The realm import contains no users or passwords. In the local Keycloak admin console, create a verified-email test user whose email already exists in NEXUS. Configure MFA in the IdP. Add these values to **backend/.env** for a backend running directly on your machine:

```dotenv
NEXUS_OIDC_ISSUER=http://localhost:8080/realms/nexus
NEXUS_OIDC_CLIENT_ID=nexus-console
NEXUS_ORIGIN=http://localhost:8000
```

Restart the API. The SSO button appears. Local roles are preprovisioned; an arbitrary IdP email does not grant access. Do not use the localhost issuer from a separate API container without designing correct externally visible issuer/backchannel routing.

Release 0.2.0 includes a separate real Keycloak HTTPS protocol fixture with issuer/JWKS/PKCE and configured TOTP verification. The Compose identity-provider fixture in this directory was not executed. Customer role provisioning, recovery, MFA policy/context mapping and production deployment still require review. Pilot mode deliberately requires HTTPS, PostgreSQL and OPA, and still does not make the mock connector a real customer integration.
