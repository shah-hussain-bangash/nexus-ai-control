# Current implementation and remaining work

Release 0.5.0 | 17 November 2026 | Schema 4 | **Production-ready status: not achieved.**

The 20-view engineering workspace from 0.4.0 remains. Its full view matrix is retained at archive/0.4.0/IMPLEMENTATION_REPORT.md. This release replaces the earlier “no provider execution” boundary with a separate, explicitly enabled inference runtime. Workflow Studio and its Test bench remain deterministic dry runs; they do not invoke an LLM or business connector.

## Newly implemented

| Capability | Actual implementation | Verification / limit |
|---|---|---|
| Live provider adapter | OpenAI / classic Azure OpenAI v1 text chat, operator host allowlist, dedicated secret prefix, no redirects or proxy-env inheritance | Controlled transport tested; no live credentials supplied |
| Cited generation path | Optional local BM25 excerpts supplied alongside the question; output and citation evidence retained | Lexical retrieval only; no vector store/OCR/document ACL pipeline |
| Provider spending controls | Operator-priced, per-organization UTC monthly reservation ledger in integer micro-USD; conditional atomic update | SQLite contention tested; current PostgreSQL integration not run |
| Usage evidence | Exact saved model version, provider token usage, request reference, local duration and returned answer | Latest 50 calls shown; no full retention/pagination or invoice integration |
| Retry safety | Idempotency key plus author/payload fingerprint; no automatic retries | Keys must be retained after uncertain outcomes; browser reload does not persist draft keys |
| Uncertainty handling | Reservation retained on timeout/status/parse failure; owner can reconcile evidence once | Operator checks provider usage; unresolved pending calls need 300-second grace |
| Role separation | Engineer invokes checked routes; owner/security activates models and maintains guardrails | Scoped authenticated API + CSRF; workbench rules are deterministic, not comprehensive safety classification |
| Request boundary | 64 KiB body limit also covers chunked requests; capped provider output and timeouts | Not a distributed WAF or organization-wide rate limiter |
| Request observability | Generated request ID and structured route/status/duration events without request bodies or credentials | Logs require external collection; no metrics stack/SLO/paging installed |
| Backups | Quiesced SQLite snapshots or PostgreSQL custom pg_dump; checksums, restrictive local permissions, integrity inspection | SQLite snapshot read/restore integrity tested; PostgreSQL dump/restore not run; encryption/retention external |
| Pilot deployment profile | Non-root/read-only API, capability drop, OPA internal network, Caddy TLS edge, explicit image digest variables | YAML parsed only; not Docker/Compose tested, not cloud deployed |
| Identity bootstrap | Empty database creates one OIDC-bound owner and organization without synthetic agents/tools | Real IdP/MFA acceptance still required |

## Runtime boundaries

The live endpoint sends request text and optionally selected retrieved excerpts to the configured provider. Outputs are stored in the organization's inference ledger and visible to authorized workspace readers. Do not enter employer/customer data before reviewing data handling, retention and provider approval. No business action is authorized by a model response. Raw prompts and credentials are not written to HTTP logs or inference audit details; response/citation content is deliberately persisted for replay and review.

Rates are supplied by the server operator as USD per million tokens for an exact host/model key. UI cost-scenario assets cannot change these rates or the runtime limit. Reservations use UTF-8 byte length plus 2,048 tokens of envelope allowance, and the requested maximum output. This is a conservative engineering bound, not a provider invoice guarantee. If provider-reported usage exceeds the reservation, the ledger records the charge even if it exceeds the configured budget; subsequent reservations fail when capacity is exhausted. Charges omit taxes, non-token fees and other applications using the same provider account. Enforce account-level controls separately.

Live calls are synchronous, non-streaming and text-only. There is no automatic fallback, tool calling, distributed cancellation, background provider job queue, custom endpoint adapter, Anthropic adapter or local-model execution. The generic connector catalog remains configuration only. The business worker still targets the synthetic supplier/purchase connector.

## Remaining software work

1. Real customer connector adapters and their contract tests, network/secret isolation and approval-bound dispatch.
2. Durable multi-step agent orchestration with pause/resume/cancellation and recovery across worker failures; current workbench pipelines are previews.
3. Enterprise RAG ingestion/OCR, embedding/vector retrieval, metadata permissions, deletion propagation, multilingual answer-quality datasets and poisoning controls.
4. Distributed rate/concurrency controls, streaming/provider fallback, richer usage reconciliation, model-specific pricing/accounting and inference evidence retention/pagination.
5. External telemetry, dashboards, alert delivery, SLOs, immutable audit storage and scheduled encrypted backup/restore automation.
6. Multi-workspace/environment lifecycle, IdP provisioning/offboarding, workload federation and independent security/accessibility review.

These are implementation gaps as well as environment tasks. A deployment template or provider key cannot complete them by itself.

## Required acceptance evidence

Read PRODUCTION_ACCEPTANCE.md. Live provider, PostgreSQL races, OPA outage/recovery, IdP/MFA lifecycle, cloud ingress/egress, backup restore, load/soak and penetration/accessibility tests must pass against the intended deployment. There is no production-ready claim in this release.
