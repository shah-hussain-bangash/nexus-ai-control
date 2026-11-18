# NEXUS AI Control: implementation and remaining phases

Release 0.4.0 | 17 November 2026 | Schema 3

## Delivered scope

A UI-first enterprise AI engineering workspace built on the existing authenticated control plane. The real application has 20 navigation views, nine persistent design asset kinds and 18 opt-in synthetic starter assets. The dashboard is backed by recorded counts rather than invented adoption, uptime or savings. The reference-inspired navy/cyan visual system, project-title sign-in, robot artwork, focus indicators, loading/error/empty states and keyboard navigation are retained and expanded.

The separate `demo-preview` is a read-only snapshot with no authentication or writes. Its data comes from isolated synthetic backend runs. The full application is `frontend/` and `backend/`.

## End-to-end dashboard map

| Area | View | Working capability | Boundary |
|---|---|---|---|
| Build | AI command center | Recorded agent/action counts, asset catalog, run evidence and navigation | No invented production telemetry |
| Build | Agent registry | Existing agent registration, status and governed identity controls | Customer workload federation remains |
| Build | Workflow Studio | Create/edit/reorder pipelines, pin references, local dry runs and traces | No LLM or external tool invocation from a dry run |
| Build | Prompt registry | Version templates, variables, deterministic assertions and rendering | No model-generated completion |
| Build | Knowledge & RAG | Save/import plain text or Markdown, English/Arabic BM25 retrieval and citations | No PDF/OCR, embedding store, semantic reranker or ACL ingestion pipeline |
| Build | Model gateway | Provider/alias/time/token configuration and credential references | Schema validation only; connections unverified |
| Build | Integration catalog | Version REST/MCP/webhook/database contracts and scopes | No generic live network connector execution |
| Govern | Tools & grants | Existing tool registry and agent grant lifecycle | Synthetic business connector |
| Govern | Safety workbench | Known override patterns, blocked terms and email block/redaction tests | Not a comprehensive jailbreak/PII detection service |
| Govern | Policy engine | Versioned deterministic/reference or configured OPA decisions | Real OPA integration not rerun this release |
| Govern | Human approvals | Exact-payload independent reviewer decisions, notes and expiry | Expired requests must be resubmitted as a new intent |
| Operate | Execution ledger | Queue, worker, outcome verification and reconciliation | Existing synthetic supplier/purchase effects |
| Operate | Traces & observability | Saved workbench steps, citations, measured local duration and JSON export | No OpenTelemetry backend, SLO/uptime history or paging integration |
| Operate | Evaluation lab | Saved retrieval cases, title recall@K and case evidence | Not answer quality, hallucination or model benchmarking |
| Operate | Policy regression | Existing repeatable policy behavior checks | Separate from retrieval benchmarks |
| Operate | AI FinOps | Saved USD token-cost scenarios and user-defined rates/limits | Planning only; no live billing or enforced spend cap |
| Operate | Security center | Existing incident records/containment actions | No SIEM or automatic threat detection |
| Operate | Audit explorer | Scoped searchable paginated audit evidence | Retention/immutable external archive requires deployment work |
| Operate | Release readiness | Saved target/rollback/checklist plans plus existing readiness endpoint | A checklist run does not deploy or certify anything |
| Operate | Workspace settings | Existing member/session/integration readiness controls | No full enterprise IdP lifecycle UI |

## Persistence and control design

WorkspaceAsset, AssetRevision and WorkbenchRun use the existing organization/environment scope. Create, edit, archive, duplicate, validate and export are implemented. Compare-and-swap version checks reject stale edits; referenced prompt/guardrail/knowledge assets are pinned to versions and stale links fail closed. Runs store the asset version and measured local duration. Citations include source, chunk, asset version and SHA-256. Audit events log references and status, not document content.

All new endpoints use the existing authenticated human-session path. Mutations require the operate permission plus CSRF; approvers and auditors inspect only. Model/connector credential fields accept environment-variable references, never actual token values; configured endpoints require HTTPS and reject userinfo, query strings and fragments. No configured endpoint is contacted in this release. These checks are not a replacement for a future managed-secret/egress implementation.

The workflow engine validates Input/Output placement and policy/independent-approval/verification boundaries around a tool step. A policy requirement halts the preview; approval is never inferred from a design checkbox. Business execution remains the existing governed Action/Approval/worker path.

## Current bounds

Assets list: latest 500; runs list: latest 100. Retrieval: at most 100 active knowledge records and 2,000 chunks. Knowledge content is limited to 24,000 characters; the API request body also has a 64 KiB limit, which can be reached sooner by multibyte text. Plain-text import is a local workbench, not a large document lake. Workflows: 2–12 ordered steps; retrieval suites: up to 30 cases. Asset retention, pagination, richer search, scheduling and high-volume ingestion are future production work.

## Remaining production phases

| Phase | Work to implement | Evidence required before calling it complete |
|---|---|---|
| 1. Live GenAI | Provider adapter, streaming, timeout/cancellation, model fallback, token accounting and failure handling | Real provider tests, secret-safe logs, rate/quota tests and cost evidence |
| 2. Enterprise RAG | Authorized ingestion, OCR/PDF pipeline, embeddings/vector storage, metadata ACLs, reranking and deletion propagation | Bilingual retrieval/answer-quality datasets, tenant-isolation and poisoning tests |
| 3. Agent execution | Durable multi-step orchestration, pause/resume, cancellation, tool registry adapter and controlled retries | Crash recovery and duplicate-effect tests; independent approval remains required |
| 4. Real integrations | Customer Nawa/FinAgent/SupplyPilot contracts, managed secrets, egress allowlists and connector sandbox | Customer-authorized end-to-end tests and permission evidence |
| 5. Reliability & cost | OpenTelemetry, metrics/alerts, SLOs, provider billing, atomic budget reservation and workload limits | Load/soak tests, alert delivery and race-condition evidence |
| 6. Production platform | Environment/workspace lifecycle, IdP lifecycle, managed PostgreSQL, backups/restore, CI/CD, IaC and staged deployment | Restore drill, rollback test, penetration/accessibility review and cloud acceptance |

These phases require customer/provider interfaces, deployment choices and measured operational evidence. They are not complete merely because a navigation view or configuration form exists. No model choice alone removes those dependencies.

## Validation

106 backend tests passed; 15 external-service tests skipped (6 PostgreSQL, 6 Keycloak, 3 OPA). Five frontend intent/retry regression tests passed. Full application and read-only preview TypeScript/Vite production builds passed. Browser inspection covered the desktop command center, workflow canvas, editor/history and recorded evaluation evidence using the separate synthetic fixture; real API writes and permissions were verified by backend tests. Native Windows 0.4.0 installation, live external services, mobile-device behavior, screen-reader audit, load tests and production recovery were not verified here.

## Portfolio positioning

The scope aligns with the supplied resume's Python/FastAPI, React/TypeScript, agentic governance, Arabic/English retrieval, evaluation and software engineering experience. Present it as an independently built AI engineering control plane with verified local capabilities. Keep planned cloud/provider capabilities distinct from demonstrated work. A strong technical project can support senior interviews; no salary or hiring result is guaranteed.
