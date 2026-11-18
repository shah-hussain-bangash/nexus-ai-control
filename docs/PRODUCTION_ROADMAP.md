# Production roadmap: 18 workstreams

Release 0.12.0 | 17 November 2026 | Schema 7

Source states: **2 not implemented, 15 partial, 1 implemented awaiting production acceptance**. No acceptance evidence is automatically populated. These workstream states are not a completion percentage. The 216 UI designs remain a long-term scope, not live backend service counts.

Working bounded orchestration and UTF-8 document ACL/search now move three workstreams from missing to partial. General agent autonomy, enterprise ingestion/OCR and broader source permission synchronization remain open. See IMPLEMENTATION_REPORT.md for exact boundaries.

| # | Workstream | Source delivery | Remaining acceptance scope |
|---|---|---|---|
| 1 | Customer business connectors | partial | Real API adapters, sandbox contract tests and approval-bound dispatch. |
| 2 | Durable agent execution | partial | Pause/resume, cancellation and worker crash recovery for multi-step agents. |
| 3 | Document ingestion & OCR | partial | Authorized ingestion jobs, parsing, OCR and deletion propagation. |
| 4 | Semantic retrieval & reranking | not implemented | Embedding/vector retrieval, ranking and repeatable relevance evidence. |
| 5 | Document-level permissions | partial | Source ACL enforcement across retrieval, indexing and deletion. |
| 6 | Bilingual answer evaluation | partial | Answer-quality, grounding, refusal and poisoning regression datasets. |
| 7 | Provider resilience | partial | Model-specific failure behavior, streaming/fallback if required, and live provider acceptance. |
| 8 | Inference traffic controls | implemented | Shared-database admission limits, concurrency reservations and saturation behavior. |
| 9 | Usage & cost governance | partial | Invoice reconciliation, evidence retention and account-level cost controls. |
| 10 | Identity & workload lifecycle | partial | IdP provisioning/offboarding, verified MFA and workload federation. |
| 11 | Workspace & environment lifecycle | not implemented | Create/switch environments with controlled membership and isolation tests. |
| 12 | Secrets & network isolation | partial | Managed-secret injection, rotation and deployment-enforced egress isolation. |
| 13 | Telemetry, alerts & SLOs | partial | External logs/metrics/traces, service objectives and operator notification drills. |
| 14 | Audit integrity & retention | partial | Immutable off-host archive, retention rules and evidence export verification. |
| 15 | Encrypted backup & recovery | partial | Scheduled encrypted backups, PostgreSQL restore and measured RPO/RTO. |
| 16 | Cloud deployment & rollback | partial | Reviewed images, TLS/private networking, staged rollout and recovery evidence. |
| 17 | Security & load acceptance | partial | Independent review, dependency/image scans, penetration and load/soak tests. |
| 18 | Accessibility & device acceptance | partial | Readable text, keyboard/screen-reader checks and responsive device assessment. |

## Retained runtime engineering from 0.6.0

1. A real, scoped readiness evidence API with version checks, guarded owner/security writes and audit events. Recording a pass does not change source delivery status. Missing capabilities cannot be marked passed through the API.
2. Shared-database, per-organization inference admission: default 30 admitted requests per rolling minute and 4 pending dispatches within a 300-second window. Settings are operator-controlled. Rejected new intents roll back their ledger row and reservation. Replaying an existing intent does not consume another admission or dispatch.
3. Signed, organization/query/status-bound keyset pagination and search for inference evidence, with a page-size cap of 25 and expiring cursors. The UI displays 10 records per page and exports only the selected page.
4. Same-tab reload recovery: only the idempotency key, SHA-256 payload fingerprint and timestamp are retained in sessionStorage, keyed by organization/user. The recovery API requires session authentication and CSRF, returns only the requesting author's record and never dispatches a provider call. Request text and credentials are not retained in this recovery record.
5. Dashboard readability: a 12px small-text floor, 14px default body text, an optional 16px body/15px navigation mode, stronger table text, larger controls, responsive card spacing and separate Readiness board / Release plans / Runtime signals tabs with keyboard navigation.

## Completion order

Prioritize a real customer connector and durable approval-bound orchestration; then authorized enterprise RAG and answer evaluation; then identity/workspace lifecycle and managed egress/secrets; then external telemetry/audit retention/recovery; finally cloud rollout and independent security/load/accessibility acceptance. Provider-specific streaming and fallback are scope decisions; they are not universal requirements for all production workloads.

Production readiness requires implementation and evidence for the agreed deployment scope. No production-ready sign-off is issued by this release.

## 0.8.0 interface layer

All 18 workstreams now have dedicated operational UI rehearsals. This does not change the runtime delivery states above. Read UI_COVERAGE_MATRIX.md for UI coverage and IMPLEMENTATION_REPORT.md for boundaries.

## 0.9.0 long-term function design

The Platform function map now includes 216 feature-screen definitions across the existing 18 modules, including the missing and partial runtime capabilities. This expands UI scope and keeps the runtime delivery states unchanged. See LONG_TERM_UI_MASTER_SPEC.md.


## 0.10.0 real runtime extension

Agent execution and Document library are actual API-backed workspaces. Only the explicitly linked bounded functions have a working path; the broader feature designs remain planned. Counts above supersede prior historical release counts. Production acceptance remains open.

## 0.11.0 document lifecycle and evidence

Version-checked source replacement, current citation verification and persisted lexical retrieval checks are working. This strengthens partial document/evaluation paths without implementing embeddings/vector retrieval or LLM grading. Source delivery counts and zero default accepted gates remain unchanged.

## 0.12.0 adapter, recovery and clarity

Fixed-contract HTTPS dispatch/reconciliation, destination binding, operating gauges and encrypted backups are implemented in source. Customer sandbox, external identity/cloud/monitoring and restore acceptance remain open. The UI now has light/dark appearance and larger readable text. Current source counts above supersede historical release counts.
