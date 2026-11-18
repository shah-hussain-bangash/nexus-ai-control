# NEXUS AI Control — 0.7.0 enterprise UI release

Enterprise Agentic AI Governance, Security & Operations Platform.

UI-first delivery for every one of the 18 defined production roadmap areas: 161 configuration fields, 54 planned action contracts, 18 operational record surfaces and seven sections per module (126 module sections). The portal now has 21 primary navigation views. Existing sign-in and working control-plane capabilities are retained.

Open **Enterprise design studio**, choose a module and review Overview → Configuration → Operations surface → Workflow preview → API handoff → Acceptance → History. Local owners can load the 18 additive synthetic examples. Save revisions to retain planning metadata. A UI review never activates runtime services or grants production acceptance.

Read [UI_COVERAGE_MATRIX.md](docs/UI_COVERAGE_MATRIX.md), [UI_IMPLEMENTATION_SEQUENCE.md](docs/UI_IMPLEMENTATION_SEQUENCE.md), and [UPGRADE_0_7_0.md](docs/UPGRADE_0_7_0.md). The real app uses backend/ and frontend/. demo-preview/ is an isolated, interactive in-memory interface preview: reload discards edits; legacy runtime mutations are blocked.

Production runtime acceptance remains open. The existing roadmap still has six missing, eleven partial and one source-implemented workstream awaiting acceptance. UI coverage is a separate measure. No cloud deployment or live external service validation was performed.

---

# NEXUS AI Control — 0.6.0 readability and operational workflow release

**Enterprise Agentic AI Governance, Security & Operations Platform.**

This release improves text visibility across the sign-in and 20-view portal, adds a larger-text mode, and introduces a scoped production readiness board, database-backed inference admission, paginated request history and same-tab reload recovery.

**Full platform production acceptance remains open.** The [18-workstream roadmap](docs/PRODUCTION_ROADMAP.md) records six unimplemented enterprise workstreams, eleven partial workstreams and one implemented source item awaiting production acceptance. These counts cover the production-extension roadmap; existing delivered control-plane features remain available.

Read [UPGRADE_0_6_0.md](docs/UPGRADE_0_6_0.md) before staging installation. Database schema advances to 5 and existing accounts/records are preserved. Keep your current installation unchanged if you require full production acceptance before updating. Live provider execution stays disabled by default; copied private settings can explicitly enable it.

The real app is backend/ plus frontend/. demo-preview/ is a separate read-only synthetic fixture with no real login or writes. Current evidence is in docs/VERIFICATION.json. Historical setup and earlier release notes follow.

---

# NEXUS AI Control — 0.5.0 production engineering build

**Enterprise Agentic AI Governance, Security & Operations Platform.**

This release adds an explicitly enabled provider execution console, atomic operator-priced monthly budget reservations, idempotent request evidence, uncertainty reconciliation, backups and runtime hardening to the 20-view engineering workspace.

**This is not a complete production-ready enterprise release.** The current acceptance report lists both missing software and missing deployment evidence. Keep your current installation unchanged if you want to update only after all production gates are closed.

Read [PRODUCTION_ACCEPTANCE.md](docs/PRODUCTION_ACCEPTANCE.md), [IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md), [MODEL_RUNTIME.md](docs/MODEL_RUNTIME.md) and [UPGRADE_0_5_0.md](docs/UPGRADE_0_5_0.md). Database schema advances to 4. Live provider execution defaults to OFF and no credentials are bundled.

For local staging use the existing Windows scripts\start.cmd or Linux bash scripts/start.sh. Preserve your private configuration and data during upgrade. The real application is frontend/ plus backend/. The separate demo-preview/ uses read-only synthetic fixtures; it cannot send provider requests or save edits.

Historical setup and release notes follow. Their schema/status descriptions refer to those older versions, not this release.

---

# NEXUS AI Control — Engineering workspace 0.4.0

**Enterprise Agentic AI Governance, Security & Operations Platform.**

This release expands the portal into 20 engineering views, with versioned workflows, prompts, bilingual knowledge, safety workbenches, evaluation evidence, provider/connector contracts, cost scenarios and release plans. It retains the independent approval and synthetic execution worker.

**Start with [START_HERE.txt](START_HERE.txt). Existing installation: read [UPGRADE_0_4_0.md](docs/UPGRADE_0_4_0.md) first. Database schema advances to 3.**

The new workbench functions use the real authenticated backend and persistent database. Provider configuration is not a live LLM integration; workflow dry runs do not execute external tools. This is a substantial local engineering foundation, not a certified enterprise production system. See [the current implementation report](docs/IMPLEMENTATION_REPORT.md) for precise capabilities and remaining phases, and [the portfolio demonstration guide](docs/FLAGSHIP_DEMO_GUIDE.md).

On first sign-in as owner, choose **Load synthetic starter designs** to add 18 editable templates. This is opt-in and additive; existing users and business records are preserved.

The standalone `demo-preview/` is an explicitly read-only synthetic UI fixture. It has no real authentication and cannot perform business actions. Use `backend/` plus `frontend/` for the full application.

