# Isolated SQLite recovery copy

`recover-encrypted-sqlite` authenticates an encrypted NEXUS backup, validates its SQLite snapshot and copies only its declared files into a brand-new plaintext directory. It never activates that database, changes runtime settings, migrates a schema, starts the application or replaces an existing path. PostgreSQL payloads are rejected before the destination is created.

This is an operator recovery building block, not full application restore acceptance. The source must be a quiesced encrypted backup created by the existing backup workflow. Supply its existing key through `NEXUS_BACKUP_ENCRYPTION_KEY` in the recovery process environment using your protected secret store. This operation deliberately does not load `.env` or validate the active application's settings, so broken app configuration does not prevent an isolated copy. It does not invent or rotate a recovery key.

Choose an existing protected parent directory on an appropriately encrypted filesystem. The final destination directory must not exist, including as an empty directory, regular file or dangling link. Windows ACLs and storage protection remain operator responsibilities. Temporary decrypted inspection files stay on the chosen parent filesystem and are cleaned normally; cleanup is not secure erasure.

From the backend directory, after your operator workflow has assigned the two path variables and injected the key privately:

```powershell
python -m nexus.cli recover-encrypted-sqlite --source "$nexusArchive" --destination "$nexusRecoveryDirectory"
```

`$nexusArchive` identifies the existing encrypted input file. `$nexusRecoveryDirectory` identifies the new, separate directory to create. Neither variable is filled in automatically. Do not select the running app's data directory. No recovery operation against your existing user data was performed while implementing or testing this feature; tests use disposable databases and keys.

Authentication and complete backup-manifest validation occur before allocating the destination. Creation is exclusive even if another process creates the path during authentication. Payload files are also created exclusively with private permissions; the manifest is copied last. Only the validated manifest's declared files are exported, excluding incidental SQLite journal companions. The copied payload is checked again before success is returned.

SQLite control and business snapshots must pass both physical integrity and declared foreign-key checks. A checksummed, authenticated snapshot with an orphaned reference or an invalid foreign-key definition is rejected before recovery allocates its destination. Checks do not repair or delete records and errors exclude private table names and row identifiers. These checks cover declared SQLite constraints, not undeclared application relationships or cross-database business consistency. SQLite documents that [integrity checking does not check foreign keys](https://www.sqlite.org/pragma.html#pragma_integrity_check); a separate `foreign_key_check` is required.

The final verification uses SQLite's immutable read mode only on this newly created, offline copy, avoiding generation of WAL/SHM companion files. The ordinary inspector's default behavior is unchanged. Immutable mode skips locking/change detection and assumes no writer can change those files during verification; protect the directory and do not run an application against it concurrently. See [SQLite's URI documentation](https://www.sqlite.org/uri.html#uriimmutable) for that mode's assumptions.

Successful output includes `isolated_copy_created: true`, `authenticated: true`, the destination and copied-file count. It deliberately retains `restore_verified: false`, `application_started: false`, `active_data_overwritten: false` and `postgresql_restore_verified: false`. An authentication, layout or manifest failure creates no destination. A copy/write/sync/final-verification failure returns an error; its partial new directory may remain for protected local review. The command never deletes that directory or unrelated files and does not retry into it. A later attempt needs a different new destination after operator investigation.

Before any real cutover, separately review runtime secrets, session validity, schema compatibility, workload/connector destinations, isolated application startup, record/business consistency and rollback. Off-host retention, key custody, full application/PostgreSQL restore and measured RPO/RTO remain unaccepted. These file-copy checks do not certify production recovery.

For a repeatable rehearsal using only disposable data, run `npm.cmd run test:recovery` from the project root. The [synthetic recovery drill](SYNTHETIC_RECOVERY_DRILL.md) creates an encrypted fixture, copies it to a new directory and exercises that copy through an in-process API. It never opens your existing backups or starts the recovered copy as a live server. The file-copy command's response remains unchanged and does not claim this separate rehearsal's application checks.
