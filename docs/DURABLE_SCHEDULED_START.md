# One-time durable workflow start

The durable execution create-run form accepts **Start once at** in the current
computer's local time. Leave it empty for the existing immediate-start behavior.
Choose a future time within seven days. The browser converts that local value
to a fixed UTC Unix timestamp; the server validates its own clock and stores the
timestamp in the immutable workflow definition. The run detail and unsigned
evidence snapshot display the saved time.

The normal `POST /v1/agent-runs` input has optional `start_at`, a strict integer
Unix timestamp in seconds. Omitted/null retains the exact old immediate-run
fingerprint, including nested null fields. An unchanged scheduled submission
with the same idempotency key returns its original run, including after the
time passes. Changing its time under the same key is a conflict. Intent recovery
returns the original time without dispatching another run.

No checkpoint or action starts before the saved time. The persisted wake-up
hint survives a new application/worker instance, and the worker also checks the
saved time before its first checkpoint. A premature hint cannot authorize an
early start. Pause/resume, an unsubmitted-step retry and expired-claim recovery
preserve the scheduled floor. Cancellation before start remains terminal when
the scheduled time passes.

At start and before new action admission, the existing worker checks current
requester access, agent generation/owner access and pinned connector destination.
Supplier/purchase policy and independent workflow/business approvals remain
required. Scheduling grants no extra permission and does not replay uncertain
effects.

The saved time is an **earliest start**, not a deadline or an exact-time service
promise. The worker must be running; a stopped PC/worker can start overdue work
when it next polls, subject to the current controls. Scheduling uses the server
clock and needs normal clock maintenance. There is no recurring calendar,
event-trigger service, timezone database, distributed cron, missed-run expiry or
autonomous planning in this addition. To change a queued time, cancel the old
run and submit a new reviewed intent with a new key.

No database migration is needed: the definition and next-poll time use existing
schema 11 fields. This source builds on PR #75 and does not update the running
app, accounts or real records. Development checks use disposable databases and
a simulated process clock, not the operating-system clock. Formal pilot,
customer-workflow and deployment acceptance remain separate.
