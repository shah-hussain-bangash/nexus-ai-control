# NEXUS AI Control 0.3.2 - local runtime fixes

14 November 2026. Enterprise Agentic AI Governance, Security & Operations Platform.

## Delivered

- Fixed the actual server-backed illustration route: root-level `nexus-agent-neon.png` and `nexus-governance.svg` are served as image files. Previously the SPA catch-all returned HTML with status 200, which explains the missing banner in the local portal screenshot.
- Missing illustration files now return 404 with a rebuild message. Unknown file requests and hidden file paths return 404; extensionless portal paths still load the SPA. Arbitrary backend files are not served.
- Added `python -m nexus.local`, a local-mode, loopback-only launcher that starts both the API and worker in one terminal. It prefers port 8000 and falls back to an available port. It retains the bound socket until Uvicorn takes over, avoiding a check-then-bind race.
- The launcher sets the actual origin for its child processes, supervises worker exit, and stops its worker when the API exits. Ctrl+C stops the managed processes. It never terminates unrelated processes occupying ports.
- Added `scripts/start.cmd` for Windows PowerShell or Command Prompt without changing execution policy. Updated PowerShell and shell wrappers to use the same launcher; Windows npm commands explicitly use `npm.cmd`.
- Worker startup prints that it is waiting for authorized queued actions. Normal processing remains silent and does not print sensitive payloads or passwords.
- Added six regression cases covering image content/MIME, missing files, SPA fallback, listener reservation, occupied-default-port fallback and a real-process local workflow.
- Preserved database schema 2, accounts, passwords and project records. No reset or authentication-policy relaxation was introduced.

## Verification for this patch

| Check | Result | Boundary |
| --- | --- | --- |
| SQLite/Python regression | 88 passed, 15 skipped, 0 failures/errors; 103 collected | Python 3.12 on Linux; six new local-runtime cases passed |
| Real API/worker process | Local owner sign-in, authenticated synthetic supplier lookup, queued action verified, Ctrl+C shutdown and port release passed | Disposable SQLite stores; stale origin overridden by launcher |
| Illustration smoke | Actual compiled PNG and SVG matched public-source bytes and correct MIME types; PNG decoded at 1536 x 1024 | FastAPI TestClient with compiled frontend; missing PNG returns 404 |
| Frontend | TypeScript/Vite build passed | Existing design preserved; new version metadata compiled |
| Windows wrappers | Supplied and reviewed | Native Windows execution was not available here; native smoke testing remains required |
| PostgreSQL/OPA/Keycloak | Historical 97-test result retained from 0.3.0 | Not rerun for 0.3.2; 6 PostgreSQL, 6 Keycloak and 3 OPA integration cases skipped in this run |

JUnit: `docs/sqlite-test-results-0.3.2.xml`. Two upstream test-dependency deprecation warnings remain. These do not change the pass/fail totals. The hosted synthetic Site was not republished; it remains a separate read-only design demonstration.

## Existing installation

Read `UPGRADE_0_3_2.md`. Stop the old API and worker, back up private configuration and both databases, then copy the release files into the existing installation without replacing runtime data. Run `scripts\start.cmd`. Open the URL printed in the terminal, and sign in with the existing password. An explicitly requested occupied port returns an error; `--port 0` requests an available port.

## Remaining work

This is an integration prototype, not a completed production platform. The earlier phase report remains applicable to enterprise scope. This patch resolves the local image/startup defects, not the remaining enterprise features.

1. Verified backup/restore and recovery procedures; scheduled operational housekeeping.
2. Redacted external telemetry and alerts; provider usage/billing and atomic budget reservations.
3. Multi-membership/environment access, assigned-object permissions, workload federation, IdP lifecycle and owner transfer.
4. General connector onboarding and an authorized customer-system integration.
5. Managed secrets, egress isolation, distributed abuse controls, cloud infrastructure and hardened audit storage.
6. Customer cloud deployment and independent security, load, accessibility and pilot acceptance reviews.

Customer integration and deployment require the selected API contract, secure credential delivery, cloud account/region and operational ownership. No completion percentage or production adoption is claimed.
