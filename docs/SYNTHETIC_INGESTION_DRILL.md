# Disposable synthetic file-ingestion drill

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run test:ingestion
```

The command needs no password, input file, report path or running NEXUS server. Your app can remain open. It creates deterministic synthetic DOCX/PDF fixtures, a temporary in-process application, disposable accounts and SQLite databases. It uses the real isolated extraction worker with local parsers, reference policies, the synthetic business connector, disabled live inference and disabled OCR. It never loads operator `.env` settings or uses your existing database, documents or accounts.

The 25 checks cover:

1. Explicit local/synthetic runtime with OCR disabled.
2. Anonymous intake access is blocked.
3. Uploads require CSRF protection.
4. A queued file cannot appear in document search.
5. Replay and recovery acknowledge the same intake.
6. A changed file request cannot reuse its original key.
7. A queued file cannot be published.
8. Real DOCX extraction preserves English and marked Arabic text and awaits review.
9. Extracted text stays out of search before publication.
10. Publication requires explicit review and the current intake version.
11. Repeated reviewed publication creates only one source document.
12. Publication discards the intake's original file bytes and review text from active storage.
13. Source provenance retains the original file hash, byte count and published-version relationship.
14. An authorized auditor can search/read the source and current citation, but cannot read the private intake record.
15. Another workspace cannot inspect the intake or source or find it in search.
16. Real searchable-PDF extraction awaits review without OCR.
17. A reviewed PDF becomes searchable.
18. A 13-page PDF fails the 12-page bound and cannot be published.
19. Forced OCR is rejected while OCR is disabled.
20. Cancellation, archival and replay cannot resurrect queued work.
21. A malformed DOCX fails without publication.
22. Retry preserves the failed intake's identity and increments its attempt count.
23. Source deletion removes active search hits and citations.
24. Replaying intake/publication cannot recreate a deleted source or its chunks.
25. All five terminal intake records have discarded file/review text and no business effects occurred.

Exit **0**, `"passed": true` and `"steps_passed": 25` mean the exercise passed. Exit **1** means a check, report write or cleanup failed. The command prints the exact new report path in the ignored `backend/data/drills` folder. Reports use format `nexus-synthetic-ingestion-drill` with unique `synthetic-ingestion-` filenames. Temporary databases are removed before a successful report is written. Reports contain fixed step outcomes and safe release/schema metadata, without file content, query text, account/session values or private exception details. Existing reports are never overwritten. An operating-system cleanup failure can leave temporary files locally for operator review; it cannot produce a success summary.

Portable entry point: `python scripts/run_synthetic_ingestion_drill.py`. Optional `--output-dir` selects the report directory. The npm wrapper uses the existing project `.venv`; runtime dependencies must already be installed, but pytest is not required.

The minimal synthetic fixtures exercise supported parser behavior; they do not establish compatibility with arbitrary office documents. These unsigned reports do not prove OCR quality, translation, malware safety, full operating-system containment, backup/WAL erasure, authenticated evidence, customer acceptance or production readiness. No customer system or model provider is contacted.
