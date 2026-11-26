# Local hybrid retrieval — 0.16.0

Open **Knowledge & RAG** after adding indexed documents in **Document library**. Enter search terms, optionally select up to 20 source revisions, choose rank/weight/threshold/top-k and select Search evidence. The result panel shows exact source excerpts, document/chunk/version citations and separate combined, semantic and keyword scores. Open Search receipts to inspect a previous result against current permissions. Refresh history while a recovered receipt is processing.

## Implemented algorithm and boundaries

The optional [one-result-per-document mode](RETRIEVAL_SOURCE_DIVERSITY.md) selects
distinct documents after scoring. Default ranking and scores are unchanged.

The worker builds Unicode word-token counts, smoothed TF-IDF vectors, row-normalizes them and fits a truncated singular-value decomposition to this authorized corpus. Latent dimensions are capped by the requested value, half the smaller matrix dimension (minimum one), and numerical rank. It projects the query into that space and combines clipped cosine similarity with BM25 scores normalized by the largest keyword score in that query. Weights/threshold are 0–1; top-k is 1–10. A score is not calibrated confidence. Small or unrepresentative corpora can produce poor or identical latent similarities; relevant-word co-occurrence and a representative evaluation corpus are necessary.

This is a real local ranking implementation, not neural embeddings, a hosted model, ANN/vector database, learned reranker, translation, generated answer or a claim of multilingual semantic quality. It does not index or send content to an external provider. Arabic word matching is tested; Arabic relevance, morphology, translation and RTL/device acceptance remain open. A fixed synthetic co-occurrence regression proves that the LSA path can rank a related term with no literal query match; this is not a production benchmark.

## Scope, privacy and integrity

Documents are filtered by organization, staging environment and current document ACL before fitting the corpus. Selected source IDs and revisions must match. After ranking, the complete selected source scope is checked again; changed access/version/content invalidates the result. Saved receipts contain source identifiers, revision/hash/position and scores. Every history read rechecks current ACL/revision/chunk hash before rehydrating an excerpt. Revoked/stale hits are withheld. Query text and excerpts are not persisted in search receipts; query/request hashes and counts are retained. Original source content remains in the document subsystem. An upstream reverse proxy must also avoid request-body logging.

POST /v1/hybrid-search requires authentication, CSRF and an author-scoped 16–100 character idempotency key. Changed intent with the same key returns a conflict. POST /v1/hybrid-search/recover accepts that key and returns only this author's scoped receipt. GET /v1/hybrid-search/history lists your history; policy administrators can inspect organization history, still subject to source access checks. Private receipt internals are excluded from generic workbench listings.

## Bounded execution

Limits are 20 documents, 128 chunks of at most 700 characters, 1,024 vocabulary terms, 30 admitted requests per minute per organization, two in flight per organization and 1,000 retained search receipts. Reaching a limit returns an explicit error; no source is silently omitted. The UI directory displays up to 200 visible documents. Runtime admission uses a shared-database organization lock; PostgreSQL concurrency acceptance is still required. A crashed processing receipt is marked interrupted on a subsequent new search after 120 seconds. New work fails closed when receipt capacity is reached; automated search-receipt retention/archival is not yet implemented.

Ranking runs in a child process with a sanitized environment and one BLAS thread. The parent enforces an eight-second deadline, bounded output and process termination. POSIX adds six CPU seconds, 1 GiB address-space and 8 MiB file-size limits. Temporary inputs are removed on normal completion. This is not a complete OS/container network sandbox, nor guaranteed crash-cleanup. Windows process termination and native dependency installation are not verified in this release. NumPy 2.3.5 is pinned in backend requirements.

## Verification and remaining work

Twelve new backend tests cover real LSA, idempotency/recovery, ACL filtering, source changes during computation, malformed worker output, corpus/rate/concurrency limits, interruption, query privacy, cross-account access and Unicode matching. Before a production search release, implement/accept the chosen persistent index and embedding/reranking architecture, relevance datasets, per-source ingestion/ACL synchronization, scalable quotas and retention. The semantic-retrieval workstream is partial.

Algorithm references: https://numpy.org/doc/2.3/reference/generated/numpy.linalg.svd.html and https://scikit-learn.org/stable/modules/decomposition.html#lsa . This source uses NumPy directly; scikit-learn is not a runtime dependency.


## Arabic search normalization

Current search tokenization supports common Arabic vowel-mark, tatweel, presentation-form and letter variants. Original excerpts and citation hashes remain unchanged. Saved searches expose their tokenizer version; older receipts retain their original scores and are labelled as an earlier method. See [Arabic search](ARABIC_SEARCH.md) for matching rules, examples and limits.
