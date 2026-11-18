# Upgrade to 0.3.2

This patch fixes the local robot-image route and startup experience. Database schema remains **2**. It does not reset users, passwords, actions or audit records.

## Preserve your existing installation

1. Stop your existing API and worker using Ctrl+C in their respective terminals. Leave unrelated services alone.
2. While stopped, make a private backup of `backend/.env` and both databases. For the default local configuration, copy `backend/data/`; for custom database paths or PostgreSQL, use the configured stores and your reviewed backup method.
3. Extract the new ZIP to a separate temporary folder. Copy its source files and built frontend into your existing `C:\nexus-ai-control` folder. Preserve your `.env`, `data/` and `.venv/`. They are excluded from this archive. Read the new files before running them.
4. From the existing project root, run:

```powershell
cd C:\nexus-ai-control
.\scripts\start.cmd
```

This installs the pinned backend dependencies, rebuilds the frontend, initializes/migrates the schema idempotently, and launches the API and worker. Existing accounts and passwords are retained. Do not re-create the workspace or delete databases to upgrade.

## Quick restart after dependencies and build are already updated

```powershell
cd C:\nexus-ai-control\backend
..\.venv\Scripts\python.exe -m nexus.local
```

Open the exact URL printed in the terminal, rather than an old bookmarked port. Both processes use the same backend working directory and configuration. Keep this terminal open. Ctrl+C stops this launcher's processes. It does not stop old instances or unrelated applications.

If you need a particular available port, pass `--port 64315`; an explicitly occupied port produces an error. With no argument, port 8000 is preferred and an available port is selected if needed. `--port 0` always selects an available port. The bound socket is retained during startup to avoid a port-selection race.

The loopback launcher is restricted to local mode. Customer/pilot hosting still needs its configured HTTPS origin, identity provider, policy service and database.

## Check the result

- Use your existing owner password. The upgrade does not generate a replacement for an existing user.
- The robot banner should load. Open `/nexus-agent-neon.png` at the printed origin to inspect the image directly; a missing illustration now returns 404 instead of app HTML. Refresh the browser if it is showing an older frontend.
- Submit a synthetic supplier lookup. Refresh the portal after the worker has had a moment to process it; its status should become Verified, or an explicit failure/blocked/unknown result requiring inspection.
- For a purchase requiring approval, sign in as the independent reviewer before expecting dispatch. Queued, pending approval and denied are different states.
