# Upgrade to 0.11.0

1. Stop all NEXUS API/worker terminals with Ctrl+C. Do not run old/new workers together against one database.
2. Back up the existing source, private .env, application database, business database and retained data. Verify your backup. Preserve accounts, data/ and backups/ when copying the new source.
3. Extract the new ZIP to review it, then copy source into C:\nexus-ai-control. Never overwrite private settings with .env.example, delete the database or rerun account resets to fix an upgrade.
4. Start PowerShell:

```powershell
cd C:\nexus-ai-control
.\scripts\start.cmd
```

The starter builds the console, applies forward migrations and runs API plus worker. Schema 7 adds document_updates (idempotent metadata receipts) and retrieval_checks (saved private queries/results). It preserves existing accounts, documents, chunks and agent runs. The schema 6 → 7 preservation test is included. A manual migration from backend/ can use `..\.venv\Scripts\python.exe -m nexus.cli migrate`.

5. Keep the terminal open and use its new printed URL. Hard-refresh old browser assets if necessary. Existing passwords remain unchanged. Follow DOCUMENT_LIFECYCLE_0_11_0.md with synthetic content.

Rollback requires stopping processes and restoring matching pre-upgrade source plus database backup. Older source must not serve a schema-7 database. Live PostgreSQL migration/restore and native Windows acceptance remain deployment responsibilities.
