# Phase 1: environment setup screen

This document records the initial setup-screen increment. The subsequent member
assignment controls and their current limits are described in
`PHASE_1_ENVIRONMENT_MEMBERSHIP.md`; references below to read-only assignments
describe this earlier increment.

Owners can open **Workspace settings → Environment setup** to inspect their
workspace's environment records, prepare a new environment, archive an unused
preparation record, restore an archived record to Preparing, and view member
assignments. Each change requires a reason, which the existing backend records
in its audit trail.

This increment uses the environment inventory API already merged in release
0.16.1 (database schema 9). It has no dependency on the separate runtime access
pull request #3. It adds no schema migration, password reset or account change.
The review branch retains the 0.16.1 version until a release is approved.

## Boundaries

- New environments remain Preparing. Switching, promotion and assignment editing
  remain unavailable. The lifecycle production gate stays incomplete.
- The current staging environment has no archive or restore control.
- The server remains authoritative for owner permission, workspace scope, the
  20-record limit, existing-record protection and version conflicts.
- Archive and restore send the version shown when the owner opens confirmation.
  A stale version closes confirmation and requires an explicit refresh.
- A lost response or server error disables further changes until the owner closes
  confirmation and refreshes. The UI never automatically repeats a write.
- If a write succeeds but refresh fails, the UI reports the saved change and
  requires refresh before another write.
- The synthetic preview supplies clearly labelled read-only examples. Its API
  continues to reject environment writes.

## Validation

- Frontend: 54 tests pass, including key/reason validation, current-environment
  protection, lifecycle state checks and reviewed-version payloads.
- Both the frontend and isolated synthetic preview build successfully on Windows.
- Manual browser checks against a disposable schema-9 SQLite database: prepare,
  archive, restore, read-only staging assignments, keyboard navigation, light/dark
  form appearance, narrow layout, and hidden controls for an approver account.
- Existing backend environment tests cover owner-only access, tenant isolation,
  stale versions, protected staging and environments containing records.

The disposable browser check does not use the owner's running database, local
account credentials or live provider connections. PostgreSQL and policy checks
run in GitHub CI; this document does not represent production acceptance.

## Review and activation

Keep this change on its review branch until approved. Review the Settings screen,
the frontend validation tests and the synthetic preview together. After approval,
merge through the normal review process, update the Cursor source and rebuild
the frontend before restarting. No additional migration beyond schema 9 is needed.
