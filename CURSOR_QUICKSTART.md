# Run NEXUS AI Control in Cursor on Windows

The current source uses schema 11. Before upgrading an older installation, stop all
API/workers, make and inspect a private backup, then follow the environment and session
upgrade notes in `docs/PHASE_1_ENVIRONMENT_FOUNDATION.md` and
`docs/PHASE_1_SESSION_CONTEXT.md`. Fresh setup uses the current schema automatically.

This package includes the original full source plus Windows setup/run commands,
Cursor tasks, and a Python debug configuration. No paid API key is needed for
the default local workspace. Live model inference requires separate provider setup.

## 1. Open the project

Extract the ZIP to a normal writable folder. In Cursor, use File > Open Folder
and select `nexus-ai-control`, the folder containing this guide and `package.json`.
Install Python and Node.js if they are missing, and reopen Cursor after installation.
The verification environment used Python 3.14 and Node.js 24.

## 2. Set up once

Open Cursor's terminal using a Command Prompt profile and run:

```cmd
npm run setup
```

In a PowerShell terminal, use `npm.cmd run setup` if script execution blocks `npm`.
Setup creates `.venv`, installs Python and frontend dependencies, builds the UI,
and initializes the local database. Keep the generated password printed in the
terminal. Secrets are created in `backend/.env`; don't copy the root `.env.example`
over it. Rerunning setup preserves existing accounts and data.

## 3. Start

```cmd
npm start
```

Open the URL printed after `Starting NEXUS at:` and sign in as `owner@nexus.local` with the password
printed during setup. Reviewer and auditor accounts use `reviewer@nexus.local`
and `auditor@nexus.local`. Keep the terminal open; Ctrl+C stops API and worker.

The launcher uses port 8000 when available and automatically chooses another
available port if 8000 is occupied. To explicitly request an available port, run
this in Cursor's PowerShell terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/cursor.ps1 -Action Run -Port 0
```

Open the URL printed by the launcher. Use its exact `127.0.0.1` address for login.

## Cursor tasks and debugging

Terminal > Run Task offers NEXUS Setup, Run, Build frontend, and Test tasks.
Run Setup once before debugging. Install the Python and Python Debugger extensions
if needed, select `NEXUS: Debug API and worker` in Run and Debug, then press F5.

After editing frontend code, run `npm run build` and refresh the browser.
Restart the server after backend changes.

## Tests

```cmd
npm test
```

This installs development Python dependencies, then runs the backend and frontend
tests. Optional integration tests need their external services and configuration.

## Reset a forgotten local password

To replace the local owner's email and password together, run `npm.cmd run account`
from the project root in an interactive terminal. Press Enter for the current
`owner@nexus.local` email, then enter your own email and a new app password twice.
Passwords stay hidden while you type. Existing records are preserved and previous
sessions are revoked. This updates the local app login, without sending email or
changing your email provider account.

In Cursor's PowerShell terminal, from the project root:

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m nexus.cli set-local-password --email owner@nexus.local
```

Follow the password prompts. Existing records are preserved.

## Run the disposable synthetic connector drill

```powershell
npm.cmd run test:connector
```

This runs 15 checks covering supplier lookup, independent purchase approval,
duplicate-request protection, timeout reconciliation and workspace isolation in a
temporary synthetic workspace. It preserves your existing accounts, records and
connector settings. No customer credentials or running server are required. The
command prints a report path in the ignored `backend/data/drills` folder. See
`docs/SYNTHETIC_CONNECTOR_DRILL.md` for the checks, exit codes and limits.

## Run the disposable synthetic retrieval drill

```powershell
npm.cmd run test:retrieval
```

This runs 18 checks covering Arabic normalization, source isolation, precision
targets, matching saved-run comparisons, replay/recovery and revoked/deleted
sources. It creates a temporary workspace and preserves your existing accounts,
documents and settings. Keep your app open. No password, report path or customer
connection is required. The command prints the saved report path in the ignored
`backend/data/drills` folder. See [the retrieval drill guide](docs/SYNTHETIC_RETRIEVAL_DRILL.md)
for exit codes and scope limits. Passing this synthetic exercise does not establish
generated-answer quality or production readiness.

