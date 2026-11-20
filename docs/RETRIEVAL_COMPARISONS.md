# Compare saved retrieval runs

In **Document library**, select a saved retrieval check. Under **Compare saved runs**, choose a baseline from your other checks on the current history page, then select **Compare with selected run**. The selected check is the candidate; comparisons can run in either chronological direction. Dates and suite names identify the runs. To create another matching run, use **Review and rerun suite**, retain its cases and controls, and optionally change its name.

Both checks must belong to the signed-in account in the current workspace and environment and must have been recorded under its current role. Ordered queries, retrieve/no-result expectations, expected document sets, top-k, reviewer language labels and optional precision targets must match. Suite names and expected-document list order may differ. Changing a test definition requires a separate review rather than a score comparison.

The view shows baseline and candidate pass counts, mean document recall, mean document precision and mean reciprocal rank, followed by each case's saved measurements. Percentage changes are percentage points, not relative percentages. Means exclude no-result cases; those cases show not applicable for retrieval scores and compare their pass outcome and unlisted-source count. Returned-source or order changes are flagged even when numeric scores are unchanged.

A case is **improved** when at least one measured value improves and none worsens; **regressed** when at least one worsens and none improves; **mixed** when both occur; otherwise **unchanged**. Higher pass outcome, recall, precision and reciprocal rank are better; fewer unlisted sources are better. These are descriptions of configured measurements. An improved case may still fail, and an unlisted source may be relevant. Review the completeness of the expected-source list.

Changed authorized-corpus fingerprints or search-normalization versions are explicitly flagged. Either run can be stale relative to today's sources. The comparison uses historical measurements and cannot establish why results changed. It performs no new retrieval, reranking, model call, generated-answer grading, customer connection or deployment acceptance.

## Access and API behavior

`POST /v1/retrieval-checks/compare` takes distinct `baseline_id` and `candidate_id` values and requires the normal authenticated context and CSRF token. Source permissions and deletion are checked again for every referenced expected and returned source before releasing comparison results. An administrator may inspect another author's check through existing detail controls but cannot compare it under their own identity. Missing or out-of-scope checks return 404; changed source access, role, definitions or unsupported saved measurements return 409.

The response contains run summaries, numeric case frames and deltas, change counts and corpus/method change flags. It does not duplicate saved query text, source identifiers, excerpts, citations or request keys. The browser labels cases using the selected check and discards late comparisons when selection, history page, workspace or session changes.

The operation briefly takes the existing workspace ordering lock while checking identity and sources. It creates no comparison record or audit evidence and does not rewrite either saved run. No database migration or dependency is introduced. Existing suite creation, replay, recovery, removal and pass rules remain in effect.
