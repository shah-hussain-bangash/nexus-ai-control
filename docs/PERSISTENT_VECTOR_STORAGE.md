# Persistent vector storage foundation — schema 12

The storage foundation adds dedicated `neural_indexes` and `neural_vectors`
tables and trusted server-side storage/ranking functions. The subsequent
[runtime integration](RUNTIME_NEURAL_INDEXES.md) connects build/query APIs and
dashboard controls. The capability is enabled only with pinned local embedding
configuration; no endpoint accepts client-supplied vectors.

## Storage and authorization

`neural_index_store.py` supports create/replay, metadata inspection, internal
vector ranking and reviewed removal. Callers establish the runtime context and
own the transaction. The layer refreshes the current actor, checks active
environment membership, scopes every query by organization/environment and
restricts an index to its author or policy administrators. All referenced source
documents and chunks must still be readable and match their versions/content
hashes before vectors can be stored or used.

An index pins an explicit model:tag and 64-character model digest. The caller
must supply vectors produced by its trusted model-bound worker; no HTTP endpoint
accepts client vectors. Matching a supplied tag/digest does not establish model
provenance or semantic quality. Query vectors are not persisted and this module
makes no model/provider calls.

Snapshots support up to 32 distinct passages from 20 documents, 4,096 dimensions,
2 MiB serialized prepared entries, and 20 metadata records per workspace and
environment. Invalidated records count toward capacity until explicitly removed.
Vectors must be finite, nonzero and dimensionally consistent; stored vectors are
normalized. Source snapshots and prepared vectors have a consistency hash.
This detects inconsistent stored data, not malicious database rewriting or
authenticated provenance.

Ranking checks sources again and uses bounded positive cosine similarity, with
optional document diversity before top-k. Results contain current authorized
citations/excerpts and scores, never raw vectors. Generic row serialization also
excludes the vector column. Metadata inspection returns the author's index name
and technical state without source IDs, source text or vectors.

## Source lifecycle and retention

Normal content replacement, reader changes and document deletion invalidate every
affected snapshot and delete **all active vector rows** in those snapshots in the
same source-update transaction. An independent index is preserved. Failure or
rollback of the source transaction preserves the previous vectors and state.
Use-time checks also reject direct source/ACL changes that missed eager invalidation.

Removal requires the current index version and an audit note. An author can remove
invalidated metadata without recovering access to its former sources. This is
logical removal from active tables; database pages, WAL, backups and retention
erasure remain separate operator responsibilities. No automatic backup, retention
schedule or forensic-erasure guarantee is introduced.

Storage-key replay lasts while its metadata record exists. Removing metadata also
removes that key; it is not a durable receipt for a model-provider execution.
Runtime build integration now reserves a separate durable intent before invoking
a model and recovers that receipt without repeating work.

## Upgrade and recovery

Read [the schema-12 upgrade boundary](UPGRADE_SCHEMA_12_VECTOR_STORAGE.md) before
applying this source. Only disposable databases were migrated during development.
The schema-11 upgrade creates the two tables and a new marker; it does not rewrite
accounts, password hashes, document content or existing records. Failed migration
rolls back the new tables/marker; a retry is supported. Earlier environment-registry
migration now discovers only physically existing tables, allowing new schemas to
be initialized in the correct order.

Both tables reside in the normal control database, so existing full database
backup primitives include them. The synthetic recovery test verifies backup file
checksums, copies to a separate restore destination, reopens the application and
queries the stored index through the internal primitive. It confirms a known
document through the normal API and rejects an auditor write with a valid request.
The runtime increment also searches that restored index through its normal API
and rejects another role before dispatch. This is not actual-record recovery,
encrypted restore acceptance, measured RPO/RTO or production readiness.

## Verification and next work

`test_neural_index_storage.py` covers persistence, ACL/actor/environment boundaries,
model mismatch, corruption detection, invalid vectors, document lifecycle,
invalidation rollback, capacity, reviewed deletion, migration preservation/failure
and disposable backup/reopen use. Existing document, session, environment,
request-key migration, workflow evidence and recovery checks cover compatibility.
Schema/storage changes also trigger the disposable Docker recovery CI workflow.

Runtime build/query integration is described in [the runtime guide](RUNTIME_NEURAL_INDEXES.md).
Scalable indexing, learned reranking, representative real-model acceptance and
deployment validation remain separate work.
