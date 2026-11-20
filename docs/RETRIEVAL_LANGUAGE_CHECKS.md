# Compare retrieval checks by query language

Open **Document library**, scroll to **Test what your sources return**, and select **New retrieval check**. Add positive queries with their expected document sources and negative queries that should return no authorized matches. Each case has an optional **Query language** label: English, Arabic, Bilingual or Unlabelled. Labels are supplied by the reviewer; the application does not infer language, translate the query or validate a label's linguistic correctness.

Run and save the check to see **Results by query language**. Only groups represented in the suite are shown. Each row reports:

- Cases passed out of all cases in that group.
- Mean document recall at the selected top-k, averaged over that group's positive retrieval cases only.
- Mean document precision, using distinct returned documents and averaged over positive retrieval cases only. See [Document precision](RETRIEVAL_PRECISION.md) for the denominator and interpretation.
- Mean reciprocal rank of the first expected chunk, also over positive retrieval cases only.
- The fraction of no-result cases that returned no authorized matches, averaged over negative cases only.

Counts beside the metrics show the relevant denominators. If a group has no positive or no negative cases, its corresponding metric is **Not applicable**, not zero or a perfect score. Negative successes do not inflate recall or reciprocal rank. The overall suite status still requires every case to pass, including any explicitly configured [precision target](PRECISION_TARGETS.md); language grouping cannot turn a failed case into a pass or grant deployment acceptance.

These are measured results from current-ACL document keyword retrieval with the current Arabic search normalization. They do not evaluate the local hybrid/LSA ranker, translation, semantic relevance, generated answers or grounding. Use representative approved test data and inspect citations. A small passing suite is not bilingual quality certification.

## Saved evidence and compatibility

Language labels are stored with new labelled case configuration/results. Query text and results retain the existing backend storage and author/owner/security visibility rules; excerpts are not added to saved evidence. The browser does not persist draft queries in recovery storage. Workspace, environment and source-access checks run before detail/metrics are returned. Revoked/deleted source access still blocks historical detail, and source/corpus/tokenizer changes still mark evidence stale.

Old cases stay Unlabelled. Detail reads derive grouped statistics without rewriting historical results, changing their labels or rerunning retrieval. Requests that omit the optional label, or explicitly send null, keep the exact previous request fingerprint and replay/recovery behavior. Changing a label is a changed intent and requires a new key. Rerunning from the editor preserves any existing labels.

The API field is `cases[].query_language`, with values `English`, `Arabic`, `Bilingual` or null/omitted. The UI's Unlabelled option omits it; the string `Unlabelled` is not an input enum. Detail/create responses add top-level `language_metrics`, with groups containing `language`, `case_count`, `passed_cases`, `retrieve_cases`, `no_results_cases`, `mean_document_recall_at_k`, `mean_document_precision_at_k`, `mean_reciprocal_rank` and `no_results_pass_rate`. Listing and recovery summaries retain their established shape.

No database migration, new dependency, provider call, customer connection, automatic relabelling or automatic test run is introduced.
