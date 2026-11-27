# Stored neural index runtime

This review increment connects schema-12 storage to normal scoped APIs and the
Knowledge retrieval dashboard. It builds on the storage foundation in PR #86.
It does not apply a migration or enable a model on an existing installation.
Read [the schema-12 upgrade instructions](UPGRADE_SCHEMA_12_VECTOR_STORAGE.md)
before applying this source to an older database.

## Operator and user flow

The existing disabled-by-default local embedding settings remain authoritative:
`NEXUS_OLLAMA_EMBEDDING_ENABLED=1`, an explicit installed model:tag and its
64-character digest. The client cannot supply model identity or vectors. There
is no model pull, remote provider selection or configuration write in this UI.
Use a separately approved configuration and installed model before real use.

Select current documents in Knowledge retrieval and name a snapshot. Building
requires `operate` permission and explicit source IDs/versions; an empty selection
never selects every document. Up to 32 current passages from 20 documents are
sent to the fixed loopback worker. Digest checks bracket embedding execution.
Validated normalized vectors are stored with the source and model snapshot.

Choose a saved snapshot and search it. Only the query is embedded; stored source
vectors and source text are not sent to the model again. The server checks actor,
environment membership, ownership, model digest, all source ACLs, versions,
content hashes and vector integrity both before dispatch and at completion.
The dashboard requests five results, one per document, minimum similarity 0.15.
Results use the existing citation display and search history. There are no
generated answers, calibrated confidence scores or semantic quality acceptance.

## Routes and receipts

| Route | Purpose |
| --- | --- |
| `GET /v1/neural-indexes` | Own or policy-admin metadata in the current environment |
| `POST /v1/neural-indexes` | Build from named, pinned source versions; requires an intent key |
| `GET /v1/neural-indexes/builds` | Paginated scoped build receipts |
| `POST /v1/neural-indexes/recover` | Recover an author's build receipt by intent key |
| `POST /v1/neural-indexes/search` | Query a current saved index; requires an intent key |
| `DELETE /v1/neural-indexes/{id}` | Reviewed removal with current version and audit note |

Build and query receipts are reserved before worker dispatch. A repeat intent
returns its original receipt; changed payloads conflict. Removing index metadata
does not remove the build execution receipt or permit that intent to rebuild.
Receipt recovery never calls the model, including after removal or disabling the
model. A failed/interrupted receipt requires a new explicit intent for new work.
Query receipts recover through the existing hybrid-search recovery endpoint.
Browser recovery stores a key, fingerprint and timestamp, without query text or
vectors. Build and indexed-query recovery namespaces include actor/workspace/
environment and remain distinct from direct search.

Builds, direct searches and indexed queries share workspace/environment limits:
two in flight, 30 starts/minute and 1,000 retained retrieval receipts. Interrupted
work is fenced at completion. Each snapshot still counts toward the 20-index
limit until reviewed removal, including invalidated snapshots. Source changes
purge affected active vectors transactionally. Backups, WAL and storage erasure
remain separate retention responsibilities.

Successful worker-backed receipts report four local HTTP requests: two digest
checks, model capability inspection and one embedding batch. Failure counts are
unknown rather than falsely zero. These unsigned receipts describe execution,
not independent provenance, customer acceptance or production readiness.

## Verification

`test_neural_index_runtime.py` uses normal APIs and synthetic HTTP transport for
build, stored-vector query, durable replay after removal, receipt isolation,
access boundaries, invalidation, reviewed removal, shared concurrency admission,
source/configuration changes during work and malformed worker output. Storage
tests reopen a separate synthetic SQLite restore and search its saved index
through the normal API, then reject another role's access without dispatch.
Backup checksum validity and restored application use are checked separately.

No test contacts a live model or customer system. Remaining work includes
representative real-model/bilingual acceptance, scalable index lifecycle,
learned reranking and deployment validation. The active pilot remains unchanged.
