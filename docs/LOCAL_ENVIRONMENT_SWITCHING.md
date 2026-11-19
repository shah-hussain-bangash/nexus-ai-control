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

## Remaining scope

Pilot activation, controlled imports/promotions, active-environment retirement, independent security review and deployment acceptance remain future work. Active environments cannot be archived through preparation controls. No deployment acceptance is granted by the local tests or a recorded operator attestation; workspace/environment lifecycle is marked partial in the roadmap.
