# Current documentation — 0.16.2 candidate

- [Enterprise architecture](ENTERPRISE_ARCHITECTURE.md) maps trust boundaries, runtime code, tests and pilot acceptance evidence.

- `PHASE_1_RUNTIME_ACCESS.md`: current staging access enforcement, worker fences, limitations and code-only update from 0.16.1.

- `PHASE_1_ENVIRONMENT_FOUNDATION.md`: current environment foundation, schema 9 migration, and maintenance plan. Existing 0.16.0 reports below are historical.

- `PRODUCTION_GAPS_0_16_0.md`: detailed implemented boundaries and remaining software.
- `PRODUCTION_ROADMAP.md` / `PRODUCTION_WORKSTREAMS.json`: current source delivery states, generated from `backend/nexus/readiness.py`.
- `FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv`: every planned function and its actual runtime boundary.
- `IMPLEMENTATION_REPORT.md` / `UPGRADE_0_16_0.md`: release behavior and upgrade instructions; schema 8.
- `HYBRID_RETRIEVAL_0_16_0.md`: ACL-first local LSA/BM25 search and remaining vector/answer-quality work.
- `IDENTITY_LIFECYCLE_0_16_0.md`: member administration and remaining identity lifecycle work.
- `PHASE_0_BASELINE.md`: baseline stabilization work, validation and open findings.
- `VERIFICATION.json`: historical verification for the original 0.16.0 release.
- Root `CURSOR_VERIFICATION.json`: historical verification of the initial Windows package.

Older numbered release documents and archived reports remain historical evidence.
Current machine-readable workstream states are checked against the API definitions in CI.
The 216 design definitions remain separate from runtime implementation and production acceptance.
