# Implementation after UI review — 0.14.0

The UI baseline covers all 216 functions. Implement and accept the agreed deployment scope phase by phase; UI review markers are not production acceptance. Existing implemented paths can be reused.

## 1 · Identity & platform foundation

Workspace, identity, access boundaries and usable global patterns. UI scope: 48 function screens.

- **Identity, SSO & workload federation**: OIDC and SAML connection design, SCIM provisioning mapping, MFA and step-up policy, Passkey enrollment lifecycle, Session and device management, Service account registry, API credential lifecycle, Role and permission matrix, Approval delegation, Emergency access request, Joiner mover leaver workflow, Access certification campaign.
- **Organizations, workspaces & environments**: Organization onboarding, Member invitation journey, Workspace membership, Project and team hierarchy, Environment creation and switch, Tenant data boundary, Workspace templates, Environment promotion, Workspace archive and restore, Branding and localization, Notification preferences, Help support and ownership.
- **Secrets, egress & isolation**: Vault reference inventory, Credential rotation plan, Envelope encryption design, TLS and certificate lifecycle, Private endpoint mapping, Outbound hostname allowlist, Proxy and outbound routing, SSRF and URL validation, Webhook trust boundary, Sensitive log redaction, Workload least privilege, Key revocation incident.
- **Accessibility, UX & device acceptance**: Information architecture review, Mobile and tablet reflow, Text contrast and zoom, Keyboard navigation journey, Screen-reader labels, Form validation and recovery, Empty loading and failure states, Arabic localization and RTL, Timezone currency and dates, Notification and live status, Contextual help and documentation, Accessibility finding workflow.

Exit evidence: reviewed user journeys and scope; implemented server/workers; role/tenant and negative-path tests; staging integration and recovery checks; operator acceptance for the selected deployment.

## 2 · Governed execution

Reviewed tools, durable execution and bounded admission. UI scope: 36 function screens.

- **Connector & MCP hub**: REST adapter mapping, MCP server discovery, Delegated OAuth connection, Webhook subscription, Tool scope binding, Idempotent dispatch review, Transport security review, Connector secret binding, Connector rate policy, Adapter version registry, Supplier sandbox contract tests, Connector decommissioning.
- **Agent runtime & orchestration**: Agent identity and capability profile, Workflow graph designer, Multi-agent delegation, Scoped agent memory, Scheduled run trigger, Event-driven run trigger, Human checkpoint and escalation, Durable checkpoint storage, Run replay and version pinning, Cancellation and compensation, Dead-letter recovery queue, Run evidence package.
- **Capacity & traffic policy**: Organization rate limits, Concurrency admission, Token throughput quota, Backpressure and queue depth, Project quotas, Priority and fairness lanes, Admission decision inspector, Budget precheck, Saturation and recovery drill, Poison-message handling, Stale-worker lease recovery, Endpoint abuse protection.

Exit evidence: reviewed user journeys and scope; implemented server/workers; role/tenant and negative-path tests; staging integration and recovery checks; operator acceptance for the selected deployment.

## 3 · Knowledge & AI quality

Reviewed sources, retrieval, model controls and measured answer quality. UI scope: 60 function screens.

