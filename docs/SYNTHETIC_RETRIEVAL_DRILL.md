# Disposable synthetic retrieval drill

In Cursor's PowerShell terminal at this project's root, run:

```powershell
npm.cmd run test:retrieval
```

No report path, password, API key or running NEXUS server is required. The command creates a fresh in-process application, temporary SQLite databases and disposable accounts. It explicitly selects local reference policy evaluation, the synthetic connector and disabled live inference. It never loads operator `.env` settings, binds a server port, contacts a customer/model provider or uses the existing NEXUS database. Your running application can remain open.

Exit **0** and `"passed": true` mean all 18 checks passed. Exit **1** means the exercise, report write or cleanup failed. The JSON summary gives the exact saved report path; do not supply an example filename. Reports are unique unsigned JSON files under the ignored `backend/data/drills` directory. The temporary databases are removed before the report is written. Reruns create new files and never overwrite prior reports.

The exercise checks:

1. Only the synthetic runtime is selected, with live inference disabled.
2. Anonymous access to saved retrieval evidence is blocked.
3. An unvowelled Arabic query matches the original marked source, and its current citation retains the original text.
4. An engineer cannot access an owner's private source; it does not affect that engineer's subsequent retrieval scores.
5. An English/Arabic/no-result baseline passes, with 100% English precision despite a private matching source.
6. Explicit English, Arabic and unlabelled query groups have the expected measurements.
7. Adding a readable source marks old evidence stale without changing its saved precision.
8. An unlisted matching source reduces English precision to 50% and fails its 100% target while recall remains 100%.
9. Comparison requests require CSRF protection.
10. Matching saved runs show one regressed case, two unchanged cases, one fewer passing case, a 25 percentage-point mean precision decrease and a changed corpus.
11. Replay, recovery and repeated comparisons preserve saved run identifiers, measurements and record counts.
12. A changed request cannot reuse the original intent key.
13. Different top-k definitions cannot be compared.
14. An administrator cannot compare another author's checks under their own account.
15. Another workspace cannot inspect the source, saved check or comparison.
16. Revoking access to an unlisted returned source blocks the candidate's saved results and comparison.
17. Deleting an expected Arabic source blocks the baseline's saved results and comparison.
18. No model calls or business effects occurred, and only the three intended retrieval records were created in the disposable database.

Reports contain fixed step identifiers, pass/fail outcomes, release/schema metadata and the scope boundary. They do not contain source text, queries, saved-run identifiers, passwords, cookies, CSRF values or private exception details. A failed check records its fixed step identifier; unexpected exceptions use a generic failure code. If cleanup or report creation fails, the command cannot claim success. Any temporary files left by an operating-system cleanup failure remain local for operator review. The reports are not signed and are not automatically uploaded to GitHub.

The portable entry point is `python scripts/run_synthetic_retrieval_drill.py`. Optional `--output-dir` chooses the report directory. Runtime dependencies must already be installed; pytest is not required. The Windows npm wrapper uses the existing project `.venv`.

This tests a bounded local keyword-retrieval workflow with synthetic text. It does not evaluate hybrid/LSA search, neural embeddings, generated answers, translation, semantic relevance, poisoning resistance, real customer access, PostgreSQL deployment, load, production readiness or customer acceptance. Continue using separately reviewed evidence for those scopes.
