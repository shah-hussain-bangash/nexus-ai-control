# Upgrade to 0.10.0

1. Stop every NEXUS API and worker terminal with Ctrl+C. Do not run old and new workers against the same database.
2. Back up your existing project, private .env, application database and synthetic business database using your established backup procedure. Verify the backup is usable. Preserve data/ and backups/ outside the new source ZIP.
3. Extract the source to a separate review directory first. Copy the new source into C:\nexus-ai-control while preserving private .env, data, backups and existing accounts. Do not overwrite private settings with .env.example. Never delete the database to resolve an upgrade issue.
4. Start in PowerShell:

```powershell
cd C:\nexus-ai-control
.\scripts\start.cmd
```

The starter installs dependencies, builds the console, runs initialization/migrations and starts the API plus execution worker. Migration 6 adds durable_runs, durable_steps, knowledge_documents and document_chunks. Existing accounts and business records are preserved. The default database configuration remains unchanged; verify any custom NEXUS_DATABASE_URL before starting.

5. Keep the terminal open and use its newly printed URL. Hard-refresh the browser if it retains old assets. Existing owner/reviewer passwords remain your own.
6. Follow RUNTIME_QUICKSTART_0_10_0.md. Confirm Agent execution and Document library appear. A manual schema check is available from backend/: `..\.venv\Scripts\python.exe -m nexus.cli init` (idempotent migrations; does not reset accounts).

Schema 6 is required by this source. To roll back, stop all processes and restore the matching previous source plus its pre-upgrade database backup. Do not start older source directly against the migrated database. PostgreSQL/live infrastructure upgrade and restore acceptance remain operator responsibilities.
