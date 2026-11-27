# Bounded larger-corpus index collections

This development increment accepts a selected corpus of up to 256 current passages
from at most 20 documents and partitions it into up to eight ordinary 32-passage
background snapshots. It builds on PR #92, retains schema 12 and adds no migration.
It does not alter the running app or start workers/model requests.

## Admission and execution

`POST /v1/neural-index-collections` takes the existing build shape: name and pinned
source IDs/versions, with an intent key. All source access/version/hash and bounded
batch inputs are checked before committing any work. The full set must fit the
existing 20-snapshot, 20-unfinished-job and shared retrieval rate/history limits.
If any reservation fails, the entire transaction rolls back: there is no partial
queue or silently omitted source. The collection and each child consume a shared
retrieval receipt/admission slot; a large collection therefore needs sufficient
remaining admission capacity for its complete set.

Partition order follows document ID and passage position. Every selected passage
belongs to exactly one child; documents may span children. Child names identify
their collection and ordinal. The existing background worker performs eight-passage
checkpoints, current actor/configuration/source checks, lease fencing and explicit
uncertain-batch resume. No new scheduler or automatic retry service is introduced.
Queued submission and lost-response recovery do not invoke a model.

Each child publishes independently. Completed children may be explicitly used as
ordinary snapshots, but the collection's full-set selection remains unavailable
until every child is complete, every snapshot is ready with matching dimensions, and captured source access
and versions remain current. Metadata readiness is not vector-integrity acceptance:
the existing multi-index query checks all selected snapshots again at use time.

## Dashboard and lifecycle

**Larger index collections** queues the full corpus, recovers a submission, displays
child progress and confirmed/unknown HTTP-call counts, and selects the completed
set in Stored neural indexes. Selection does not run a query. The configured
embedding model/digest must match before the dashboard enables that selection.
Refreshing/choosing a new selection fences older snapshot-list responses. A changed or incompatible selected snapshot blocks querying instead of silently shortening the selection.

Pause, resume and uncertain-batch acknowledgement remain individual child controls
in Background index builds. **Cancel unfinished collection builds** requires a
fresh token over the displayed child states plus a note. In-flight cancellation
still takes effect at a safe batch boundary. Completed snapshots and all receipts
remain; they are not silently deleted. Historical checkpoint progress can include
vectors subsequently purged by cancellation/failure, so progress is distinct from
readiness. A failed/cancelled child makes a collection incomplete; changed/removed
snapshots or lost source access make it stale. It never returns a shortened set as
the complete collection.

Collections are author or policy-admin scoped in the bound workspace/environment.
They are excluded from generic workbench responses. Active collections sort before
recent terminal records, with pagination. Recovery reads the original collection
without execution, including after cancellation. Reusing its key with changed
sources/name conflicts. A new build requires a new explicit intent.

Routes:

- `GET /v1/neural-index-collections` — active/recent scoped collection metadata.
- `GET /v1/neural-index-collections/{id}` — current collection/child progress.
- `POST /v1/neural-index-collections/recover` — author's intent-key recovery.
- `POST /v1/neural-index-collections/{id}/cancel` — reviewed unfinished-child stop.

Existing single-snapshot jobs, combined search, quality review/comparison and
optional reranking are retained. Source-version/index lineage is handled by the
existing child snapshots and multi-index search receipts. No query text, vectors
or source passages are copied into collection receipts.

## Focused development checks and boundaries

Disposable checks cover a corpus over 32 passages through worker publication,
combined query and saved review; whole-set readiness; atomic capacity/rate/job
rejection; reviewed partial cancellation; source staleness; scope/version fences;
and the eight-snapshot/256-passage limit. A 252-passage selection produces eight
gap-free child partitions without executing a model, while 264 passages reject
before any staging records are committed. Existing job/runtime/combined-query
checks cover compatibility. Frontend checks cover complete-set selection, model
compatibility and separate lost-reply intent; the build is checked.

Full acceptance, model quality/load evaluation, merges and deployment remain
deferred under the development-first plan. This is bounded local partitioning,
not an ANN/vector service, an unbounded index, automatic source refresh, a new
retention/erasure policy or a production-readiness claim.
