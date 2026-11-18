# Production release blockers — 0.16.0

18 November 2026. **The complete enterprise platform is not production-ready.** This source adds working backend capability and connected UI; it does not complete every enterprise feature or certify a deployment.

The source-defined roadmap has 18 workstreams: **1 implemented awaiting acceptance, 16 partial, 1 not implemented; zero accepted by default**. These are workstream states, not a completion percentage. The UI catalog has 216 function previews; a working-view link does not prove its entire planned feature is implemented. FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv preserves every catalog item and its exact implementation note.

| Workstream | Working source | Remaining software | Required deployment/acceptance |
| --- | --- | --- | --- |
| Customer business connectors (partial) | Fixed-contract HTTPS business adapter; approval/payload/destination binding; synthetic default. | General protocol/OAuth mappings and enterprise ERP/CRM adapters; retries/webhooks as required. | Customer sandbox contract, credentials, reconciliation and change approval. |
| Durable agent execution (partial) | Persistent bounded multi-step execution, checkpoints, approval pause, cancellation and worker recovery. | General graph/branch/parallel/scheduler architecture and connector-specific compensation. | Long-running crash/restart/duplicate-effect drills at target scale. |
| Document ingestion & OCR (partial) | Reviewed text/PDF/DOCX intake, bounded extraction and optional OCR worker. | Enterprise source sync, malware scanning, complete parser sandbox, broader document fidelity and retention automation. | Real document corpus, Arabic OCR quality and security review. |
| Semantic retrieval & reranking (partial) | NEW: ACL-first local LSA/BM25 ranking, current citations, score controls and scoped history. | Persistent scalable vector retrieval, chosen neural embedding/reranking paths, cache and relevance evaluation. | Representative English/Arabic relevance, access-change, deletion and load acceptance. |
| Document-level permissions (partial) | Organization/document ACLs, pre-retrieval filtering and source revision checks. | Federated source ACL sync, index-delete propagation and enterprise access lifecycle. | Tenant/ACL attack cases with the deployed identity and sources. |
| Bilingual answer evaluation (partial) | Saved lexical retrieval checks and existing policy regression surfaces. | Generated-answer grounding/refusal/poisoning and bilingual evaluator/dataset workflows. | Curated labeled datasets and acceptable quality thresholds. |
| Provider resilience (partial) | Controlled OpenAI/Azure request path with recorded outcomes and cost reservation. | Provider-specific streaming/failover/circuit-breaker behavior where required. | Actual provider timeout/quota/error/unknown-cost acceptance; no live provider contacted here. |
| Inference traffic controls (implemented) | Shared-database admission, rate/concurrency reservations and saturation controls. | Source implementation exists for this defined gate; distributed deployment acceptance remains. | PostgreSQL/multi-worker load, fairness, quota and recovery evidence. |
| Usage & cost governance (partial) | Budgets, cost reservations, usage records and bounded admission. | Provider invoice reconciliation, allocation/chargeback, pricing governance and retention. | Actual billing reconciliation and unknown-cost recovery evidence. |
| Identity & workload lifecycle (partial) | NEW: owner preprovisioning, exact configured OIDC subject binding, role/activation changes, session revocation and local password CLI. Existing OIDC flow retained. | SCIM/SAML, passkeys, workload federation, delegated/owner-transfer review and invitation delivery. | Real IdP login/MFA/revocation and joiner/mover/leaver acceptance. |
| Workspace & environment lifecycle (not_implemented) | Fixed organization scoping and staging environment; design-only workspace/environment views. | Create/switch/promote/archive organizations/environments with membership scoping and cross-environment isolation. | Environment ownership, region/residency policy and isolation tests. This lifecycle capability is not implemented. |
| Secrets & network isolation (partial) | Configuration validation, HTTPS adapter restrictions and server-only secrets boundaries. | Managed secret-store integration, rotation orchestration and deployment-enforced network policy. | Approved secret manager, KMS/IAM/egress/private-network validation. |
| Telemetry, alerts & SLOs (partial) | Structured HTTP logs, metrics endpoint and runtime signal views. | Off-host traces/log/metric pipeline, alert routing, paging and SLO burn-rate automation. | Actual observability stack, incident notification and alert-delivery drills. |
| Audit integrity & retention (partial) | Scoped audit events and existing evidence export/integrity paths. | Immutable off-host archive, legal holds, retention/deletion lifecycle and archive verification. | Object-lock/retention configuration and export/tamper acceptance. |
| Encrypted backup & recovery (partial) | Encrypted AES-GCM backup generation/inspection and tamper/wrong-key tests. | Scheduled off-host backup, managed key lifecycle, restore orchestration and failover automation. | Actual PostgreSQL restore and measured RPO/RTO; none performed here. |
| Cloud deployment & rollback (partial) | Deployment/CI/configuration assets and local startup worker supervision. | Environment-specific infrastructure and staged rollout/rollback integration. | Approved AWS target, TLS/DNS/private networking, deployment and rollback/restore evidence. |
| Security & load acceptance (partial) | Security-oriented API tests, source checks and CI assets. | Resolve findings and add deployment-specific load/soak/abuse and dependency/image gates. | Independent penetration/security review and realistic multi-worker load evidence. |
| Accessibility & device acceptance (partial) | Light/dark UI, larger text, dialogs/labels, contrast corrections and sampled desktop inspection. | Complete device/RTL/screen-reader validation, bespoke advanced editors where needed and findings remediation. | Formal keyboard/screen-reader/WCAG/device acceptance; sample inspection is not certification. |

## Ordered implementation path

1. Close the missing workspace/environment lifecycle and extend identity/workload access using an agreed tenant and deployment architecture. Do not turn preview selectors into claims of tenant switching.
2. Implement the selected enterprise retrieval and source-sync stack, broader connector contracts and required agent graphs/schedules. Validate generated-answer/bilingual quality separately from source ranking.
3. Connect managed secrets, network isolation, observability/paging, immutable evidence retention, cost reconciliation and automated recovery.
4. Deploy to the approved target, run the external PostgreSQL/Keycloak/OPA suites, conduct security/load/accessibility acceptance and demonstrate restore/rollback. Only then assess the scoped production release.

## What can be completed from source, and what needs the deployment

The unimplemented/partial software above still needs engineering; credentials alone do not implement it. Cloud account/region/networking, IdP issuer/subjects/MFA, customer sandbox contracts, data-residency/retention requirements, provider billing and agreed SLO/RPO/RTO are also needed for real acceptance. None is silently selected or enabled by this ZIP. All work possible in this pass used isolated disposable data. No live provider, real staff permissions, customer endpoint or cloud resource was changed.

## Verification for this release

- Backend full regression: 303 tests, 288 passed, 15 skipped, zero failures/errors. Skips: PostgreSQL 6, Keycloak 6, OPA 3.
- New search/member paths: 20 tests passed in the full suite. Updated catalog/readiness targeted checks: 33 passed after catalog metadata changes.
- Frontend: 51 tests passed; console and isolated preview production builds passed.
- Sample browser QA: search controls and saved real-backend synthetic receipt results, member directory and provisioning dialog, light/dark label contrast, protected owner display, current session display and no document-level horizontal overflow at a 1348px viewport. Runtime writes are blocked in the visual harness.
- No native Windows, formal security/load/accessibility, real provider/IdP/customer/cloud acceptance or PostgreSQL restore was performed.

See VERIFICATION.json, test-results-0.16.0.xml, HYBRID_RETRIEVAL_0_16_0.md, IDENTITY_LIFECYCLE_0_16_0.md and UPGRADE_0_16_0.md.
