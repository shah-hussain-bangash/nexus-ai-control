# Disposable synthetic connector drill

From the project root in Cursor's PowerShell terminal, run:

```powershell
npm.cmd run test:connector
```

No report path, supplier credential, real account password or running NEXUS server is required. The command runs against a fresh in-process API, local reference policy evaluation and a synthetic business database. It does not bind a server port or load operator `.env` settings, and explicitly selects the synthetic connector even if the operator environment selects HTTP or pilot mode. No customer system, provider or existing application database is used. The temporary workspace's accounts and generated passwords are discarded after the run.

The JSON summary reports `passed`, `steps_passed`, the saved report path and a fixed scope boundary. Exit **0** means all 15 checks passed. Exit **1** means a check, report write or cleanup failed; inspect the saved report when a path is provided. Reports are unique files in the ignored `backend/data/drills` folder; reruns create new reports and do not overwrite previous results. Temporary SQLite databases are removed before the report is saved. Reports contain step outcomes and a synthetic effect count, not passwords, cookies, CSRF values or raw private error details. They are local, unsigned artifacts and are not automatically uploaded to GitHub.

The drill checks:

1. Only the synthetic adapter is selected.
2. Governed supplier intake has no business effect before the worker runs.
3. The worker dispatches the supplier read.
4. Replaying or recovering the supplier intent returns the same verified action with one synthetic effect.
5. The exported supplier evidence passes offline checksum verification and retains its synthetic/unsigned labels.
6. A purchase above the policy threshold waits for approval and has no effect while waiting.
7. Self-approval is rejected.
8. An approval with a changed payload hash is rejected.
9. An independent reviewer can approve dispatch.
10. A simulated timeout after the synthetic commit leaves the purchase outcome unknown.
11. Replaying that uncertain intent does not dispatch a second purchase.
12. Changing the body under the same key is rejected without another effect.
13. Another workspace cannot read the action or supplier evidence.
14. Another workspace cannot reconcile it or perform an authoritative lookup.
15. The original owner can explicitly reconcile the authoritative result without retrying the purchase. The final synthetic effect count is two: one supplier lookup and one purchase.

The portable entry point is `python scripts/run_synthetic_connector_drill.py`. An optional `--output-dir` selects where new reports and their temporary workspaces are created. Application runtime dependencies must already be installed; pytest is not required. The Windows npm wrapper uses the existing project `.venv`.

This exercises local control-plane behavior against synthetic data. It does not prove customer-side authentication, remote tenant isolation, atomic idempotency, real timeout behavior, PostgreSQL deployment, network isolation, operational recovery or production readiness. Those still need separately authorized customer-sandbox and deployment acceptance. No actual purchases are made.
