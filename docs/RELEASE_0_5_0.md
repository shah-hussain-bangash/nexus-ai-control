# Release 0.5.0 — provider runtime and operational controls

17 November 2026 | Database schema 4 | **Production engineering build; not production-ready sign-off.**

Implemented an explicit, disabled-by-default inference API and console. Approved OpenAI and classic Azure OpenAI v1 routes can execute bounded text requests when an operator provisions the exact host, model rates, monthly limit and secret reference. Optional cited BM25 evidence can be included. This is separate from workflow previews and synthetic business execution.

Added persistent integer micro-USD monthly reservations, a request idempotency ledger, recorded provider usage, owner reconciliation after uncertainty, bounded responses, no automatic network retries and secret-safe errors. Guardrail changes require policy permission; model activation requires manage permission. Normal engineers can invoke approved routes but cannot activate their own edited route.

Added checksummed SQLite/PostgreSQL backup commands, backup inspection, consistent request size limits including chunked bodies, generated request IDs, structured HTTP events, verified-TLS PostgreSQL requirement in pilot mode and an empty-workspace OIDC bootstrap command. A candidate Compose/Caddy deployment profile is included; actual image digests and infrastructure must be supplied and tested.

Provider tests use a controlled HTTP transport; no paid provider was contacted. Docker, pg_dump and a PostgreSQL server are unavailable in this environment. The pilot Compose file was parsed as YAML but not deployed or validated by Docker Compose. Existing 15 external-service cases remain skipped. See VERIFICATION.json for the final test count and PRODUCTION_ACCEPTANCE.md for unresolved gates.

Inference counters and model usage are not fictitious preview completions: live-call evidence has its own ledger, separate from the deterministic workbench run list. Default runtime execution remains disabled.
