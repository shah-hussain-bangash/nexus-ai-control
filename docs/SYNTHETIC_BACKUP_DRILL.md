# Disposable synthetic backup-safeguard drill

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run test:backup
```

No password, backup key, existing archive, report filename or running server is required. Your app can remain open. The command creates a fresh schema and three disposable accounts in one SQLite database, plus a small synthetic second SQLite database. It closes every fixture writer before taking snapshots. It never loads operator `.env` settings, databases, backup folders or encryption keys. The temporary key is generated in memory and supplied through a replacement environment view in the encryption module only; the process environment is not changed. Inspection temporary directories are confined to the disposable workspace, and module replacements are restored on exit. Pytest is not required.

The 34 checks cover:

1. A current-schema, synthetic, inference-disabled fixture with three accounts is selected.
2. Plaintext backup requires acknowledgement of quiescence.
3. The plaintext snapshot is created.
4. Plaintext integrity inspection passes without claiming PostgreSQL restore.
5. Every noninternal control-table record matches the source snapshot.
6. The second database's records match its snapshot.
7. An existing plaintext backup destination is never overwritten.
8. A modified snapshot is rejected.
9. A mismatched schema declaration is rejected.
10. An empty file manifest is rejected.
11. A missing control snapshot is rejected.
12. Encrypted backup also requires acknowledgement of quiescence.
13. A missing encryption key is rejected before an archive is created.
14. Invalid base64 key configuration is rejected.
15. An encrypted snapshot is created without serializing its key or obvious SQLite plaintext.
16. Authenticated encrypted inspection passes without restoring active data.
17. An existing encrypted destination is never overwritten.
18. A different key cannot authenticate the archive.
19. Modified ciphertext is rejected.
20. A truncated archive is rejected.
21. An unsupported format header is rejected.
22. A correctly authenticated archive with an empty manifest is rejected.
23. An excessive member list is rejected before extracting anything.
24. An unsafe member path is rejected before extracting anything.
25. Internal plaintext inspection/snapshot temporary directories are removed.
26. Both source databases retain their original logical records.
27. The original good plaintext snapshot and encrypted archive remain valid and unchanged after fault cases.
28. Plaintext backup rejects a disposable business database with a broken declared reference and creates no success manifest.
29. Encrypted backup rejects that broken reference before publishing a final archive.
30. An interrupted final copy reports failure and retains its incomplete archive.
31. That incomplete archive cannot pass inspection.
32. A retry into the retained destination is rejected without changing its bytes.
33. A retry to a different new destination succeeds and authenticates.
34. A replacement file survives a publication failure after the original output handle closes; the moved original archive still authenticates.

Fault injection changes only disposable fixture files and temporary encryption-module views of the key environment, copy function and output-handle wrapper. It never changes process-global OS/shutil functions or the process environment, and restores module views on exit. The drill restores the good plaintext snapshot bytes after negative checks. It creates malformed but correctly authenticated archive fixtures with its disposable key to exercise content checks separately from authentication. A separate broken-reference database leaves both original source databases intact. Publication faults copy only a short ciphertext prefix or replace a closed fixture path; all affected files stay in the disposable workspace and are removed during outer cleanup. The failed original publication is not counted as a successful backup even when its retained bytes authenticate. Three backup operations succeed: the plaintext snapshot, the original encrypted archive and the fresh-path retry. It checks all application tables by local row counts and hashes without publishing those hashes. These comparisons and SQLite checks do not establish full application recovery, durable publication or logical completeness for arbitrary databases.

Exit **0**, `"passed": true` and `"steps_passed": 34` indicate success; exit **1** indicates failure. The exact new report path is printed under ignored `backend/data/drills`. Unique `synthetic-backup-` reports use format `nexus-synthetic-backup-drill` and are written after removing the workspace and its snapshots, archives and temporary plaintext files. Reports contain fixed outcomes, release/schema metadata and fixture backup/account counts—not keys, passwords, record contents, table hashes, backup paths or private exceptions. Reruns never overwrite reports. Report-write/cleanup failure cannot return success; an operating-system cleanup failure may leave disposable fixture files for local review. File cleanup is not secure erasure or proof of memory zeroization. Older reports retain their original 27 checks and two successful-backup operations; their files are not rewritten.

Portable invocation: `python scripts/run_synthetic_backup_drill.py`. Optional `--output-dir` selects the report directory. Runtime dependencies must already be installed; the Windows wrapper uses the project's existing `.venv`.

These are unsigned local drill reports. Authentication results refer to the temporary AES-GCM archives; they do not authenticate the drill report. No active database is restored or overwritten. Real encrypted restore, application recovery, PostgreSQL restore, scheduled/off-host retention, key custody, measured RPO/RTO and production acceptance remain separate work. No provider or customer system is contacted. Do not use this disposable test key or these fixture archives for actual recovery.
