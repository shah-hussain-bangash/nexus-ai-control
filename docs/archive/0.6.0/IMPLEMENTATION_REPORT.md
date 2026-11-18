# Current implementation and production limits — 0.6.0

**Full platform production acceptance remains open.** Read PRODUCTION_ROADMAP.md for all 18 tracked workstreams and the current 6 missing / 11 partial / 1 implemented source-state breakdown. Existing control-plane functions are not included in those counts as separate completed workstreams.

## Delivered in this update

- Owner/security users can record scoped production evidence with an outcome, bounded note, optional credential-free HTTPS reference and expected revision. New evidence and edits generate audit events. Stale edits fail with 409. Unknown workstreams fail with 404. A capability marked not implemented in source cannot receive a passed outcome. Read access remains scoped and authenticated.
- Shared-database inference admission serializes per-organization reservations using an organization row lock on PostgreSQL and SQLite write serialization locally. Defaults: 30 admitted requests per rolling 60 seconds, 4 pending dispatches within the last 300 seconds. The organization lock spans month changes. Existing idempotent replays return prior records before admission checks. Limits apply to inference, not all API endpoints or IdP login attempts. This is not a network WAF. Live PostgreSQL/multi-worker behavior still requires integration testing.
- Inference history has signed keyset cursors, tied-timestamp ordering, query/status/organization binding, expiry, bounded search and page sizes. Search uses call/model references and current model-route names; it does not search prompt bodies. The UI exports the current page. Existing runtime summary remains bounded to its last 50 calls for compatibility. Retention/archival remains separate work.
- The browser can recover a submitted inference intent after a reload of the same tab. It saves only key, content fingerprint and timestamp; no request text, credentials or response bodies. The authenticated recovery API is author-scoped and does not call a provider. Unknown/pending outcomes continue to require review/reconciliation. Closing the tab, cleared/disabled browser storage or using another device is outside this recovery guarantee.
- Typography, contrast, form/table text and click targets were improved across the portal. A persistent appearance preference offers larger text. Release readiness now has three dedicated views instead of stacking several different controls in one long page. Independent accessibility and mobile assessment remain open.

## Retained boundaries

Provider requests remain explicitly enabled, text-only, synchronous and non-streaming. Their operator-priced reservation ledger is not a provider account spending cap or a full invoice reconciliation. Business effects remain synthetic and distinct from provider requests. Workbench workflows remain previews. Knowledge retrieval remains local BM25 with optional cited generation, not a complete enterprise semantic RAG pipeline. Generic customer connector execution, durable multi-step agents, workspace/environment lifecycle, immutable off-host audit, external monitoring/alerts and cloud recovery remain incomplete.

The 0.5.0 capability details are retained at archive/0.5.0/IMPLEMENTATION_REPORT.md. PRODUCTION_ACCEPTANCE.md still defines external acceptance prerequisites. No customer/cloud deployment was changed by this delivery.
