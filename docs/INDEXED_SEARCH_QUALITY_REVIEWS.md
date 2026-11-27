# Reviewer-labelled quality measurements for saved indexed searches

This increment measures a completed stored-index search without rerunning it or
calling a model. It builds on PR #87 and adds no database migration beyond its
schema-12 requirement. It does not enable embeddings or change the running app.

## Dashboard flow

Open a completed indexed search in Ranked evidence, including an existing saved
receipt. In **Review saved indexed-search quality**, choose either expected source
retrieval or an expected empty result. Positive cases require a complete expected
document list of up to five current authorized documents. An optional integer
precision target is 0–100 percent. Supply a review note and, optionally, an explicit
English, Arabic or Bilingual query-language label. Labels are never inferred.

The server records recall over expected documents, precision over distinct returned
documents, first expected passage reciprocal rank, unexpected documents, and a
pass/fail outcome. A positive case passes when all expected sources were found and
its optional precision target is met. An empty-result case passes only when the
completed saved search returned no passages. Failed or incomplete searches cannot
be reviewed as successful empty results. Precision and recall are not applicable
to negative cases. As with existing retrieval checks, reciprocal rank uses passage
positions while precision and recall use distinct documents.

The dashboard displays saved reviews with the original search settings and model
identity. A measurement uses reviewer labels and does not independently establish
semantic correctness, language quality, answer grounding, customer acceptance or
production readiness. The expected list is treated as complete: unexpected sources
may require revising the label, rather than automatically proving poor retrieval.

## API and durable evidence

- `POST /v1/indexed-search-reviews` accepts a saved search ID, expectation,
  expected document IDs, optional language/precision labels and note. An intent
  key is required. It requires `operate` permission and current source access.
- `GET /v1/indexed-search-reviews` lists accessible reviews with paging.
- `GET /v1/indexed-search-reviews/{id}` reads a scoped saved review.
- `POST /v1/indexed-search-reviews/recover` retrieves an author's original review
  by intent key without execution.

The shared control database stores bounded review receipts as a separate workbench
run kind, excluded from the generic workbench response. There are at most 1,000
reviews per workspace/environment. Reviews are author or policy-admin scoped;
underlying search ownership and all referenced source ACLs apply too. Inaccessible
reviews are filtered before pagination and counts. No review can bypass revoked,
deleted or out-of-environment sources. This remains true for replay and recovery.

Creation requires a completed current stored-index search and a matching valid
index snapshot. Every index source plus each expected source is recorded by
version/hash without excerpts or vectors. Query text is not accepted or copied;
the browser persists only a scoped intent key/fingerprint/timestamp. Review notes
are stored as reviewer input, so avoid credentials or private query text.

A repeat key returns its original review; changed labels conflict. Receipts remain
readable but explicitly stale after accessible source changes or index removal.
Revoked sources hide the receipt entirely. A changed underlying saved run causes a
conflict instead of silently reinterpreting previous measurements. The review's
zero model-call count is separate from the original search's local HTTP-call count.
The model can be disabled while measuring an unchanged saved result.

These are unsigned application records, not authenticated evidence or an off-host
archive. No new retention/erasure schedule or independent reviewer attestation is
introduced. Real-model/bilingual acceptance, scalable indexing and learned
reranking remain separate work.

## Verification

Normal-API tests use disposable databases and mock local embedding transport.
They cover metrics and precision targets, negative results, incomplete/unsupported
and stale searches, invalid labels, request replay/recovery, source revocation and
deletion, cross-account isolation, changed saved runs, metadata removal and model
disablement. Review tests forbid additional worker dispatch. Frontend tests cover
query-free label payloads, negative-case normalization, cloned source selections,
scoped lost-reply recovery and definitive pre-admission conflicts.
