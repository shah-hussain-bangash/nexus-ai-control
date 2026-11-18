# Production acceptance reference

The sections below retain historical 0.5/0.6 acceptance requirements. For current
source delivery states, use `PRODUCTION_ROADMAP.md` and `PRODUCTION_GAPS_0_16_0.md`.
For the current local baseline review, use `PHASE_0_BASELINE.md`. Historical counts
and capability descriptions below must not be treated as a fresh verification.

## 0.6.0 acceptance update

The readiness board tracks 18 enterprise roadmap items. Source states and operator-attested evidence remain separate. New local tests cover scoped evidence, optimistic revisions, cursor isolation/expiry, rate/concurrency admission and recovery without re-dispatch. Live service, cloud, PostgreSQL restore, load/security and independent accessibility evidence is still required. PRODUCTION_ROADMAP.md is the current item-by-item scope; the 0.5.0 deployment acceptance details below remain applicable.

---

# Production acceptance gates

**Decision: DO NOT label the entire platform production-ready yet.** No current Windows installation or cloud environment was modified by this release.

| Gate | Current evidence | Required next evidence |
|---|---|---|
| Local backend behavior | Current JUnit suite and controlled provider transport tests | Preserve CI evidence for the exact deployed source/image |
| Live provider | Adapter implemented; no paid request made | Approved account, exact deployment/model rates, secret injection, live success/error/usage tests |
| PostgreSQL / OPA / IdP | Existing harnesses retained; 15 service-dependent cases skipped | Run integration suites on disposable services, then staging IdP/MFA and OPA fail-closed acceptance |
| Customer business effects | Synthetic connector only | Actual API contract, sandbox credentials via secret manager and duplicate-effect recovery tests |
| Agent pipeline runtime | Visual designs and dry-run traces | Durable execution, approval pause/resume, cancellation and crash recovery implementation/tests |
| Enterprise RAG | Bilingual BM25 and optional cited generation path | Authorized ingestion, semantic retrieval, per-document permissions and answer-quality evaluation |
| Deployment | Compose/Caddy candidate and YAML parse | Vetted image digests, Docker Compose validation/build, DNS/TLS/private PostgreSQL, egress rules and staging rollout |
| Recovery | Checksummed SQLite snapshot and inspection tested | Encrypted off-host backups, scheduled retention, PostgreSQL restore to isolated DB, measured RPO/RTO |
| Observability | Structured HTTP events and inference ledger | External log/metric collection, alerts, tracing, service objectives and operator response drill |
| Security/performance | Local role/CSRF/scope/egress/budget tests | Threat review, penetration and dependency/image scans, concurrent load/soak tests and accessibility assessment |

## Deployment information needed

Target AWS or Azure environment; public hostname and TLS/DNS owner; managed PostgreSQL endpoint and trusted CA; OIDC issuer/client/MFA policy; approved provider host/deployment and rate schedule; customer API sandbox contract; backup storage/KMS and operational ownership. Provision credentials through the target environment's secret manager, never chat messages or source commits.

The supplied pilot profile can run on a reviewed container host, but is not a high-availability managed cloud architecture. Its egress network is not an egress allowlist: the operator must enforce network/firewall rules outside Compose. The optional worker profile is named synthetic-demo-only and is off by default. Do not connect real purchasing endpoints until their adapter and approval/recovery contract are implemented and tested.

## Release decision

A technical owner should record each gate's environment, exact image/source digest, test artifact, date, reviewer and result. Only sign off the explicitly tested scope. The missing software capabilities above prevent whole-platform sign-off even if basic infrastructure starts successfully.
