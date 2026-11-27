# Checkpointed background index builds

This development increment adds queued, bounded local embedding builds to the
existing execution worker and Knowledge dashboard. It builds on PR #90, uses the
existing schema-12 tables and adds no migration or running-app configuration change.

## Queue and progress

Select current documents and name a background snapshot. The queue API returns a
durable job immediately, without invoking the model. The normal execution worker
(`python -m nexus.worker` in the backend) processes one batch of at most eight
passages per iteration alongside existing action/workflow/intake processing. The
existing startup flow must have its worker running; queuing in the API alone
does not execute the job. No new worker is started by this review change.

Builds retain the 32-passage/20-source/2-MiB prepared-vector limits and the pinned,
disabled-by-default local embedding configuration. A staged snapshot reserves one
of the environment's 20 metadata slots and is marked `building`. Search and direct
snapshot removal reject it. Normal document source changes also invalidate an
empty stage before any vectors exist. No endpoint accepts client vectors or model
settings, and checkpoint receipts do not copy source text or vectors.

Each completed batch commits vectors in `neural_vectors` and its offset/checksum
in the job in one transaction. Vectors remain unavailable for query until the
entire snapshot passes current actor/membership/permission, operator-model,
source-version/ACL/hash, vector/dimension and final-size checks. Publication flips
the snapshot to `ready` with a new version atomically. Resume uses saved batches;
it does not recompute them. Checkpoint corruption fails closed and purges staging.

The dashboard queues jobs, recovers a lost submission, shows passage progress,
and provides reviewed pause/resume/cancel controls. Refresh reads actual worker
progress. Controls require the displayed job version and a note. Active builds
are listed before recent terminal receipts, within a 50-record response.

## Interruption and controls

Pause/cancel requests during a model batch retain its in-flight reservation until
the batch completes or its lease expires. Pause takes effect at the boundary and
preserves a valid checkpoint; cancellation discards the returned batch and purges
all active staging vectors. A finished last batch may complete before a pause.
Terminal receipts remain; staging metadata can then be removed through the
existing reviewed removal control. Checkpoint progress on a terminal receipt is
historical and does not assert that purged vectors remain available.

Each claim has a unique token and 120-second lease around the existing bounded
embedding child. Expired work becomes `interrupted` without automatic replay.
The completion path checks the lease again before checkpoint publication, using
a savepoint to roll back a late batch while preserving earlier checkpoints. A
cancel request is honored after lease expiry without replay. Stale worker tokens
cannot publish. Other queued jobs remain eligible while one lease is active.

Explicit resume of an uncertain batch requires acknowledging that its uncommitted
model request may already have executed and can run again. There are at most three
attempts for one uncommitted batch; committed batches reset that attempt counter.
Resume cannot change the original model or sources. Changed/revoked sources or
operator configuration block progress; start a new reviewed intent instead.

Confirmed local HTTP calls are counted separately. Each successful batch confirms
four local requests. Total calls remain unknown after an uncertain interruption,
even if the job later completes. This is not an exactly-once model-execution claim.

## API and capacity

- `POST /v1/neural-index-jobs` queues a name and pinned source IDs/versions with an
  intent key; repeat keys recover the same job, including after cancellation.
- `GET /v1/neural-index-jobs` lists active/recent jobs in the current scope.
- `GET /v1/neural-index-jobs/{id}` reads progress.
- `POST /v1/neural-index-jobs/recover` reads the author's original job by intent key.
- `POST /v1/neural-index-jobs/{id}/control/{pause|resume|cancel}` applies a reviewed
  version/note and explicit uncertain-resume acknowledgement where required.

Jobs are author or policy-admin scoped. Worker execution uses the original active
author and bound workspace/environment, with current membership/operate checks.
Jobs share retrieval history/rate limits and the two in-flight reservations with
search/build requests; at most 20 unfinished jobs are admitted per environment,
also subject to snapshot capacity. Paused/interrupted jobs do not dispatch until
explicit resume. No automatic expiry, retention/erasure schedule, source refresh,
external queue service or unrestricted corpus growth is introduced.

## Focused development checks

Disposable checks use synthetic embedding transport for nonexecuting enqueue and
recovery, searchable publication, multi-batch pause/resume, cancellation during a
batch, expired startup/completion leases, late-publication rollback, requester
revocation, checkpoint corruption, source invalidation before the first batch,
shared admission, concurrent worker claims and scoped/versioned controls.
Related storage/runtime and combined-search checks cover compatibility. Frontend
checks cover source-version snapshots and separate lost-reply recovery intent;
the dashboard build is checked. No live model/customer system or actual database
is contacted. Full acceptance and deployment remain deferred.

Reranking, larger-scale storage/indexing, representative model quality and the
other unfinished roadmap workstreams remain separate development work.
