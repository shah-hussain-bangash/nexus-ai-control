# Workflow attention filter

The durable execution dashboard has a **Needs attention only** filter. It shows
checkpoint reviews, failed/expired/rejected workflows, uncertain outcomes, and
active runs whose current linked action needs approval or has stopped. A paused
workflow with an already-submitted approval or uncertain effect remains visible.
Normal queued/executing work, completed runs and fully cancelled runs are not
included unless their workflow state itself needs attention.

The normal-session API is `GET /v1/agent-runs?attention_only=true`. Filtering is
performed before the existing ordered pagination, within the current workspace
and environment. The default unfiltered API remains available. Only the current
step's action can contribute to the filter; an older action cannot pull an
unrelated later checkpoint into this queue.

Switching the filter resets pagination and selection. Responses from an older
list request cannot replace the current filtered view. A previously selected run
that leaves the attention queue is not fetched back into it by selection recovery.
Background polling waits for an in-flight list response instead of repeatedly
superseding it. Explicit refresh and view changes can replace an older request;
late cleanup cannot release a newer request or populate another view.

This is an inspection view. It does not dispatch, retry, approve, reconcile,
cancel or compensate any effect. Use the existing independent review, business
approval and reconciliation controls after inspecting the original record. A
run leaving this filter is not proof of success: for example, a paused run whose
business approval was granted still waits for an operator to resume it.

No schema migration, scheduler, autonomous planning or automatic dead-letter
replay is introduced. This addition builds on the run-evidence change in PR #74;
formal customer workflow and deployment acceptance remain separate work.
