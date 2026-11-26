# One result per document in keyword search

Document library has an optional **One result per document** checkbox next to
keyword search. It starts unchecked. Search still returns the usual cited
passages; when enabled, only the highest-ranked matching passage from each
readable document is returned. The result description records the mode used by
that response, rather than changing when the checkbox is toggled afterward.

## API and ranking

`GET /v1/documents/search?q=procurement&top_k=10&one_per_document=true`

Omit `one_per_document`, or use `false`, for the existing passage-level ranking.
The response includes the resolved boolean and a method description. Normal
human authentication, workspace/environment binding, query bounds and current
document permissions apply. No provider/model call or database write is added.

All authorized current-version chunks are scored with the existing BM25-style
keyword formula. Scores are sorted descending, with the existing document ID
and chunk-position tie-breaks. If enabled, the first passage per document is
retained **before** applying `top_k` (1–10). Other documents can therefore fill
slots that repeated passages occupied. Scores and citation IDs do not change.
No corpus terms or chunks from unreadable documents enter ranking.

The internal search helper defaults to the existing behavior. Existing internal
callers and generated-answer retrieval retain passage-level mode. Saved quality
checks now support an explicit, recorded opt-in described in
[document-diversity evaluation](RETRIEVAL_DIVERSITY_EVALUATION.md); older checks
retain their original passage-level interpretation.

## Limits

This is document-record diversity, not content deduplication, semantic reranking,
source independence, or evidence validation. Distinct records with identical
text remain distinct. Fewer results are expected if fewer documents match. The
current bounded document-library capacity still applies. Citation inspection
continues to check current access and version.

There is no schema migration or deployment configuration change. This PR is
independent of the separate hybrid-retrieval and identical-text-review PRs.

## Reproduction

Run `python -m pytest tests/test_lexical_source_diversity.py tests/test_documents.py
tests/test_document_lifecycle.py tests/test_document_environment_context.py` from
the backend directory with development dependencies installed and a disposable
test destination. The focused tests exercise real ranking and normal API calls,
including a long dominant source, unchanged legacy scores, top-k ordering,
matching copies, ACL revocation, tenant/environment boundaries, stale chunks,
empty results, query validation and current citation inspection.

Frontend validation uses `npm test` and `npm run build` from `frontend`.
Automated checks do not establish representative bilingual retrieval quality or
production acceptance.
