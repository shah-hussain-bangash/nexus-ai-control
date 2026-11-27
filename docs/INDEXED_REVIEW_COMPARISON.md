# Compare saved indexed-search quality reviews

This increment adds a read-only comparison of two saved indexed-search quality
reviews, without model execution, database migration or configuration changes.
It builds on PR #88 and retains its schema-12 requirement.

## Dashboard and API

In the indexed-search quality panel, choose a baseline and candidate from the
accessible reviews on the current page. **Compare saved measurements** submits
only the two review IDs to `POST /v1/indexed-search-reviews/compare`. The server
rechecks review ownership, original-search access and every captured source ACL
on both sides. Comparison does not create another receipt or rerun retrieval.

A comparison requires two distinct saved searches, the same original query and
actor, identical expected-source sets/outcome/language/precision labels, matching
retrieval-method versions, and the same top-k, score threshold and document-diversity
controls. Reviewer notes and expected-source ordering may differ. An author or
policy administrator still needs current source access to both reviews.

The result shows recall, precision, reciprocal rank and unexpected-document counts,
with candidate-minus-baseline deltas. Direction is improved, regressed, mixed or
unchanged over the recorded metrics and pass/fail outcome. Positive metric deltas
are favorable, while fewer unexpected documents are favorable. Negative cases
retain not-applicable recall/precision/rank instead of inventing a quality score.

Model, corpus and index changes are reported separately. Accessible source changes
or removed/invalidated indexes make the comparison explicitly historical/stale.
Revoked or deleted sources hide it. A better measured outcome does not establish
that a model change caused it, especially when the source corpus also changed.
The comparison adds zero model calls and grants no independent model, bilingual,
generated-answer, customer or production acceptance.

## Private query equality and compatibility

New indexed-search receipts contain a server-private HMAC-SHA256 identity over the
workspace, environment, original author and exact validated query. The existing
private application secret keys it. This identity is not sent to the embedding
worker, returned in search/review/comparison APIs, or written to browser storage.
Raw query text remains transient. Different actors, scopes, secrets or queries
produce different identities; only the existing query trimming is applied.

Older searches have no such identity and cannot be compared reliably from their
whole-request fingerprints. They remain readable/reviewable, but both searches
must be run again for comparison. Replaying an older intent never retrofits an
identity or repeats model execution. No migration invents equality evidence.
Rotating the application secret also prevents comparisons across old/new identity
keys; rerun both searches under the same key instead. This equality check is an
application control, not an authenticated evidence signature or proof that a
reviewer's language/expected-source labels are correct.

## Verification

Disposable normal-API tests use synthetic embedding transport. They cover same-query
comparison without dispatch, private query identity, changed model snapshots,
label/control/query/legacy mismatches, duplicate searches, source staleness and
revocation, scope isolation and expected-source ordering. Existing storage,
quality-review, workbench and document-context tests cover compatibility. Frontend
tests check comparison order and missing/duplicate selection handling; the dashboard
discards a response if its selections or displayed review list changed while waiting.

Scalable indexing, learned reranking, representative model/language acceptance and
deployment validation remain separate work. The running local app is unchanged.
