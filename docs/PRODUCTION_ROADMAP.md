# Production roadmap — 0.16.2

Generated from `backend/nexus/readiness.py` by `scripts/export_production_roadmap.py`. Update the source definitions, then regenerate these documents.

Source states: **1 implemented awaiting acceptance, 17 partial, 0 not implemented.** No deployment acceptance is granted by these source states. The 216 function previews describe the intended UI scope.

| Workstream | Source state | Remaining evidence / scope |
| --- | --- | --- |
| Customer business connectors | partial | HTTP adapter, governed supplier checks, receipt recovery, approval-bound dispatch, unsigned evidence downloads, synthetic drills and a separate developer reference gateway with scoped durable receipts are implemented. Real customer mapping, sandbox purchase/idempotency/isolation acceptance and deployment evidence remain. |
| Durable agent execution | partial | Bounded pause/resume, approvals, cancellation, one-time scheduled starts, verified-supplier allowlist conditions, lease recovery, unsigned scoped run-evidence snapshots and a disposable synthetic agent-workflow drill are implemented. Autonomous planning, customer-workflow and deployment acceptance remain. |
| Document ingestion & OCR | partial | Authorized intake, local parsers, reviewed publication, OCR controls, deletion propagation and a disposable DOCX/PDF ingestion drill are implemented. OCR quality, broader file compatibility and deployment acceptance remain. |
| Semantic retrieval & reranking | partial | ACL-first LSA/BM25, document diversity, disabled-by-default local neural ranking and scoped stored-vector build/query APIs with dashboard controls, durable receipts, invalidation, bounded multi-index search, checkpointed background builds, bounded larger-corpus collections and optional local model passage reranking are implemented. Larger-scale indexing and representative model/bilingual/reranking acceptance remain. |
| Document-level permissions | partial | Source ACL enforcement across retrieval, indexing and deletion, plus read-only exact indexed-text copy review with visibility-filtered counts. Source ACL federation and representative deployment acceptance remain. |
| Bilingual answer evaluation | partial | Reviewer-labelled keyword and saved indexed-search metrics, precision targets, saved-run and same-query indexed-review comparisons, synthetic retrieval checks and a disposable English/Arabic answer-control exercise with optional installed local Ollama are implemented. Independent generated-answer quality, grounding, refusal, broader poisoning and representative pilot acceptance remain. |
| Provider resilience | partial | Bounded response validation, elapsed-time completion checks, uncertain-outcome accounting and a disposable synthetic inference-control drill are implemented. Model-specific failure behavior, streaming/fallback if required, and live provider acceptance remain. |
| Inference traffic controls | implemented | Shared-database admission limits, concurrency reservations and saturation behavior. |
| Usage & cost governance | partial | Owner-entered selected-call statement comparison, saved discrepancy records, stale-ledger detection and owner-managed model-route admission ceilings are implemented. Provider-verified invoice/account reconciliation, retention policies and provider-account aggregation remain. |
| Identity & workload lifecycle | partial | IdP provisioning/offboarding, verified MFA and workload federation. |
| Workspace & environment lifecycle | partial | Local lifecycle, membership isolation and reviewed prompt/guardrail/workflow draft copying with pinned reference remapping and receipt recovery are implemented. Pilot lifecycle, general configuration promotion and deployment acceptance remain. |
| Secrets & network isolation | partial | Managed-secret injection, rotation and deployment-enforced egress isolation. |
| Telemetry, alerts & SLOs | partial | Environment-scoped owner threshold policies, manual database evaluations and versioned local receipts are implemented. Continuous monitoring, external logs/metrics/traces, notification delivery drills and service-objective acceptance remain. |
| Audit integrity & retention | partial | Unsigned supplier-check and workflow exports with offline format/checksum verification are implemented. Immutable off-host archive, authenticated evidence, retention rules and deployment acceptance remain. |
| Encrypted backup & recovery | partial | Quiesced snapshots, authenticated encrypted inspection, isolated SQLite recovery copies, disposable SQLite drills and a CI PostgreSQL recovery rehearsal are implemented. Scheduled encrypted backups, deployment application/PostgreSQL recovery acceptance and measured RPO/RTO remain. |
| Cloud deployment & rollback | partial | Reviewed images, TLS/private networking, staged rollout and recovery evidence. |
| Security & load acceptance | partial | Independent review, dependency/image scans, penetration and load/soak tests. |
| Accessibility & device acceptance | partial | Readable text, keyboard/screen-reader checks and responsive device assessment. |

Implementation order for a team pilot:

0. Establish reproducible builds, tests, current documentation and a recorded dependency review.
1. Implement workspace/environment lifecycle and membership isolation.
2. Connect one customer sandbox and validate approval-bound execution and recovery.
3. Complete the selected ingestion, retrieval, permissions and answer-quality scope.
4. Validate live provider behavior, budgets and cost reconciliation.
5. Connect secrets, network controls, monitoring, audit retention and tested recovery.
6. Deploy staging and complete security, load, accessibility and rollback acceptance.

Use `PRODUCTION_GAPS_0_16_0.md` for detailed release boundaries and `FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv` for individual planned functions. Historical verification reports retain their original dates; they do not prove acceptance of later revisions.