- **Document ingestion & OCR**: Document upload queue, Enterprise source synchronization, Arabic and English OCR review, Table and layout extraction, Chunking strategy designer, Duplicate and content-hash review, Metadata schema mapping, Document lineage and versioning, Incremental update and deletion, Quarantine and parser failure, Index publication approval, Source retention and purge review.
- **Semantic search & reranking**: Embedding route configuration, Vector index lifecycle, Hybrid retrieval weights, Reranker experiment, Access-filtered retrieval, Citation and provenance inspector, Retrieval relevance benchmark, Retrieval cache policy, Similarity threshold review, Multilingual retrieval, Conversation context scope, Grounded answer delivery.
- **Knowledge access & data controls**: Source ACL synchronization, Document RBAC matrix, Attribute-based document policy, Tenant isolation boundary, PII detection and redaction, DLP and export controls, Data retention schedule, Legal hold case, Data subject request workflow, Consent and processing purpose, Residency and transfer boundary, Periodic access attestation.
- **AI quality & evaluation lab**: Evaluation dataset registry, Golden answer authoring, Rubric and grader configuration, Candidate and baseline comparison, Production-quality drift plan, Human feedback triage, Agent red-team scenarios, Retrieval poisoning tests, Language and bias evaluation, Release evaluation gate, Scheduled evaluation jobs, Evaluation evidence report.
- **Model routing & resilience**: Model routing registry, Circuit breaker policy, Timeout and bounded retry, Streaming response lifecycle, Batch inference plan, Multimodal model capability, Context-window management, Output and token controls, Provider model version pinning, Regional fallback boundary, Provider credential binding, Prompt registry and playground.

Exit evidence: reviewed user journeys and scope; implemented server/workers; role/tenant and negative-path tests; staging integration and recovery checks; operator acceptance for the selected deployment.

## 4 · Operational assurance

Cost controls, visibility, evidence and tested recovery. UI scope: 48 function screens.

- **AI FinOps & usage reconciliation**: Workspace budget editor, Cost reservation ledger, Provider usage ingestion, Invoice reconciliation, Chargeback cost centers, Currency and accounting period, Model price-card versions, Spend anomaly investigation, Budget forecast scenario, Showback dashboard, Budget alerts and escalation, Billing evidence export.
- **Observability, alerts & service objectives**: Distributed trace explorer, Span and dependency waterfall, Structured log search, Service metrics dashboard, Service-level objective editor, Alert rule designer, On-call routing, Maintenance and alert silence, Incident response timeline, Runbook and mitigation steps, Escalation and acknowledgement, Notification delivery review.
- **Audit archive & evidence integrity**: Audit event search, Signed evidence export, Off-host archive destination, Immutable retention policy, Cross-service correlation, Control and evidence mapping, Compliance review package, Custodian archive access, Audit payload redaction, Legal hold evidence, Archive integrity verification, Evidence chain investigation.
- **Backup, restore & continuity**: Backup scheduling, Backup encryption references, Recovery point inventory, Incremental backup chain, Isolated restore drill, Regional failover rehearsal, PostgreSQL recovery procedure, RPO and RTO measurement, Backup expiry and deletion, Restore approval workflow, Recovery runbook steps, Recovery evidence and lessons.

Exit evidence: reviewed user journeys and scope; implemented server/workers; role/tenant and negative-path tests; staging integration and recovery checks; operator acceptance for the selected deployment.

## 5 · Deployment & acceptance

Controlled delivery and verified deployment acceptance. UI scope: 24 function screens.

- **Cloud delivery, environments & rollback**: Build artifact registry, Software bill of materials, Image vulnerability gate, Deployment approval, Database migration review, Canary rollout designer, Rollback and release recovery, Feature flag lifecycle, Infrastructure change plan, Environment configuration diff, Certificate and domain readiness, Release monitoring and sign-off.
- **Security, performance & resilience testing**: Threat model registry, Dependency vulnerability scan, Static analysis campaign, Dynamic API assessment, Penetration test scope, Tenant and role isolation tests, Load and capacity campaign, Soak and resource leak tests, Chaos and dependency failure, Finding remediation workflow, Risk exception review, Retest and release evidence.

Exit evidence: reviewed user journeys and scope; implemented server/workers; role/tenant and negative-path tests; staging integration and recovery checks; operator acceptance for the selected deployment.

## Cross-cutting release gate

Supply approved identity/customer sandboxes, cloud/private network configuration, secret/key custody, monitoring/notification targets, retention and recovery policy, and security/load/accessibility/restore evidence. Remaining software is tracked in IMPLEMENTATION_REPORT.md and IMPLEMENTATION_MATRIX.csv. No default acceptance gates were passed by this UI release.
