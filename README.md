# NEXUS AI Control — 0.16.2 candidate

The current source uses database schema 11 and supports governed runtime
environment switching. Preserve your private configuration and database when
updating; older installations may require a backed-up schema upgrade. See the
[current production roadmap](docs/PRODUCTION_ROADMAP.md) for delivered scope and
remaining acceptance work.

**Cursor on Windows:** start with [CURSOR_QUICKSTART.md](CURSOR_QUICKSTART.md).
Run `npm run setup`, then `npm start` from this folder.

**Phase 1 connector development:** the [synthetic Business v1 reference gateway](docs/PHASE1_BUSINESS_REFERENCE.md)
provides scoped, persistent operation receipts and a developer example through
`npm run dev:business-reference`. It does not connect or accept a customer system.

**Local pilot on this PC:** follow [local pilot acceptance](docs/LOCAL_PILOT_ACCEPTANCE.md).
Use `npm run pilot:check` for read-only checks and `npm run test:answers:local`
for the small synthetic English/Arabic Ollama exercise. Automated passes do not
grant customer or production acceptance.

Enterprise Agentic AI Governance, Security & Operations Platform.

**Featured case study:** [NEXUS AI Control Case Study — governed AI execution, evidence retrieval and operational accountability](docs/case-study/NEXUS_AI_CONTROL_CASE_STUDY.md). Explore architecture decisions, independent approval, uncertain-outcome recovery, AI FinOps, source-scoped retrieval, environment isolation and inspected current CI evidence.

New working services: **local hybrid document retrieval** and **owner-controlled member/session administration**, connected to Knowledge & RAG and Workspace settings. Existing governance, approvals, execution, reviewed document intake, provider controls, business adapter and UI design workflows are retained.

Windows: follow [the Cursor quickstart](CURSOR_QUICKSTART.md) and open the URL
printed by `npm start`. Keep the API/worker terminal open. The older versioned
upgrade reports describe their original releases, not the current schema.

- [Implemented source and verification](docs/IMPLEMENTATION_REPORT.md)
- [Durable run evidence snapshots](docs/DURABLE_RUN_EVIDENCE.md)
- [Workflow attention filter](docs/DURABLE_RUN_ATTENTION.md)
- [One-time durable workflow start](docs/DURABLE_SCHEDULED_START.md)
- [Bounded supplier allowlist condition](docs/DURABLE_SUPPLIER_CONDITION.md)
- [Offline workflow report verification](docs/OFFLINE_RUN_EVIDENCE.md)
- [All production gaps and ordered next work](docs/PRODUCTION_GAPS_0_16_0.md)
- [Every planned function and connected boundary](docs/FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv)
- [Local hybrid retrieval](docs/HYBRID_RETRIEVAL_0_16_0.md)
- [Combined local-pilot integration review](docs/PILOT_INTEGRATION_REVIEW.md)
- [One result per document](docs/RETRIEVAL_SOURCE_DIVERSITY.md)
- [Read-only identical indexed-text review](docs/DOCUMENT_COPY_REVIEW.md)
- [One result per document in keyword search](docs/LEXICAL_SOURCE_DIVERSITY.md)
- [Saved quality checks for document-diverse search](docs/RETRIEVAL_DIVERSITY_EVALUATION.md)
- [Hybrid completion and concurrent source changes](docs/HYBRID_COMPLETION_ORDERING.md)
- [Local ranking response validation](docs/RANKING_RESPONSE_VALIDATION.md)
- [Disposable synthetic retrieval test](docs/SYNTHETIC_RETRIEVAL_DRILL.md) — `npm run test:retrieval`
- [Offline English and Arabic answer review](docs/SYNTHETIC_ANSWER_EVALUATION.md) — synthetic fixtures, citation checks and response-bound reviewer labels
- [Combined synthetic knowledge test](docs/SYNTHETIC_KNOWLEDGE_DRILL.md) — `npm run test:knowledge`
- [Synthetic file-ingestion test](docs/SYNTHETIC_INGESTION_DRILL.md) — `npm run test:ingestion`
- [File-worker completion deadlines](docs/INGESTION_COMPLETION_DEADLINES.md)
- [Extraction response validation](docs/EXTRACTION_RESPONSE_VALIDATION.md)
- [Members, roles and sessions](docs/IDENTITY_LIFECYCLE_0_16_0.md)
- [Paused agent-review expiry](docs/PAUSED_REVIEW_EXPIRY.md)
- [Durable worker claim deadlines](docs/DURABLE_CLAIM_DEADLINES.md)
- [Synthetic agent-workflow test](docs/SYNTHETIC_AGENT_DRILL.md) — `npm run test:agents`
- [Synthetic inference-control test](docs/SYNTHETIC_INFERENCE_DRILL.md) — `npm run test:inference`
- [Local Ollama connection](docs/LOCAL_OLLAMA.md) — opt-in local models without a provider API key
- [Document-backed model answers](docs/DOCUMENT_INFERENCE.md) — opt-in source excerpts with current access/version checks
- [Synthetic backup-safeguard test](docs/SYNTHETIC_BACKUP_DRILL.md) — `npm run test:backup`
- [Offline backup inspection](docs/OFFLINE_BACKUP_INSPECTION.md) — inspect backups without loading application settings
- [Streaming backup checksums](docs/BACKUP_STREAMING_CHECKSUMS.md) — verify payloads using bounded reads
- [Maintenance preview](docs/MAINTENANCE_PREVIEW.md) — preview cleanup without initializing or upgrading a database
- [Request rejection events](docs/REQUEST_REJECTION_EVENTS.md) — correlate oversized-request errors in structured logs
- [Offline recovery evidence checker](docs/OFFLINE_RECOVERY_EVIDENCE.md) — inspect a provided version-2 evidence pack without running NEXUS
- [All synthetic drills in one command](docs/SYNTHETIC_SUITE.md) — `npm run test:synthetic`
- [Synthetic recovered-application test](docs/SYNTHETIC_RECOVERY_DRILL.md) — `npm run test:recovery`
- [Disposable Docker recovery and restart](docs/DISPOSABLE_DOCKER_RECOVERY.md) — `npm run test:docker-recovery` from a clean checkout
- [Current UI baseline](docs/UI_BASELINE_0_16_0.json)
- [Machine-readable verification](docs/VERIFICATION.json)

The agreed design inventory remains 18 areas / 216 function previews. Design records, walkthrough roles/environments and exported review markers do not activate backend integrations. The isolated demo-preview harness blocks runtime writes; frontend and backend contain the authenticated application.

**Full enterprise production readiness is not claimed.** The current roadmap has 1 implemented workstream awaiting acceptance and 17 partial workstreams, with deployment acceptance still open. Read the current roadmap before rollout. No real customer, IdP, cloud or provider account was changed by this release.
