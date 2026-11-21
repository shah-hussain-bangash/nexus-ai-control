# Disposable synthetic inference-control drill

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run test:inference
```

No provider key, password, report filename or running NEXUS server is required. Your app can stay open. The command creates a fresh in-process API, disposable accounts and temporary SQLite databases. It never loads operator `.env` settings or the existing app database. It enables inference only on that disposable app, with explicit fixture prices, a fixed synthetic billing period, a placeholder credential map and an HTTP mock transport. An independent transport guard rejects attempts to enter the real HTTP transport before network I/O. All temporary module patches are restored on exit. Pytest is not required.

The 27 checks cover:

1. The isolated mock-provider/synthetic-business runtime is selected.
2. Anonymous runtime access is blocked.
3. Inference requires CSRF protection.
4. A disabled inference runtime sends nothing.
5. A stale model version sends nothing.
6. An unapproved provider route sends nothing.
7. An unpriced model sends nothing.
8. Redaction cannot hide an original-input blocking signal.
9. Owner-reviewed archiving of the blocker allows the same intent, still redacted.
10. Successful mocked usage settles its reservation.
11. Completed replay/recovery returns the same record without another request.
12. A changed immutable intent is rejected.
13. A simulated timeout keeps an unknown outcome and held reservation, hiding private errors.
14. Unknown replay/recovery does not send another request.
15. A nonowner cannot reconcile usage.
16. Another workspace has no private calls or budget entries.
17. Another workspace cannot recover or reconcile the call.
18. Owner reconciliation settles usage once, with duplicate settlement rejected.
19. A malformed provider message stays unknown without retry.
20. A provider quota response stays unknown without retry.
21. A redirect stays unknown without following another destination.
22. An oversized response stays unknown without retry.
23. A simulated completion at the exact deadline stays unknown.
24. Simulated pending-call saturation rejects new admission without dispatch/reservation.
25. An exhausted monthly fixture budget rejects new admission without dispatch.
26. A saturated request-rate limit rejects new admission without dispatch.
27. Exactly seven mock requests exist, no pending/unknown reservations remain after fixture reconciliation, the ledger contains 40 synthetic micro-USD of usage, and no business effects occurred.

The deadline case advances only the adapter's local monotonic-clock reference when the mocked response stream closes. The pending case temporarily relabels one disposable unknown call as pending, then restores it before reconciliation. Fixture route edits exercise the allowlist/pricing gates. The fixed billing period is only for reproducible synthetic accounting. None of these faults changes the operating-system clock, other processes, your live settings, provider credentials, accounts or records. The prices and token counts are fixture values, not current market rates or an invoice.

Exit **0**, `"passed": true` and `"steps_passed": 27` indicate success; exit **1** indicates failure. The exact new report path is printed under ignored `backend/data/drills`. Unique `synthetic-inference-` reports use format `nexus-synthetic-inference-drill` and are written after temporary database cleanup. They contain fixed outcomes, release/schema metadata and fixture counts/cost totals, not request bodies, answers, identities, session values, credentials or private exceptions. Reruns never overwrite earlier reports. Report-write/cleanup failure cannot return success; an operating-system cleanup failure may leave temporary files for local review.

Portable invocation: `python scripts/run_synthetic_inference_drill.py`. Optional `--output-dir` selects the report directory. Runtime dependencies must already be installed; the Windows wrapper uses the project's existing `.venv`.

These are unsigned local exercise reports. Selected mocked responses do not establish actual provider/model compatibility, generated-answer quality, real timeout/quota handling, provider billing or customer acceptance. The transport guard is an exercise safeguard, not deployment-enforced network isolation. PostgreSQL deployment, authenticated evidence and production readiness remain separate acceptance work. No provider or customer system is contacted.