---

## Historical release notes and setup instructions

# Release 0.3.3 - explicit tool selection and correct new-intent submissions

Run governed action now requires an explicit business tool, shows purchase fields only for purchases, and reports the actual action reference/status. Successful new submissions get fresh intent keys; uncertain retries preserve their key while the UI remains loaded. This fixes repeated identical submissions returning an old record with a misleading generic toast. Clean npm installation, five frontend regression cases and the TypeScript/Vite build passed. See **docs/RELEASE_0_3_3.md** for upgrade steps and validation boundaries. Approval expiry, role controls and schema 2 are retained.

# Release 0.3.2 - reliable local startup and illustration serving

The API now serves the robot PNG and governance SVG as actual images. The local launcher starts the API and worker together, reserves an available loopback port, and prints the correct browser URL. Windows users can run `scripts\start.cmd` without changing PowerShell execution policy. See **docs/RELEASE_0_3_2.md** for changes, verification boundaries and remaining phases; existing installations should use **docs/UPGRADE_0_3_2.md**.

# Release 0.3.1 - reference-matched sign-in and portal

NEXUS now uses the uploaded design's dark blue, cyan/violet lighting, glass panels, AI robot and colored feature tiles. Real interface text remains sharp and accessible. See docs/RELEASE_0_3_1.md for the artwork prompt, visual changes and validation scope. Functional scope and remaining enterprise phases remain as documented for 0.3.0 below.

# Release 0.3.0 - UI, audit navigation and operations

Enterprise Agentic AI Governance, Security & Operations Platform (NEXUS AI Control).

The redesigned sign-in includes the full project title and an original SVG governance illustration. The portal adds quick navigation (Ctrl/Cmd+K), operations readiness, paginated audit search and owner-only member revocation. Expired sessions, OIDC state and exports can be cleaned with a dry-run/apply CLI.

Existing installation: read **docs/UPGRADE_0_3_0.md** before replacing source or running maintenance. The database schema remains version 2. The complete application is in backend/ and frontend/; demo-preview/ is a separate read-only visual demo.

This is a tested integration prototype. See **docs/IMPLEMENTATION_REPORT.md** for current implemented scope and remaining enterprise work. Historical release notes below describe earlier milestones.

# NEXUS AI Control

A runnable, independently built integration prototype of the NEXUS agent-action control plane. Professional React/TypeScript sign-in and portal, FastAPI backend, persistent SQLAlchemy data, scoped workload identity, deterministic policy decisions, independent approval and a durable execution worker.

**Status: tested local synthetic MVP, not an enterprise production release.** The included implementation report identifies implemented, partially implemented and remaining phases. Never use the synthetic mock connector to claim real customer integration, payments or production adoption.

## Release 0.2.0 - PostgreSQL and SSO continuation

This release adds schema upgrades, encrypted server-side PKCE verifiers, single-use sign-in state, issuer/JWKS/context validation, private-CA support and real-service test harnesses. Read `docs/UPGRADE_0_2_0.md` before upgrading existing data. The phase report and JUnit files define the actual verified scope.

## Start here

Requirements: Python 3.12+, Node.js 22+ (npm), and Internet access for dependency installation. Docker is optional. No paid model-provider account is needed for the core application.

### Windows PowerShell

Extract the ZIP and open PowerShell inside `nexus-ai-control`:

```powershell
.\scripts\start.cmd
```

The script installs dependencies, builds the portal, initializes the local schema, starts the worker and serves the app. It prints three development accounts and a **randomly generated password** on first setup. Save that output privately. There is no committed default password.

Open the **http://127.0.0.1:PORT** address printed by the launcher. It uses port 8000 when available and another port if occupied. Sign in as `owner@nexus.local`. Sign out and use `reviewer@nexus.local` to independently approve a request. `auditor@nexus.local` can inspect/export evidence. These are synthetic development accounts only.

The `.cmd` wrapper works from PowerShell or Command Prompt; the optional `start.ps1` wrapper is also included. Both start the same local runtime. Keep the terminal open; Ctrl+C stops its API and worker.

### macOS / Linux

```sh
bash scripts/start.sh
```

