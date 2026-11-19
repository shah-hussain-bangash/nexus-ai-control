# Phase 1: environment-scoped design handoffs

This increment scopes exported design reviews to workspace, user and runtime
environment, and fences late local-file imports. Public runtime access remains
staging-only. Source/schema remain 0.16.2/10; there is no database migration,
activation operation or environment selector, and Phase 1 remains incomplete.

## Handoff contract

- New exports use `nexus-ui-review` schema 2, release 0.16.2, with an explicit
  `workspace_scope.environment`. Full and review-only exports follow the same
  scope checks. Download names include the environment.
- Scope comes from authenticated `me.environment`, not the UI's simulated
  Staging/Production design selector. Imports require the same workspace, user
  and environment before becoming candidates. Applying a candidate checks its
  destination again; export and import also require the mounted session epoch.
- Schema 1 files from 0.15/0.16 remain importable only in staging for the matching
  workspace/user. Their examples and valid four-part review checklists are
  preserved. Re-export produces explicit environment scope.
- Unscoped 0.14 legacy examples remain staging-only, with the existing explicit
  confirmation and warning that ownership is unverified. Review attestations are
  cleared. Declared conflicting scope, unsupported schemas and release/schema
  downgrade attempts are rejected rather than silently reinterpreted.
- File size, safe JSON, catalog completeness, example field validation, bounded
  event histories and false runtime/production-acceptance flags remain enforced.
  These files are editable local design data, not signed provenance, credentials
  or authorization. Scope metadata cannot certify production or grant access.

## Client-state review

Design examples and review markers currently live in component memory and are
retained through handoff exports; there is no hidden local-storage design database
to migrate. The session epoch reset from the previous increment clears that view.
File reads capture a validated target scope and a selection ticket. A changed
epoch, later file selection or unmount prevents an older file from becoming an
import candidate or replacing current feedback.

Existing runtime recovery storage is already keyed by workspace/user/environment
and remains untouched. Member provisioning intentionally stays workspace/user
scoped because it creates workspace accounts. Appearance and text-size settings
remain device preferences; they contain no workspace records. No new browser
storage keys or automatic file conversion are introduced.

## Validation and application

All 79 frontend tests and the production build pass. Eight new cases cover
explicit scope, full/review-only exports, preserved older staging reviews,
downgrade rejection, legacy review handling, malformed destinations, candidate
scope checks, late files and captured scope/selection ordering. Existing recovery,
session-context and uncertain-action key tests continue to pass.

Backend source is unchanged from the schema 10 increment. Require all four GitHub
checks before applying. Take a private backup, update source and rebuild the
frontend, restart and verify readiness and preserved records/configuration. No
account, session, password or assignment changes are needed. Existing handoff
files stay on disk until the user deliberately imports/re-exports them.

Runtime key uniqueness constraints, activation/provisioning, atomic context-changing
selection, remaining raw/service paths and final isolation acceptance still need
review before enabling public environment switching. Preserve shared inference
spending and admission limits.
