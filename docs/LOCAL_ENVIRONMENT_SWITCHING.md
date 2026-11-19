# Local environment activation and switching

This release enables isolated environment selection in **local mode**. An environment named `production` is a local namespace, not evidence of production readiness. Pilot mode continues to allow staging only. Database schema remains 11; no migration is needed for this change.

## Owner setup

1. Open Workspace settings and create a preparing environment.
2. Open its Members dialog and assign the required accounts, including yourself as owner. Assignment changes revoke the affected account's sessions. Sign in again after assigning yourself.
3. Choose Activate, review the empty namespace and enter a reason. Activation requires a current version and an assigned active owner. Existing runtime records block activation: there is no implicit import or promotion.
4. Use the header's environment switch button, choose an assigned active environment, save/export unsaved work, and confirm the review checkbox.

Activation creates only an initial policy with purchasing disabled (threshold and maximum zero). It does not copy agents, tools, grants, documents, provider settings, secrets or approvals. Shared workspace identity, membership administration and infrastructure budgets retain their existing workspace scope. Configure each runtime environment explicitly.

## Isolation and recovery

Selection uses the authenticated workspace, session binding, expected session revision and target environment version. Request headers assert the selection; they cannot choose a namespace. Selection increments the revision and rotates CSRF. Client views remount and discard old context; late server responses are checked against fresh session, membership and role state before delivery. Normal human writes and selection use the same workspace lock. Inference preparation is read-only; final admission reacquires this lock and rechecks access and configuration before reserving provider work.

After the first switch, runtime requests must include their selected context ID and revision. Only `/v1/me` and `/v1/session-context` remain unpinned discovery endpoints. Old context headers, concurrent selection attempts and revoked membership are rejected. An uncertain switch outcome triggers discovery rather than an automatic repeat. New sign-ins start in staging.

Background operations keep their persisted origin environment when a browser switches. Workers check active environment membership before work and before publication. A switch does not cancel an existing job or move its result. Audit events record activation and selection in the initiating environment's ledger. Workspace account provisioning receipts remain workspace-wide to avoid duplicate account creation across selections.

## Pause and resume a local runtime

From staging, an assigned owner can choose **Pause runtime** for another active environment in Workspace settings. Review the selected-session count, confirm the checkbox and supply a reason. Pausing preserves records, configuration and membership, blocks runtime access and revokes only sessions selected into that environment. Staging and the initiating session's current environment are protected. Membership editing is unavailable while paused.

Queued or executing actions, pending approvals, unknown outcomes, paused/unfinished durable runs, queued/processing/awaiting-review ingestion and pending/unknown inference block the change. Finish, cancel or reconcile these through their normal controls first. Unknown future status values also block. The server rechecks this activity and the reviewed session count under the same workspace lock used by human and workload admission. A stale snapshot requires refresh; no automatic retry occurs.

**Resume runtime** requires a new versioned owner review and restores access using the existing policies, agents, grants and credentials. Review that configuration before resuming. Resume does not restore signed-out sessions or replay jobs. Members sign in to staging and explicitly select the resumed environment again. Both commands are local-only and audited in the initiating environment. No records, credentials, approvals or budget reservations are deleted or reset. Schema remains 11.

## Retire a paused local runtime

An assigned owner, working from staging, can choose **Retire runtime** for an idle paused environment. Review the warning, enter a reason, type the exact environment key and confirm the review checkbox. Active environments must be paused first. The same environment-version, session-count and unfinished-work checks used by pause/resume apply again under the workspace admission lock. Stale or uncertain results require refresh, not automatic retry.

Retirement is a terminal runtime state in this app: it cannot be resumed, reactivated, restored to Preparing or used for new assignments. The key remains reserved. Existing records, configuration, assignments and credentials are retained; no data is deleted, budget reset, job replayed or external provider credential revoked. Workload access and environment selection stay blocked. Owners can still see the retired inventory entry and retained assignments. Historical runtime rows remain in the database and backups under their original environment; retirement does not copy them into staging. The audit event is recorded in the initiating staging ledger. Schema remains 11 and pilot retirement is unavailable.

## Remaining scope

Reviewed prompt, guardrail and explicitly remapped workflow draft copying is described in [Reviewed design copying](REVIEWED_DESIGN_COPY.md). Pilot lifecycle, general configuration imports/promotions, independent security review and deployment acceptance remain future work. Active and retired environments cannot be archived through preparation controls. No deployment acceptance is granted by the local tests or a recorded operator attestation; workspace/environment lifecycle is marked partial in the roadmap.
