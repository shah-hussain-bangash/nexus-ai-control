# Phase 1: controlled environment membership

Review increment based on 0.16.2 and schema 9. This adds owner-controlled
assignment management to the existing environment inventory and runtime access
guards. It does not activate runtime environment switching or complete the
workspace lifecycle production gate. Release numbering is reserved for an
approved release; the review branch keeps 0.16.2.

## Owner workflow

Open **Workspace settings → Environment setup → View assignments**. The dialog
shows assigned members and eligible active members from the same workspace.
Choose an assignment or removal, review the member and environment, provide a
5–500 character reason, and acknowledge the session sign-out effect before
confirming. Cancel and closing the dialog perform no write.

Each successful change signs the affected member out of all existing sessions.
The account, password, organization role, other environment assignments and
business records are preserved. Removing staging membership blocks a new sign-in
until an owner restores that assignment. Reassigning a member does not revive
old sessions. An inactive member must be activated before a grant.

Current owners' staging assignments are protected from both grant and removal
through this endpoint. Preparing environments may have assignments, including
owners, but still do not allow runtime access. Changing an owner's own Preparing
assignment signs that owner out too; their protected staging assignment remains.
Archived environments are read-only until restored, and retain their assignments.
Organization roles remain authoritative; no per-environment roles are introduced.

## API and consistency

- `GET /v1/workspace-environments/{key}/assignments` returns assigned members,
  eligible candidates, the environment record/version and `editing_enabled`.
  Each member includes an opaque revision covering current identity and sessions.
  The existing 200-member workspace bound applies. No passwords, identity bindings
  or session identifiers are returned by this endpoint.
- `POST /v1/workspace-environments/{key}/assignments/control` accepts `user_id`,
  `command` (`grant` or `revoke`), `expected_version`, `expected_member_revision`,
  `note`, and `reviewed: true`. Owner permission, CSRF and workspace checks apply.
- Writes serialize through the organization and environment rows and lock the
  target user. They reject stale environment/member revisions, duplicate grants,
  missing assignments, inactive grant targets and archived environments. Each
  success advances the shared environment version and appends an audit event.
- A PostgreSQL read locks the organization while producing the assignment
  snapshot. Identity/session changes after review are checked again at commit
  admission through the member revision. These checks do not claim to prevent a
  member from signing in after a successful grant.
- Lost, malformed or mismatched acknowledgements never trigger automatic retry.
  Refresh assignments and inspect current membership before another confirmation.
  Stale/failed requests disable submission until refresh. A successful write with
  a failed refresh is reported as saved, with refresh or sign-in required.

The existing runtime guards check committed revocation before new work at their
documented dispatch/delivery boundaries. Revocation cannot undo delivered data
or an external operation already dispatched; retain the reconciliation workflow
for uncertain outcomes. This is application authorization, not database row-level
security or cancellation of an external effect.

## Validation and review

- Full Windows backend regression: 359 passed, 20 service/platform skips.
- New API cases cover grant/revoke, fresh sign-in, account preservation, tenant
  and owner boundaries, CSRF, malformed/unreviewed input, stale member/environment
  revisions, archived/preparing environments and queued dispatch after revocation.
- A PostgreSQL concurrency case requires exactly one successful writer for two
  changes sharing the same reviewed environment version. GitHub CI supplies the
  live PostgreSQL and policy results; a SQLite skip is not PostgreSQL evidence.
- Frontend: 58 tests, including protected owners, candidate provenance, review
  confirmation and complete acknowledgement checks. Both app builds pass.
- Disposable browser review covered removal, reassignment, stale review after a
  member signs in, explicit refresh, keyboard navigation and mobile light/dark
  layouts. The synthetic preview continues to reject access changes.

No live account or assignment is changed by developing or reviewing this branch.
After approval, update source, rebuild and restart from schema 9; no migration is
needed. Before approving source activation, review all CI results and the session
sign-out behavior. Runtime switching, promotion and cross-workspace membership
remain future increments.
