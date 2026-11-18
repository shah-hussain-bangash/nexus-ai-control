# Production roadmap — 0.16.2

Generated from `backend/nexus/readiness.py` by `scripts/export_production_roadmap.py`. Update the source definitions, then regenerate these documents.

Source states: **1 implemented awaiting acceptance, 16 partial, 1 not implemented.** No deployment acceptance is granted by these source states. The 216 function previews describe the intended UI scope.

| Workstream | Source state | Remaining evidence / scope |
| --- | --- | --- |
| Customer business connectors | partial | Real API adapters, sandbox contract tests and approval-bound dispatch. |
| Durable agent execution | partial | Pause/resume, cancellation and worker crash recovery for multi-step agents. |
| Document ingestion & OCR | partial | Authorized ingestion jobs, parsing, OCR and deletion propagation. |
| Semantic retrieval & reranking | partial | Local ACL-first LSA/BM25 retrieval is implemented. Neural embeddings/vector indexing, scalable retrieval, reranking and bilingual relevance acceptance remain. |
| Document-level permissions | partial | Source ACL enforcement across retrieval, indexing and deletion. |
| Bilingual answer evaluation | partial | Answer-quality, grounding, refusal and poisoning regression datasets. |
| Provider resilience | partial | Model-specific failure behavior, streaming/fallback if required, and live provider acceptance. |
| Inference traffic controls | implemented | Shared-database admission limits, concurrency reservations and saturation behavior. |
| Usage & cost governance | partial | Invoice reconciliation, evidence retention and account-level cost controls. |
| Identity & workload lifecycle | partial | IdP provisioning/offboarding, verified MFA and workload federation. |
| Workspace & environment lifecycle | not_implemented | Create/switch environments with controlled membership and isolation tests. |
| Secrets & network isolation | partial | Managed-secret injection, rotation and deployment-enforced egress isolation. |
| Telemetry, alerts & SLOs | partial | External logs/metrics/traces, service objectives and operator notification drills. |
| Audit integrity & retention | partial | Immutable off-host archive, retention rules and evidence export verification. |
| Encrypted backup & recovery | partial | Scheduled encrypted backups, PostgreSQL restore and measured RPO/RTO. |
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
