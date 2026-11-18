# Run NEXUS AI Control 0.16.0 in Cursor on Windows

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
