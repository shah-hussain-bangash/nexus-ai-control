# Phase 0 — baseline stabilization

Review date: 18 November 2026. Starting revision: `b096886`.
This phase establishes an engineering baseline; production acceptance remains open.

## Changes

- Fixed non-deterministic DOCX test files: ZIP timestamps are now fixed so retries
  reuse identical immutable bytes. The intake API's conflict protection is unchanged.
- Made the SQLite snapshot integrity test create its own disposable SQLite database,
  including when the wider suite uses PostgreSQL. PostgreSQL concurrency tests and
  encrypted-backup tests retain their original database coverage.
- Generated the current roadmap and machine-readable workstream inventory from the
  API's `GATES` definitions, and added a CI check to prevent stale generated files.
- Updated the documentation index and labeled older acceptance sections as historical.
- Restricted frontend and demo development/preview servers to `127.0.0.1`.

## Validation and evidence

- Starting revision, local Windows backend: 285 passed, 18 skipped, zero failures.
  Skips cover external services, OCR provisioning and POSIX-only checks.
- Starting revision, frontend: 51 tests passed and production build passed.
- Changed intake/backup test files, local Windows: 14 passed, 1 OCR-related skip.
- Post-change frontend: 51 tests passed; isolated demo: 5 tests passed; both builds passed.
- Production-dependency audits (`npm audit --omit=dev`) reported zero vulnerabilities
  in both frontend packages. The full build-tool audit remains open as described below.
- Generated roadmap `--check`: passed; 1 implemented awaiting acceptance,
  16 partial, 1 not implemented, zero deployment acceptance granted by default.
- Original GitHub run: backend, frontend and OPA jobs passed; PostgreSQL job failed
  on the two test issues corrected above. Follow the Phase 0 branch's GitHub checks
  for post-change PostgreSQL evidence; this document does not claim those checks passed.

Local tests use disposable databases. Existing accounts and application data are preserved.

## Open dependency finding

The frontend dependency audit reported four high-severity package entries that trace
to the same Picomatch advisory, GHSA-fc5q-39xc-vjpf / CVE-2026-112366. The affected
chain is Vite, tinyglobby, fdir and picomatch. The current registry reports Picomatch
4.0.7 as latest; the advisory lists no patched version as of this review.

Advisory: https://github.com/advisories/GHSA-fc5q-39xc-vjpf

These packages are development/build dependencies. This is not a clean full audit
or a production security sign-off. Restricting dev/preview servers to loopback reduces
network exposure but does not patch the vulnerable pattern matcher. Keep build inputs
trusted and track an upstream fix or a separately tested dependency migration.

## Next phase

Phase 1 begins with workspace/environment data modeling and membership boundaries.
Keep existing records assigned to a default context during migration. Implement and
test server-side isolation before connecting workspace switching to the interface.
