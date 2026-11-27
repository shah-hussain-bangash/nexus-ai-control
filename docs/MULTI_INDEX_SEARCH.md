# Bounded search across saved neural snapshots

This development increment searches up to eight compatible saved snapshots with
one query embedding. It extends PR #89 without another schema migration. It does
not activate embeddings, upgrade the running database, or change the active app.

## Combined search

`POST /v1/neural-indexes/search` accepts either the existing `index_id` or a new
`index_ids` list of 1–8 distinct IDs. They are mutually exclusive. List order is
canonicalized before fingerprinting, so replaying the same selection in another
order returns the original receipt. Existing single-index fingerprints remain
unchanged. The usual query, top-k, minimum score, diversity and intent-key controls
still apply; no client vectors or model settings are accepted.

All snapshots must belong to the current authorized scope, be ready, use the
operator-pinned model/digest and have matching dimensions. Every snapshot's actor,
source ACLs, current versions, hashes and vector integrity are checked before
dispatch and again at completion. One invalid, inaccessible or changed snapshot
rejects the entire search. No partial result is exposed or silently omitted.

The fixed local worker embeds only the query once. Its successful four-HTTP-call
protocol is unchanged: digest checks, capability inspection and one embedding
batch. Stored source passages/vectors are not sent to the model again. Parent-side
ranking merges each snapshot's candidates, keeps the highest score for overlapping
passages, applies document diversity across the union and truncates to the global
top-k. Ties use document ID and passage position. Scores are not confidence.

Each snapshot retains its existing 32-passage/20-document/2-MiB bounds. Combined
search can inspect up to 256 vector rows over eight snapshots; corpus/source
counts report distinct passages/documents rather than duplicate copies. This is
bounded local composition, not ANN indexing, an unbounded vector database,
background index builds, automatic refresh or learned reranking.

## Dashboard and historical evidence

Choose a primary saved snapshot, then optionally select compatible additional
snapshots. The query searches the whole selection; reviewed removal still applies
only to the primary snapshot. The dashboard shows the combined snapshot count.
Lost-response recovery uses the existing scoped indexed-search intent and never
reruns the model.

Search parameters pin every selected index/version. Quality-review creation
validates all selected snapshots and captures every snapshot plus all source
versions. Review reads become stale if any snapshot changes or is removed; source
ACL loss still hides the evidence. Comparisons use the complete snapshot sets,
report index/corpus changes, and retain same-query/actor/label/control requirements.
Older single-snapshot review records remain readable without rewriting them.

## Focused development checks

Disposable API checks cover overlap deduplication, one embedding request, combined
corpora over 32 passages, eight-snapshot operation, invalid selections, global
diversity/top-k, scope isolation, incompatible model identity, completion-time
source changes, receipt replay, review/comparison lineage and removal staleness.
Single-index runtime, review and comparison checks cover compatibility. Frontend
checks cover the unchanged single-index payload, copied/canonical combined
selection and the eight-snapshot bound; the dashboard build is checked as well.

Only focused engineering checks are performed during development. Full acceptance,
real-model quality/load tests, merges and deployment are later steps. Background
indexing, larger-scale storage, reranking and representative model acceptance
remain unfinished development/acceptance work.

[Checkpointed background builds](BACKGROUND_INDEX_BUILDS.md) now queue bounded snapshots, resume saved batches, and publish completed indexes through the existing worker. Larger-scale storage and learned reranking remain separate work.
