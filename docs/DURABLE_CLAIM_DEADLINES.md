# Check durable-worker claims before beginning a step

A durable worker commits a short processing claim, then opens the transaction that handles its current step. Completion already required the same processing status and token, but a worker delayed between those transactions could begin a step after its lease ended when no other worker had swept the expired claim.

The worker now checks the lease deadline after locking and matching the claimed run, before fingerprint checks, cursor advancement, linked-action observation or new governed-intent submission. At or after the deadline, it performs the same recovery transition as the normal expired-claim sweep and returns without processing a step in that call. The idle sweep now treats exact deadline equality as expired too.

Recovery preserves the saved cursor, step state, cancellation flag and any existing linked action. It clears the old lease, increments the existing recovery/version counters, records `WORKER_LEASE_EXPIRED` and writes the normal scoped recovery event. The existing budget allows three automatic recoveries across a run; further recovery makes it failed. Existing manual retry restrictions remain. A later valid poll observes an already submitted action through its saved ID rather than creating another business intent. Existing outbox idempotency and approval controls still govern dispatch.

The check is a cutoff before beginning the step transaction's work; it does not retract an external action already dispatched or introduce a new timeout for work already running under that transaction's row lock. Superseded tokens, pause/cancel controls, review expiry and unknown-outcome reconciliation retain their existing behavior. There is no lease extension or new recovery budget.

Regression tests advance a controlled clock immediately after the claim transaction commits, without long sleeps. They cover exact/late deadline checks before checkpoints and governed actions, timely execution, recovery-budget exhaustion, existing-action observation with exactly one synthetic effect, and idle recovery at equality. The original implementation advances the checkpoint under an expired claim; the new regression reproduces that behavior before the fix.

No schema migration, public request field, dependency, frontend or customer connection is added. This strengthens durable execution recovery and does not grant customer or production acceptance.
