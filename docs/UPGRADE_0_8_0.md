# Upgrade to 0.8.0

Use a staging copy first. This package does not update your running Windows installation automatically.

1. Stop NEXUS with Ctrl+C. Back up the existing project, .env, configured databases and local business data using the existing documented backup process. Preserve the previous source release for rollback.
2. Extract the ZIP to a separate folder. Review UI_COVERAGE_MATRIX.md and IMPLEMENTATION_REPORT.md. Do not overwrite private .env/data/backups with package defaults.
3. Copy reviewed source files into the staging project while retaining its existing .env and database files. The ZIP contains no credentials or production records. For external databases, retain your configured connection and test against staging.
4. Run scripts\start.cmd from the project root on Windows. It builds the UI and starts API/worker. Accounts are preserved; do not reset passwords or erase the database. Schema remains 5 from 0.6.0; older releases follow their documented migration chain.
5. Open the URL printed by the launcher. Sign in with your existing local account, open Enterprise design studio and load examples as a local owner. This adds interface plans only. Existing runtimes are not activated by those plans; your retained environment settings still control live provider access.
6. Verify existing governance flows and the new UI. Roll back using the matching backed-up source/settings/data if staging verification fails. Do not restore a database over an active service.

The separate demo-preview has no real sign-in; its in-memory plan edits disappear on reload and cannot update your installed backend.

Operational metadata is stored inside existing versioned blueprint assets. Older 0.7.0 servers do not understand this new operational_state field; use matching backed-up source/settings/data for rollback. No account reset is required. Copy source files while preserving your private settings and runtime data.
