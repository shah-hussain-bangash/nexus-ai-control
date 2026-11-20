# Disposable synthetic knowledge drill

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run test:knowledge
```

This runs the existing 18 [keyword-retrieval checks](SYNTHETIC_RETRIEVAL_DRILL.md) and 18 additional local hybrid-search checks. Your existing `test:retrieval` command still runs its original 18 checks and keeps its report format. No password, API key, report path or running NEXUS server is needed. Your app can remain open.

The combined exercise creates temporary databases and synthetic identities, with local reference policies, a synthetic business connector and live inference disabled. It never reads operator `.env` settings or the existing application database. Hybrid checks use another disposable workspace, separate from the keyword corpus, and invoke the real isolated NumPy ranking worker. Only the supplied synthetic text is fitted. No customer, model provider, pretrained embedding model or persistent vector service is contacted. The worker's existing bounded runtime and sanitized environment apply.

Additional checks cover:

1. Local search capabilities declare their corpus bounds and absence of neural embeddings or a persistent vector index.
2. Search submission requires CSRF protection.
3. A query for `car` returns both its keyword source and an `automobile` source through corpus co-occurrence; the latter has zero lexical score and positive local semantic score.
4. A private matching source is excluded from the engineer's five-source fitted corpus.
5. A current result citation resolves to the original source text.
6. An unknown query completes with no results.
7. Arabic normalization retrieves the marked original text.
8. Replay and recovery return the original receipt without changing saved measurements or record counts.
9. Query text and source excerpts are absent from persisted search receipts.
10. A changed request cannot reuse the original search key.
11. A private selected source is rejected, as is an outdated selected source version.
12. An unrelated account cannot inspect or recover another author's search.
13. Another workspace cannot inspect search history or select its sources.
14. Revoked sources are withheld from saved history and their citations are inaccessible.
15. Deleted sources are withheld from saved history and their citations are inaccessible.
16. A replaced Arabic source invalidates its old result/citation; a fresh search uses version 2 and its updated text.
17. An oversized vocabulary produces an explicit failed receipt with no fabricated hits.
18. No provider calls or business effects occurred.

Hybrid history can retain its completed status while withholding stale or inaccessible hits. This differs from keyword suite evidence, which blocks the entire saved detail when a referenced source is no longer readable. The exercise checks each API's existing behavior.

Exit **0**, `"passed": true` and `"steps_passed": 36` indicate a successful combined exercise. Exit **1** indicates failure. The command prints the exact new report path under the ignored `backend/data/drills` folder. Combined reports use format `nexus-synthetic-knowledge-drill` and filenames beginning `synthetic-knowledge-`. Temporary databases are removed before a successful report is saved; reports are unique and never overwrite previous runs. They contain safe metadata, fixed step identifiers and outcomes, without query/source text, account credentials, session values or private exception details. Failed cleanup/report creation cannot claim success. An operating-system cleanup failure can leave temporary files locally for review.

Portable invocation: `python scripts/run_synthetic_retrieval_drill.py --include-hybrid`. Optional `--output-dir` selects the report directory. Runtime dependencies, including NumPy, must already be installed; pytest is not required. The npm wrapper uses the project's existing `.venv`.

These are unsigned local exercise reports. Scores describe corpus-fitted LSA/BM25 behavior, not calibrated confidence, multilingual semantic understanding, translation or generated-answer quality. Passing does not establish neural retrieval, scalable indexing, reranking, poisoning resistance, customer acceptance, deployment security or production readiness.
