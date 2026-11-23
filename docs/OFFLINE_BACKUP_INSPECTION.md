# Offline backup inspection

Backup inspection can run when the application's settings are missing or invalid. Both inspection commands return before loading `Settings`, reading `.env`, opening the configured application database, migrating or seeding it. They inspect only the chosen backup input. They do not activate a recovered application or replace live data.

From the backend directory, with the input path assigned by your operator workflow:

```powershell
python -m nexus.cli inspect-backup --source "$nexusBackupDirectory"
python -m nexus.cli inspect-encrypted-backup --source "$nexusEncryptedArchive"
```

Use the first command for a private plaintext backup directory and the second for an encrypted archive. The existing `--destination` spelling remains accepted as an input-path alias for these two inspection commands. Choose exactly one of `--source` or `--destination`; neither or both is an argument error. Creation commands still use `--destination`, validate application settings and require quiescence acknowledgement.

Encrypted inspection requires `NEXUS_BACKUP_ENCRYPTION_KEY` injected directly into the inspection process through your protected secret workflow. It does not load this key from `.env` or fall back to the application's settings. If an earlier inspection command obtained its key from `.env`, explicitly inject that same existing key before using this version; do not generate a replacement key. Never put a key in a command argument, source file or shared transcript. Missing or wrong keys fail inspection rather than returning a success report.

The existing checksum, manifest bounds, SQLite integrity and declared foreign-key checks remain. Encrypted inspection authenticates the archive and cleans its normal temporary plaintext directory; this is not secure erasure. Inspection output retains its existing fields and does not claim PostgreSQL restore, application cutover or measured RPO/RTO. Protect the input and temporary filesystem and keep inspection away from concurrent writers. The separate isolated SQLite recovery-copy command also remains independent of application settings.

Regression tests use disposable archives, SQLite snapshots and fixture keys, including a broken `.env` and separate real CLI subprocesses. They require unchanged fixture files, no initialized application database, no configuration loading and successful inspection with the explicitly injected process key. No existing operator backups or active data are used.
