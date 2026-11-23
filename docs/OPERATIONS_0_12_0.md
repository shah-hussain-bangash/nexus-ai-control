# Metrics and encrypted backup operations — 0.12.0

## Current operating signals

Open Release readiness → Runtime signals. Counts are scoped to the signed-in organization/staging environment. Refresh explicitly to sample current database state. They do not prove a worker is alive or establish request latency, alert delivery or SLO compliance.

To enable aggregate Prometheus-format database gauges, provision NEXUS_METRICS_TOKEN with at least 32 characters through the server secret store. A monitoring collector must send it in X-Nexus-Metrics-Token when scraping /metrics. Do not put it in URLs, a browser form, public configuration or screenshots. Export is disabled without the token; ordinary browser sessions are not a substitute for that monitoring credential. Metrics intentionally have fixed status labels without tenant/record IDs. Secure the scrape route on your private network and configure your monitoring/alert service separately.

## Encrypted backup and inspection

Provision NEXUS_BACKUP_ENCRYPTION_KEY as base64-encoded 32 random bytes through your protected secret store. Keep recoverable key custody separate from the archive and test recovery access. A lost key makes the archive unreadable; do not generate a throwaway key that will disappear with the shell. Never include the key inside this source or backup archive.

Stop every API/worker writer first. Use a private encrypted destination filesystem with appropriate Windows ACLs; the command uses private temporary plaintext snapshots and normal cleanup cannot guarantee secure erasure after a crash. Then from the backend directory:

```powershell
cd C:\nexus-ai-control\backend
..\.venv\Scripts\python.exe -m nexus.cli backup-encrypted --destination C:\private-backups\nexus-2026-11-17.enc --quiesced
..\.venv\Scripts\python.exe -m nexus.cli inspect-encrypted-backup --destination C:\private-backups\nexus-2026-11-17.enc
```

Create the private parent directory first. Commands never overwrite an existing archive. The 512 MiB archive limit is explicit; use reviewed large-database tooling above it. SQLite snapshots and optional synthetic business data are included. PostgreSQL creation requires operator-provisioned pg_dump as with the existing backup path. Credentials stay out of subprocess arguments.

Inspection authenticates AES-GCM before extracting safe members into a temporary inspection directory, then checks the manifest and SQLite integrity. It never overwrites the active application database. This is not a full PostgreSQL restore test or a measured recovery-time/recovery-point objective. Schedule backups, retain encrypted off-host copies, rotate keys, manage retention and perform isolated database/application restore drills before production acceptance. Keep the normal plaintext backup command only for an already protected workflow; upgrading does not encrypt older files.

Current manifest validation requires a supported database kind, positive schema version and a nonempty matching control snapshot (`control.sqlite3` or `control.dump`). File declarations must have unique safe names, byte counts and SHA-256 checksums; members must be regular files rather than symbolic links. Inspection compares declared sizes/checksums and verifies the SQLite control snapshot's recorded schema version. An empty manifest, a missing snapshot, or successful encryption authentication alone cannot pass inspection. Plaintext workflows may include additional declared operator artifacts such as `runtime.env`; encrypted archives retain their existing restricted member layout. PostgreSQL payload checksums do not validate dump contents or prove a restore, and SQLite integrity/schema metadata do not establish complete application recovery.

Encrypted archive member validation is incremental: it stops on the first unsafe resolved member or the fifth member, retaining at most four accepted entries. The full archive is still authenticated before tar parsing, and no files are extracted until the allowed member layout is validated. The existing 512 MiB archive/payload limits remain in force. This bounds resolved file-list enumeration; it does not change the archive format or certify arbitrary tar metadata/resource behavior or a complete database restore.

## Remaining operational acceptance

An isolated SQLite copy can be created from a validated encrypted backup without replacing active data. See [isolated recovery instructions](ISOLATED_SQLITE_RECOVERY.md) for the fresh-directory requirement, explicit process key injection, partial-copy behavior and remaining cutover acceptance. This operation does not start the application or claim a verified application restore.

SQLite snapshot creation and inspection also run `PRAGMA foreign_key_check` after physical integrity checks, covering each SQLite control/business payload's declared relationships. Orphaned references and invalid foreign-key definitions cannot produce a successful backup/inspection/recovery result even when file hashes and encryption authentication are valid. Existing result fields and archive formats are unchanged. Source data is never repaired or altered by these checks; errors omit private constraint details. A failed plaintext backup may leave incomplete files in its new directory without a manifest, following the existing snapshot-failure behavior; inspect privately and use a new destination for a later attempt. Encrypted backup failures clean their normal temporary workspace and publish no archive. Undeclared relationships, cross-database consistency and full deployment recovery still require separate acceptance.

Both plaintext and encrypted backup creation require a destination with no existing final directory entry. Existing files, directories and symbolic links (including dangling links) are rejected before resolving that final name, preventing a dangling destination link from redirecting backup creation. Metadata lookup errors fail closed. Only the parent is resolved; parent links and concurrent parent-directory replacement remain outside this safeguard, so use a protected parent directory. Exclusive final directory/file creation still rejects a destination created after validation. Plaintext backup retains its existing ability to create missing parents; encrypted backup requires the parent to exist already. Inputs, archive formats, encryption keys and success response fields are unchanged. This follows [Python's distinction between absolute paths, link resolution and non-following metadata lookup](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.lstat).

Choose the cloud account/region/private network, IdP/MFA policy, secret service, monitoring and notification destinations, immutable audit archive, backup retention and measured RPO/RTO. Run deployment-specific security/load/device/accessibility reviews. Source tests are engineering evidence, not approval to deploy sensitive customer workloads.
