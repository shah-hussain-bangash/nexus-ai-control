# NEXUS AI Control — 0.16.2 candidate

The current source uses database schema 11 and supports governed runtime
environment switching. Preserve your private configuration and database when
updating; older installations may require a backed-up schema upgrade. See the
[current production roadmap](docs/PRODUCTION_ROADMAP.md) for delivered scope and
remaining acceptance work.

**Cursor on Windows:** start with [CURSOR_QUICKSTART.md](CURSOR_QUICKSTART.md).
Run `npm run setup`, then `npm start` from this folder.

Enterprise Agentic AI Governance, Security & Operations Platform.

**Featured case study:** [NEXUS AI Control Case Study — governed AI execution, evidence retrieval and operational accountability](docs/case-study/NEXUS_AI_CONTROL_CASE_STUDY.md). Explore architecture decisions, independent approval, uncertain-outcome recovery, AI FinOps, source-scoped retrieval, environment isolation and inspected current CI evidence.

New working services: **local hybrid document retrieval** and **owner-controlled member/session administration**, connected to Knowledge & RAG and Workspace settings. Existing governance, approvals, execution, reviewed document intake, provider controls, business adapter and UI design workflows are retained.

Windows: follow [the Cursor quickstart](CURSOR_QUICKSTART.md) and open the URL
printed by `npm start`. Keep the API/worker terminal open. The older versioned
upgrade reports describe their original releases, not the current schema.

- [Implemented source and verification](docs/IMPLEMENTATION_REPORT.md)
- [All production gaps and ordered next work](docs/PRODUCTION_GAPS_0_16_0.md)
- [Every planned function and connected boundary](docs/FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv)
- [Local hybrid retrieval](docs/HYBRID_RETRIEVAL_0_16_0.md)
- [Hybrid completion and concurrent source changes](docs/HYBRID_COMPLETION_ORDERING.md)
- [Local ranking response validation](docs/RANKING_RESPONSE_VALIDATION.md)
- [Disposable synthetic retrieval test](docs/SYNTHETIC_RETRIEVAL_DRILL.md) — `npm run test:retrieval`
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
- [Synthetic backup-safeguard test](docs/SYNTHETIC_BACKUP_DRILL.md) — `npm run test:backup`
- [Offline backup inspection](docs/OFFLINE_BACKUP_INSPECTION.md) — inspect backups without loading application settings
- [Streaming backup checksums](docs/BACKUP_STREAMING_CHECKSUMS.md) — verify payloads using bounded reads
- [Maintenance preview](docs/MAINTENANCE_PREVIEW.md) — preview cleanup without initializing or upgrading a database
- [Request rejection events](docs/REQUEST_REJECTION_EVENTS.md) — correlate oversized-request errors in structured logs
- [All synthetic drills in one command](docs/SYNTHETIC_SUITE.md) — `npm run test:synthetic`
- [Synthetic recovered-application test](docs/SYNTHETIC_RECOVERY_DRILL.md) — `npm run test:recovery`
- [Disposable Docker recovery and restart](docs/DISPOSABLE_DOCKER_RECOVERY.md) — `npm run test:docker-recovery` from a clean checkout
- [Current UI baseline](docs/UI_BASELINE_0_16_0.json)
- [Machine-readable verification](docs/VERIFICATION.json)

The agreed design inventory remains 18 areas / 216 function previews. Design records, walkthrough roles/environments and exported review markers do not activate backend integrations. The isolated demo-preview harness blocks runtime writes; frontend and backend contain the authenticated application.

**Full enterprise production readiness is not claimed.** The current roadmap has 1 implemented workstream awaiting acceptance and 17 partial workstreams, with deployment acceptance still open. Read the current roadmap before rollout. No real customer, IdP, cloud or provider account was changed by this release.
