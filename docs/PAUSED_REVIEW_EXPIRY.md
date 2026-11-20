# Paused independent reviews keep their expiry deadline

Pausing an agent run at an independent review checkpoint does not suspend or extend its review window. Resume already rejected an expired review, but the worker previously swept only runs whose status was `waiting_review`. A paused review could therefore remain active indefinitely and continue consuming one of the workspace's 50 active-run slots until an operator cancelled it.

The worker now also expires a run that is paused with a saved resume state of `waiting_review` once its existing deadline is reached. It marks the pending approval checkpoint expired, advances the run version, clears its lease through the normal terminal transition and records the existing scoped `agent_run.review_expired` event. Cursor and review deadline are preserved. The expired run stops consuming active-run capacity and cannot be resumed, retried or approved; an operator creates a new reviewed intent when needed.

The same checkpoint-status update applies to normal waiting reviews so the run and its pending checkpoint agree. Repeated worker polls do not repeat the expiry event or increment the terminal run version again. Paused runs waiting to execute a checkpoint or observe an action are outside this expiry rule. A timely paused review can resume at its original deadline, and an already approved/queued run is not expired merely because its historical review deadline later passes.

This does not pause the clock, approve a checkpoint, cancel an already submitted business action or dispatch a new one. Existing publication/business approval rules, unknown-outcome reconciliation, pause/resume controls and manual retry restrictions remain. Regression tests use a controlled clock and disposable runs to cover paused/unpaused expiry, exact deadline equality, timely resume/approval, unrelated paused work, audit idempotence and freeing an exhausted active-run quota.

No database migration, public request field, dependency, frontend change or customer connection is introduced. This is a durable workflow lifecycle correction, not customer acceptance or production readiness.