### Manual setup (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm.cmd ci
npm.cmd run build
cd ..\backend
..\.venv\Scripts\python.exe -m nexus.cli init
..\.venv\Scripts\python.exe -m nexus.local
```

For an existing built installation, the last command is sufficient. To request an available port explicitly use `python -m nexus.local --port 0` with your virtual-environment interpreter. The launcher sets the origin for its child processes; there is no need to copy a port into `NEXUS_ORIGIN`.

Advanced manual operation remains supported. If you start Uvicorn separately instead of using `nexus.local`, start the worker in a second terminal from `nexus-ai-control\backend`:

```powershell
..\.venv\Scripts\python.exe -m nexus.worker
```

The worker is necessary and is started automatically by `nexus.local`. `Queued` means accepted, not executed. Without a worker a manually hosted API deliberately leaves requests queued. Worker startup now prints a clear message; it does not log action payloads or passwords.

For manual macOS/Linux commands, substitute `.venv/bin/python`, `../.venv/bin/python` and normal `/` paths. For frontend development use `npm run dev` in `frontend`; API proxying is configured for port 8000.

## Your first complete workflow

1. Sign in as the owner; open Agent registry and inspect Procurement Atlas and its explicit grants.
2. Run a governed purchase request for USD 12,500. It requires independent approval.
3. Inspect its canonical payload, policy version, expiry and SHA-256 fingerprint.
4. Sign out. Sign in as reviewer and approve with a note.
5. The worker rechecks authorization and executes the exact synthetic action. Open Executions to inspect its verified result and event trail.
6. Run USD 30,000: it is denied without calling the tool. Run a purchase with Supplier Scout: missing grant denies it.
7. Run USD 2,400 with `Timeout after commit`: the worker records Outcome unknown. Open the action and reconcile. It finds the original mock business record without creating a duplicate.
8. Open Evaluations to run actual policy-boundary checks. Open Audit explorer as owner/auditor to create a scoped, expiring JSON evidence export.

## What works

- Password-hashed local login; server-side revocable sessions and CSRF protection.
- Role enforcement and tenant-scoped object access; signed per-agent workload tokens with generation revocation.
- Draft registration; scoped grants; activation, suspension, rotation and containment.
- Typed supplier/purchase arguments, immutable action envelopes and deduplication keys.
- Reference policies and a real fail-closed OPA adapter with versioned thresholds.
- Payload-bound independent approvals, expiry and atomic decision conflict handling.
- Persisted queue, separate worker, lease recovery, mock connector idempotency and result verification/reconciliation.
- Live dashboard, audit timeline, owner-scoped export, real runtime policy evaluations and transparent limitations.
- Versioned schema upgrades, optional PostgreSQL/OPA Compose composition, Python SDK, optional LangGraph adapter, CI definition and backup utility.

## Source map

```text
backend/nexus/    Configuration, SQLAlchemy schema, auth, API, policies, worker
backend/tests/    Security, workflow, recovery and OPA integration tests
frontend/src/    React/TypeScript portal and responsive design system
policies/        Rego policy and OPA unit cases
sdk/             Workload client and optional LangGraph example
scripts/         Startup, Compose secret generation and local backup
infra/           Optional local Keycloak fixture and deployment boundaries
docs/            Implementation report, test evidence and reference designs
```

The built frontend is included in the archive for convenience; startup still rebuilds from source. Source and lockfile are authoritative. The ZIP excludes databases, `.env`, virtual environments, node_modules, generated runtime credentials and temporary visual-QA authentication fixtures.

## Verification

```sh
cd backend
../.venv/bin/python -m pip install -r requirements-dev.txt
../.venv/bin/python -m pytest
```

On Windows use `..\.venv\Scripts\python.exe`. The optional real OPA integration requires `OPA_BIN` pointing to a trusted OPA executable. Without it, those integration cases are skipped explicitly.

```sh
OPA_BIN=/absolute/path/to/opa ../.venv/bin/python -m pytest
opa test ../policies -v
```

Frontend: `cd frontend && npm ci && npm run build`. API reference: `/api/docs`. OpenAPI JSON: `/openapi.json`. See `docs/INTEGRATION_TESTS.md` for the real-service matrix.

## Optional local Docker composition

```sh
python scripts/prepare_compose.py
docker compose up --build
```

Generated root `.env` holds unique Compose secrets. Initial development credentials appear in the init service log. PostgreSQL is private to Compose; only the API is bound to `127.0.0.1:8000`. This composition is supplied but was not executed for this delivery. It requires a Docker daemon, image access and validation in your environment. Do not expose it publicly.

## Important limits

- The local workflow uses a synthetic business store, not a customer API or managed secret service.
- OIDC BFF source and a Keycloak fixture are supplied; the real Keycloak protocol and configured TOTP flow are now covered by integration tests. Production IdP policy still requires customer validation.
- the backend suite is exercised against a real isolated PostgreSQL 16.2 server as well as SQLite. The Docker Compose topology itself remains unexecuted.
- One staging environment and one workspace per user; guided onboarding and multi-membership switching remain expansion work. Audit cursor pagination is implemented.
- Audit intent is durable in SQL. This is not certified immutable storage, external OpenTelemetry/Langfuse integration, or regulatory compliance.
- Provider usage/billing, hard budget reservations, scheduled retention/deletion, real notifications, cloud Terraform/HA and an independent security review remain open.
- The native local mock store has no public execution endpoint, but true gateway network isolation must be validated in deployment.
- A dispatch authorization commit is the cutoff: suspension cannot undo an external call already dispatched.
- Concurrent duplicate submissions may return a conflict; retry the **same** idempotency key to resolve the original logical intent. Do not generate a new key after a network timeout.
- For real data, review payload visibility/redaction, database permissions, connector endpoint validation, distributed rate limits, request-size limits, concurrency and disaster recovery.

Read `docs/IMPLEMENTATION_REPORT.md` before planning a pilot. No completion percentage is presented because enterprise readiness is gated by evidence, not screen count.
