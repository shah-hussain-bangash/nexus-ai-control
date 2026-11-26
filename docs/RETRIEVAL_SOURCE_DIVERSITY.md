# One result per document

The local hybrid search form has an optional **One result per document** mode.
It keeps the highest-ranked qualifying chunk from each authorized document,
then returns up to the requested top-k distinct documents. The default allows
multiple chunks per document and retains the previous behavior.

This is useful when several highly ranked chunks from one document would fill
the result list. It can return fewer results when too few documents qualify.
Turn it off when multiple passages from the same document are useful. It does
not judge whether documents are independent, deduplicate copies stored as
different document records, or guarantee better answer quality.

The local TF-IDF/LSA and BM25 scores and threshold are unchanged. Selection runs
over all qualifying candidates before top-k truncation, preserving their score
order and deterministic position tie-break. No neural model, learned reranker,
provider call, vector database or extra dependency is introduced. Existing
20-document/128-chunk, vocabulary, rate/concurrency and child-process limits
remain.

`POST /v1/hybrid-search` accepts optional strict boolean `one_per_document`.
Document group identifiers are derived from the already-authorized database
snapshot, not accepted from clients. The worker checks the bounded group map;
the parent rejects results with repeated documents when the mode was requested.
ACL filtering still happens before fitting, full source-scope checks still
happen at completion, and history reads still withhold stale/revoked excerpts.

The chosen mode is saved in receipt parameters and shown with the saved result.
The checkbox's current value cannot relabel an older receipt. Changing the mode
under the same idempotency key is a conflict; recovery returns the original
mode. Omitted/false retains the exact previous fingerprint. Query text, source
excerpts and the internal group map are not added to persisted receipts.

No database migration or active configuration change is needed. This is an
independent development PR based on main, separate from the unmerged workflow
PRs. Development checks use disposable synthetic documents and include actual
child-process ranking, default compatibility, worker-result rejection,
idempotency/recovery, source revocation/version changes and privacy. The native
Windows run skips an existing POSIX-only process-group test. This does not grant
bilingual relevance, customer-data, scale or production acceptance.
