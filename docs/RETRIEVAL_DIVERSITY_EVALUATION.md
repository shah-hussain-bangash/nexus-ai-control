# Saved checks for document-diverse keyword retrieval

The retrieval quality editor offers **Keep only the highest-ranked passage per
document**. It starts unchecked for a new suite and is restored when reviewing
and rerunning a saved suite. Each inspected result states the recorded mode;
editing the checkbox does not relabel historical evidence.

`POST /v1/retrieval-checks` accepts optional `one_per_document: true` with the
existing name, top_k and cases. Only a JSON boolean is accepted. False or omitted
retains the existing passage-level behavior and exact legacy request fingerprint.
True is part of the saved definition and idempotency fingerprint. Changing modes
with an existing request key returns an idempotency conflict.

Document diversity uses the existing keyword scores, authorized current-version
chunks, deterministic ordering and grouping before top-k from the Document
library option. Recall, precision, reciprocal rank and language-group metrics
keep their existing definitions. Top-k limits returned passages; in diversity
mode each belongs to a different document record. Identical text in separate
records is still counted separately. Precision assumes the reviewer supplied a
complete expected-source list.

New results explicitly save the boolean. Older definitions/results with neither
field mean passage-level retrieval. Inspection rejects inconsistent or nonboolean
saved modes, including a diversity definition with no corresponding measured
mode. Existing source-visibility, current-version, corpus-fingerprint and
normalization checks continue to apply. No raw source excerpts are newly saved.

Saved-run comparisons require the same mode as well as the existing matching
ordered cases, expected sources, top-k, language labels and precision targets.
Mixed modes return `COMPARISON_DEFINITION_CHANGED`, rather than treating a method
change as a same-definition regression. Comparison snapshots include the mode.
To inspect both modes, save a suite under each and inspect their individual
measurements; they cannot be combined into a matching-definition comparison.

This feature makes no provider calls, schema changes, migrations or automatic
acceptance decisions. It measures reviewer-defined keyword retrieval only, not
neural relevance, generated-answer quality, source independence or production
readiness. Answer-generation retrieval remains unchanged.

Validation lives in `backend/tests/test_retrieval_diversity_evaluation.py` and
the existing lexical-ranking, precision, language metrics, comparison and
synthetic retrieval-drill suites. Use disposable test databases. Frontend
validation remains `npm test` and `npm run build` from the frontend directory.
This change builds on the unmerged keyword-search PR #81; no merge or deployment
is part of this development change.
