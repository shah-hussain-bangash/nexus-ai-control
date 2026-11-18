# Pilot deployment candidate — not production sign-off

This profile requires an externally managed PostgreSQL database with certificate validation and an OIDC provider enforcing the configured MFA context. No database, IdP, secret manager or cloud account is provisioned automatically. Business tools are synthetic; the synthetic worker is disabled by default.

1. Build the application image using the root Dockerfile in CI; scan it and record its immutable digest. Obtain reviewed compatible Caddy 2 and OPA image digests. Never use the placeholder digests.
2. Create private runtime/deployment environment files from the supplied examples. Provision distinct runtime secrets, database connection, IdP settings and optional provider credentials through your environment. Keep private files outside source and protected by filesystem/cloud permissions. A trusted database CA may require an additional read-only volume mount and sslrootcert parameter. Provision the app-owned data volume for uid 10001.
3. Configure DNS, TLS reachability, firewall/egress rules, encrypted backups and monitoring. The profile's egress network allows outbound connections and is not an allowlist.
4. With Docker available, validate: docker compose --env-file deployment.env -f infra/pilot/compose.yaml config -q. YAML parsing in this build is not equivalent to this check.
5. After an authorized backup and maintenance window, run the migrate service once. For a brand new empty deployment, run python -m nexus.cli bootstrap with --email, --name, --organization and --oidc-subject via a one-off app container. This creates one OIDC-bound owner, no synthetic agents/tools. Do not use local init in pilot mode.
6. Start api/edge/opa and perform actual authentication, fail-closed policy, provider, load and recovery acceptance before opening access. The API has no published host port; Caddy is the TLS edge.

The profile has not been built/run here because Docker is unavailable. It is a single-host pilot template, not a managed high-availability AWS/Azure architecture. Read docs/PRODUCTION_ACCEPTANCE.md before any production claim.

## Backups

Stop API and worker before a cross-database snapshot. From the configured backend environment: python -m nexus.cli backup --destination ABSOLUTE_NEW_PRIVATE_DIRECTORY --quiesced. The destination must not already exist. PostgreSQL requires pg_dump to be installed and permitted; credentials are passed in process environment, not command arguments. The minimal application image does not bundle pg_dump: run backup in an operator environment with a compatible PostgreSQL client. Encrypt, transfer and retain the output using approved external storage.

Inspect: python -m nexus.cli inspect-backup --destination BACKUP_DIRECTORY. This verifies checksums and SQLite integrity; it does not restore PostgreSQL. Test pg_restore into a new disposable database using protected connection settings; never use the live database or destructive --clean for a restore drill. Confirm schema, accounts, audit/action consistency and actual app readiness against the restored database. Record RPO/RTO and restore evidence. No automated production restore is claimed.
