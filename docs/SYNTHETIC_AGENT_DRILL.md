# Disposable synthetic agent-workflow drill

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run test:agents
```

No password, API key, report filename or running NEXUS server is required. Your app can remain open. This creates a fresh in-process API, temporary SQLite databases and disposable accounts. It explicitly selects local reference policy evaluation, the synthetic business connector and disabled live inference. It never loads operator `.env` settings or uses your existing application accounts, records or business adapter. Pytest is not required.

The 24 checks cover:

1. Only the synthetic runtime is selected, with live inference disabled.
2. Anonymous run access is blocked.
3. Run creation requires CSRF protection.
4. Replay/recovery acknowledge the same run without effects.
5. A changed workflow cannot reuse its immutable intent key.
6. Pausing before the first checkpoint prevents advancement.
7. A stale resume version is rejected.
8. A valid resume advances only the checkpoint.
9. A supplier intent has no effect until the business worker dispatches it.
10. A verified supplier lookup reaches the independent workflow-review gate.
11. The requesting author cannot approve that checkpoint.
12. An independent reviewer can approve it.
13. The purchase still needs its separate business approval.
14. A changed business-approval payload hash is rejected.
15. A simulated timeout after synthetic commit remains outcome-unknown.
16. Retrying the uncertain action through run controls is rejected.
17. Polling and replay do not repeat its effect.
18. Cancellation does not claim to undo an uncertain effect.
19. Authoritative reconciliation finishes cancellation without another purchase.
20. Another workspace cannot inspect, recover or control the run.
21. A simulated overdue paused review expires its run/checkpoint.
22. A simulated late worker claim recovers before advancing a step.
23. That recovered workflow can finish under valid claims.
24. Exactly two synthetic effects and three workflows exist: one supplier lookup and one purchase effect, with cancellation, expiry and recovery outcomes retained.

The deadline cases are explicit fault injections. The exercise sets one disposable review deadline into the past and temporarily advances only its own process's durable-worker clock immediately after a claim commits. It restores the clock function and removes its temporary callback afterward. It does not alter your operating-system clock, other processes, active NEXUS settings or production deadlines. It uses bounded explicit worker ticks rather than waiting for real review/lease windows.

Exit **0**, `"passed": true` and `"steps_passed": 24` indicate success; exit **1** indicates failure. The command prints the exact new report path under the ignored `backend/data/drills` folder. Unique `synthetic-agents-` reports use format `nexus-synthetic-agent-drill` and are written after temporary database cleanup. They contain fixed step outcomes, safe release/schema metadata and synthetic effect/run counts—not credentials, session values, workflow/action IDs, approval hashes, raw requests or private exceptions. Reruns never overwrite earlier reports. Failed report creation/cleanup cannot return success; an operating-system cleanup failure may leave temporary files locally for operator review.

Portable invocation: `python scripts/run_synthetic_agent_drill.py`. Optional `--output-dir` selects the report directory. Runtime dependencies must already be installed; the Windows wrapper uses the existing project `.venv`.

These are unsigned local exercise reports. The effect counter describes synthetic database operations, not real purchases. The command does not prove autonomous model planning, customer-side idempotency, real network failures, PostgreSQL deployment, authenticated evidence or production readiness. No customer system or model provider is contacted.
