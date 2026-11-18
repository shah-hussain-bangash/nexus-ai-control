# Runtime implementation report — 0.10.0

17 November 2026 | Database schema 6 | Production acceptance: not granted.

## Working source added

**Persisted agent execution.** The new Agent execution dashboard creates 2–12-step bounded workflows with input checkpoints, governed actions, optional independent human checkpoints and an output record. Definitions, payload hashes, requesting agent generation, step state, action links and verified external references persist in the database. The existing worker processes both action outbox and workflow checkpoints. Existing supplier/purchase actions use the synthetic business connector; arbitrary scripts, autonomous LLM planning and customer adapters are not enabled.

Operator controls include pause, resume, cancellation and narrowly guarded retry. Pause stops new checkpoints; an already submitted action may finish. Cancellation withdraws queued or approval-pending actions and their pending approval records. An executing or uncertain action remains tracked until its outcome is known; cancellation cannot undo external effects. Verified results are preserved even after cancellation. Retry is offered only for a failed step with no submitted action. Unknown outcomes require the existing reconciliation path and are never blindly replayed.

A version check rejects stale control/review requests. A database claim and fencing token protect worker ownership; expired leases recover up to three times. Waiting-action polls do not continually change the record version. Run creation is idempotent per organization/author/key and capped at 50 active workflows per organization. Independent workflow review expires after 30 minutes, binds to the immutable definition, requires the approve permission and forbids the requesting author from approving. Purchase policy review is a separate second gate; workflow review does not replace it. Agent generation and active operator permission are rechecked before new work.

**Authorized text evidence.** Document library accepts UTF-8 TXT, MD, CSV and JSON files up to 32 KiB, with format validation, content hash, language, persisted content and deterministic chunks (700 characters with 80-character overlap). It supports at most 200 active documents per organization. Upload is idempotent. Files are not executed. PDF, OCR, images, embeddings, vector search and model-generated answers are outside this implementation.

Reader access requires the source author, organization owner/security administration, an explicit role grant or an explicit active user grant in the same organization. Read permission does not grant ACL management or deletion: only author or policy-capable administration can manage a source. Tenant and current source ACL filtering occur before lexical BM25-style ranking, and search returns document/version/chunk citations. English and Arabic Unicode tokens are supported. This is lexical retrieval, not semantic search or a bilingual answer-quality certification. This ACL path applies to the new document store; old workspace knowledge assets are not silently migrated into it.

ACL changes and deletion require current version plus a visible note. Deletion removes active document content and chunks, retains a metadata tombstone/audit record and makes the source unavailable to retrieval. It is logical active-store removal, not guaranteed physical erasure from database pages, WAL, backups or exported copies. Deployment retention, encryption and backup deletion policies must be implemented separately. Stored text is plain database content; use approved deployment encryption and data policies before sensitive intake. Audit events omit document content.

**Dashboard integration.** Two actual runtime workspaces bring primary navigation to 24 views. Selected design functions link to their bounded working workspace and state what remains. Run timelines show checkpoint state, action links and evidence. Document screens show file/version/hash, current content, access controls, deletion and cited search. Existing larger-text mode, responsive layouts and design studio remain available.

**Safe request recovery.** Create/upload intents retain only an idempotency key, SHA-256 body fingerprint and timestamp in same-tab sessionStorage scoped by organization and user. The payload and file text are not stored there. Uncertain network/server outcomes keep the key; a changed body is blocked until the pending request is reconciled. Definite validation failures allow correction. Recovery APIs require session authentication and CSRF, return only the requesting author's record and do not dispatch or ingest again. This is not cross-device recovery.

## Verification

The release evidence records 247 backend tests: 232 passed, 15 skipped, zero failures/errors. The skipped tests require PostgreSQL (6), Keycloak (6) or OPA (3); those integrations were not accepted by local SQLite tests. Frontend tests: 31 passed. Both frontend and isolated preview builds pass. See VERIFICATION.json and the included logs/JUnit report.

Focused checks cover both independent approvals, crash lease recovery, three-worker SQLite contention, immutable definition rejection, generation revocation, stale revisions, author-scoped intent recovery, cancellation of queued/pending/unknown actions, no unknown-effect replay, document ACL changes, tenant separation, reader management denial, Arabic retrieval and source deletion. SQLite concurrency evidence does not establish PostgreSQL HA or production throughput.

Browser review used an isolated synthetic harness: run timeline and verified action reference, supervised procurement fields, document search/citation/source inspection, access dialog and readable larger-text desktop view. The 1363px viewport had no document overflow. Runtime API writes were tested against disposable real backend databases, not faked through the preview. Native Windows, mobile/screen reader, load/soak, penetration and live restore/cloud acceptance were not run.

## Remaining production work

The source roadmap has 18 workstreams: **1 implemented in source awaiting acceptance, 14 partial and 3 not implemented**, with zero acceptance gates automatically passed. These are workstream states, not a completion percentage. The 216 design definitions are not 216 implemented live services.

- Real customer REST/MCP/webhook adapters, OAuth provisioning, sandbox contracts and approval-bound external effects.
- General workflow graphs, durable schedules, delegation, compensation, dead-letter operations and approved autonomous model orchestration beyond the bounded sequence implemented here.
- Enterprise connectors/source synchronization, large/asynchronous intake, PDF/layout parsing, OCR, quarantine, deletion propagation to external indexes and retention/legal-hold workflows.
- Embeddings/vector/hybrid retrieval, reranking, ACL synchronization, grounded generation and measured Arabic/English answer-quality datasets.
- Full identity/workload provisioning, SCIM/SAML acceptance, environment lifecycle and organization switching.
- Managed secrets/rotation, enforced private networking and egress, off-host telemetry, notification/on-call drills and tamper-resistant audit retention.
- Scheduled encrypted PostgreSQL backup/restore/failover with measured RPO/RTO; cloud rollout/rollback and reviewed deployment evidence.
- Independent security review, dependency/image scanning, penetration/load/soak/chaos and device/accessibility acceptance for the agreed deployment.

Production readiness requires those applicable requirements to be implemented and verified in a named deployment. This release makes real backend progress and preserves the remaining design plan; it does not claim all remaining enterprise functions are complete.
