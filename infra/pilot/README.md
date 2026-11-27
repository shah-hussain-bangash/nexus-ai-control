# Pilot deployment candidate — not production sign-off

This profile requires an externally managed PostgreSQL database with certificate validation and an OIDC provider enforcing the configured MFA context. No database, IdP, secret manager or cloud account is provisioned automatically. Business tools are synthetic; the synthetic worker is disabled by default.

1. Build the application image using the root Dockerfile in CI; scan it and record its immutable digest. Obtain reviewed compatible Caddy 2 and OPA image digests. Never use the placeholder digests.
2. Create private runtime/deployment environment files from the supplied examples. Provision distinct runtime secrets, database connection, IdP settings and optional provider credentials through your environment. Keep private files outside source and protected by filesystem/cloud permissions. A trusted database CA may require an additional read-only volume mount and sslrootcert parameter. Provision the app-owned data volume for uid 10001.
3. Configure DNS, TLS reachability, firewall/egress rules, encrypted backups and monitoring. The profile's egress network allows outbound connections and is not an allowlist.
4. With Docker available, validate: docker compose --env-file deployment.env -f infra/pilot/compose.yaml config -q. YAML parsing in this build is not equivalent to this check.
5. After an authorized backup and maintenance window, run the migrate service once. For a brand new empty deployment, run python -m nexus.cli bootstrap with --email, --name, --organization and --oidc-subject via a one-off app container. This creates one OIDC-bound owner, no synthetic agents/tools. Do not use local init in pilot mode.
6. Start api/edge/opa and perform actual authentication, fail-closed policy, provider, load and recovery acceptance before opening access. The API has no published host port; Caddy is the TLS edge.

The [`pilot-compose` CI job](../../.github/workflows/ci.yml) resolves this configuration with disposable values. It checks that only Caddy publishes host ports, OPA stays on the internal network, and migration and synthetic execution remain opt-in profiles. This check does not start containers or connect to staging services. The pilot template targets one host. See the [production acceptance reference](../../docs/PRODUCTION_ACCEPTANCE.md) for rollout evidence.

## Release image smoke test

The [`pilot-image` CI job](../../.github/workflows/ci.yml) builds the root Dockerfile and starts its image on a loopback-only port with disposable SQLite data. It checks UID 10001, read-only operation, database readiness, anonymous access denial, and service of the compiled portal and its JavaScript. To repeat on a host with Docker, Bash, and Python 3, run `bash scripts/smoke_pilot_image.sh` from the repository root.

The smoke test uses local reference policy and synthetic records. It removes its generated container, image tag, and volume on exit.

CI publishes a `pilot-image-evidence` artifact with SPDX and Syft inventories, Grype's vulnerability report, and a receipt linking the tested local image ID to the source revision. Findings are report-only and require review before release. The scan covers packages identified in the final image. Bundled browser dependencies may require a separate lockfile review. Staging identity and production rollout require separate evidence.

## Backups

Stop API and worker before a cross-database snapshot. From the configured backend environment: python -m nexus.cli backup --destination ABSOLUTE_NEW_PRIVATE_DIRECTORY --quiesced. The destination must not already exist. PostgreSQL requires pg_dump to be installed and permitted; credentials are passed in process environment, not command arguments. The minimal application image does not bundle pg_dump: run backup in an operator environment with a compatible PostgreSQL client. Encrypt, transfer and retain the output using approved external storage.

Inspect: python -m nexus.cli inspect-backup --destination BACKUP_DIRECTORY. This verifies checksums and SQLite integrity; it does not restore PostgreSQL. Test pg_restore into a new disposable database using protected connection settings; never use the live database or destructive --clean for a restore drill. Confirm schema, accounts, audit/action consistency and actual app readiness against the restored database. Record RPO/RTO and restore evidence. No automated production restore is claimed.

## Staging verification

After the approved staging endpoint is up, run the read-only preflight from the repository root. Install `backend/requirements.txt` in your operator virtual environment first.

```sh
python scripts/check_staging.py https://YOUR_REVIEWED_STAGING_HOST --expected-schema 11 > staging-preflight.json
```

The command fails if the expected schema, readiness, HSTS, pilot policy engine, OIDC configuration or anonymous access controls fail. It follows no redirects and accepts a trusted private CA with `--ca-bundle`. To verify a scrape, inject `NEXUS_STAGING_METRICS_TOKEN` from the approved secret store and add `--check-metrics`. The scrape token is used only in the metrics request header. The receipt records check results, rather than URLs, tokens, or response bodies. Keep the receipt with the environment and immutable image digest in your private release record.

| Gate | Evidence required on the target environment |
| --- | --- |
| SSO and MFA | Sign in with a pre-provisioned test user after the IdP confirms the required MFA context. Repeat with a password-only session and an unprovisioned identity. Record denial and revocation outcomes. |
| Secret management | Record the deployed secret references, access owners, and rotation test. Prove the new secret works and the previous one is rejected. Store secret values only in the approved store. |
| Monitoring and alerts | Record a passing authenticated scrape. Configure the approved monitor for failed readiness and scrape availability. Review operational thresholds for queued work and unknown outcomes if the worker is enabled. Trigger and resolve a controlled failure in staging, then record alert delivery and recovery times. |
| Database recovery | Restore a representative encrypted snapshot to a separate disposable target. Verify readiness, scoped access, and one approved business record. Record the measured recovery time and data-loss window against agreed RTO and RPO targets. |
| Release decision | Record the scope, image digest, run IDs, owners, and disposition of each gate. CI recovery and synthetic browser runs can support the record. Complete the target-specific checks before accepting the deployment. |

The hosted [PostgreSQL recovery rehearsal](../../docs/CI_POSTGRESQL_RECOVERY.md) describes the tested archive and fresh-restore procedure. The preflight receipt leaves deployment acceptance open.
