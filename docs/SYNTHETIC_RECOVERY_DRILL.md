# Disposable synthetic recovered-application drill

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run test:recovery
```

Your app can stay open. No account password, existing backup, operator key or server address is needed. Runtime dependencies must already be installed; the Windows wrapper uses the project's `.venv`. Portable invocation is `python scripts/run_synthetic_recovery_drill.py`; optional `--output-dir` chooses the report directory. Pytest is not required.

The drill creates a fresh SQLite control database, four disposable accounts across two workspaces, one prompt per workspace and a synthetic business receipt. Each workspace has its own owner and staging assignment. That receipt is explicit fixture data, not a governed customer dispatch. After closing fixture writers it makes an encrypted backup with a random in-memory key and invokes the existing isolated recovery primitive. The key is supplied only through a replacement encryption-module environment view, never by changing the process environment. All source, snapshot, encrypted and decrypted files stay inside one disposable filesystem directory. It does not load operator `.env`, settings, databases, keys or backup folders.

The recovered app uses explicit settings pointed at the copied SQLite files, local login, reference policies, the synthetic connector and disabled live inference. FastAPI's in-process test client opens no listening port. No worker is started, no provider/customer system is contacted, and the recovered database is neither migrated nor seeded. This tests compatibility with the same release/schema, not an upgrade or production deployment.

The 39 checks cover:

1. A disposable synthetic, inference-disabled source app.
2. Source owner login and a saved version-one marker.
3. A saved synthetic business receipt.
4. Four disposable accounts in the source database.
5. A quiesced encrypted fixture backup.
6. Wrong-key rejection without allocating a recovery directory.
7. Rejection of the existing source directory as a destination.
8. Authenticated copying without activation by the file-copy primitive.
9. All logical control records matching before recovered startup.
10. All logical business records matching before recovered startup.
11. Cleanup of private inspection temporary directories.
12. A synthetic recovered runtime.
13. Schema readiness without migration or reseeding.
14. Anonymous access rejection.
15. Copied owner session and staging context preservation.
16. Explicit revocation of the copied session.
17. Rejection of that revoked session.
18. Fresh login with the fixture's recovered credentials.
19. Disabled live inference.
20. Readable recovered prompt and configuration.
21. CSRF enforcement on writes.
22. Deterministic local prompt preview with passing assertions.
23. Auditor read permission.
24. Auditor write rejection.
25. New records written to the recovered copy.
26. A new recovered revision.
27. Stale revision rejection.
28. Retention of the original revision.
29. Receipt lookup without redispatch or extra business calls.
30. Original source records and sessions unchanged after recovered API writes.
31. Unchanged encrypted input.
32. A second source workspace with its own owner and saved marker.
33. The second owner's recovered identity, workspace and staging context.
34. Only that workspace's marker appearing in its recovered listing.
35. Rejection of cross-workspace history reads.
36. Rejection of cross-workspace edits, using a current version and valid request context.
37. Rejection of cross-workspace prompt runs, using valid CSRF/context headers.
38. Successful new writes within the second recovered workspace.
39. The primary workspace retaining only its own assets/revisions after the second owner writes, with reverse history access also blocked.

Isolation checks use authenticated owners on both sides, so a low-privilege role or missing CSRF token cannot explain the cross-workspace denials. Both copied owners can list their own assets and create records; foreign asset/history/run requests return 404. Fault-injection tests turn these denials into successful responses or leak an extra listing row and require the drill to fail. This exercises the restored workbench API's workspace scope, not every feature's authorization or a customer deployment's isolation acceptance.

Session cookies are opaque references to database records. A copied session remains valid until expiry or explicit revocation; changing a runtime secret does not sign or invalidate it. The drill demonstrates revocation only in its recovered fixture, and verifies that the original fixture's session rows remain unchanged. Review real session revocation and runtime/connector bindings separately before cutover.

Exit **0**, `"passed": true` and `"steps_passed": 39` indicate success; exit **1** indicates failure. Each run prints a unique `synthetic-recovery-` JSON report path under ignored `backend/data/drills`. Format `nexus-synthetic-recovery-drill` contains fixed check outcomes, release/schema metadata and the fixture account count. It contains no keys, credentials, cookies, record contents, table hashes or private exception details. Logical comparisons use private counts/hashes internally. Reports are written only after normal workspace cleanup. Failed cleanup or report writing cannot claim success; an operating-system cleanup failure may leave disposable fixture files for local review. Cleanup is not secure erasure or memory zeroization. Older reports from the earlier single-workspace drill retain their original 31 checks and three-account fixture count.

Successful reports set `synthetic_api_exercised: true`; they retain `active_database_restored: false`, `postgresql_restore_verified: false`, `customer_acceptance: false` and `production_ready: false`. These unsigned reports do not become authenticated evidence because the temporary archive authenticated successfully. Real application cutover/rollback, customer data/session/connector acceptance, PostgreSQL restore, scheduled/off-host retention, key custody and measured RPO/RTO remain separate work. Do not use disposable keys or fixture archives for actual recovery.