## Run the combined knowledge drill

```powershell
npm.cmd run test:knowledge
```

This runs all 18 keyword checks plus 18 local hybrid-search checks, using the real
isolated ranking worker in a separate disposable workspace. It covers related-word
retrieval, Arabic text, saved search recovery, source access changes, stale citations
and explicit vocabulary limits. Existing data and settings are preserved. See
[the knowledge drill guide](docs/SYNTHETIC_KNOWLEDGE_DRILL.md) for the 36 checks and
the limits of this synthetic exercise.

## Run the disposable file-ingestion drill

```powershell
npm.cmd run test:ingestion
```

This runs 25 checks with synthetic DOCX/PDF files and the real local extraction
worker. It covers review before publication, provenance, source access, replay,
cancellation, parser limits and deletion without resurrection. Your existing
data and settings are preserved. No files or passwords are required. See
[the ingestion drill guide](docs/SYNTHETIC_INGESTION_DRILL.md) for the checks and
the limits of this synthetic exercise; OCR quality is not tested.

## Run the disposable agent-workflow drill

```powershell
npm.cmd run test:agents
```

This runs 24 checks across durable pause/resume, independent workflow and business
approvals, uncertain-outcome cancellation/reconciliation, workspace isolation and
simulated review/claim expiry. It uses fresh synthetic accounts and databases;
your existing app, records and settings remain separate. See
[the agent drill guide](docs/SYNTHETIC_AGENT_DRILL.md) for exit codes, fault
injection details and limits. No customer credentials or report path are needed.

## Run the disposable inference-control drill

```powershell
npm.cmd run test:inference
```

This runs 27 checks for input guardrails, budget reservations, uncertain provider
outcomes, replay/recovery, reconciliation and workspace isolation. It uses an
in-process API, fresh accounts/databases and an HTTP mock transport. No provider
key, report path or running server is required; your existing settings and data
are preserved. See [the inference drill guide](docs/SYNTHETIC_INFERENCE_DRILL.md)
for simulated deadline/pending states, exit codes and limits. No provider or
customer system is contacted.

## Run the disposable backup-safeguard drill

For encrypted recovery followed by in-process login, record and permission checks,
run `npm.cmd run test:recovery`. Its 31 checks use fresh disposable databases and
an in-memory key; your running app can stay open. See
[the recovery drill guide](docs/SYNTHETIC_RECOVERY_DRILL.md). It exercises a separate
synthetic copy without restoring your active database or certifying deployment recovery.

```powershell
npm.cmd run test:backup
```

This runs 27 checks using temporary SQLite databases and a fresh, disposable
encryption key. It checks snapshot records, authentication, wrong keys, tampering,
malformed archives, overwrite prevention and cleanup. No existing backup or key
is needed; your running app and settings are untouched. See
[the backup drill guide](docs/SYNTHETIC_BACKUP_DRILL.md) for exit codes and limits.
This inspects temporary backups; it does not restore the active application.

## Verify a downloaded supplier evidence report

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run evidence:verify -- 'C:\path\to\supplier-evidence.json'
```

Replace the example path with the downloaded report. This command checks the saved
format and checksum offline. It does not open the application database, upload the
file or contact a supplier. A valid file can still describe a pending/uncertain check;
`lookup_verified` reports that distinction. An unsigned checksum does not prove who
created the report or establish customer acceptance. See
`docs/GOVERNED_SUPPLIER_CHECKS.md` for expected-scope options and exit codes.

## Included source and limits

- `backend/nexus`: API, authentication, governance, document retrieval and workers.
- `frontend/src`: React/TypeScript authenticated application.
- `sdk`: Python client and integration example.
- `infra`, `policies`, `contracts`: deployment and integration resources.
- `demo-preview`: isolated UI demonstration, separate from the live application.

Local defaults use SQLite, synthetic business tools and reference policy evaluation.
External SSO, OPA, PostgreSQL, OCR, provider inference and customer connectors require
their own configuration. The original release has unfinished enterprise workstreams;
216 UI design previews do not mean 216 implemented services. See
`docs/PRODUCTION_GAPS_0_16_0.md` for the supplied project's scope.
