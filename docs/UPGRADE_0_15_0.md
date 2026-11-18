# Upgrade to 0.15.0

1. Stop all API/worker processes. Back up existing source/configuration/databases and preserve .env, data and backups. Do not replace private files with example settings.
2. Export any current 0.14 UI walkthrough session before leaving it if you need its synthetic examples. The new importer can migrate valid legacy examples; legacy review markers require the new checklist.
3. Extract the source ZIP into a review folder. Copy updated application/frontend/scripts/requirements into your project while retaining private state. Do not copy virtual environments/node_modules from another machine.
4. From C:\nexus-ai-control run scripts\start.cmd. Keep its terminal open and use the new printed URL. Schema remains 8; no account/password reset or new schema migration is introduced by this UI release.
5. Hard-refresh assets, sign in and open Product UI walkthrough. Test a synthetic example, export, leave/reopen and import the handoff. Confirm the replacement summary before restoring. Check the four-part review checklist.

Existing working APIs, workers, approvals, document/OCR intake, business connector, metrics and backup paths are retained. OCR/customer/IdP/cloud integration is not enabled automatically. Follow earlier schema-8 migration instructions if upgrading from older source. Native Windows deployment acceptance remains an operator task.

Rollback: stop writers and restore matching pre-upgrade source/settings/verified backup. Test rollback in an isolated destination first. Never delete databases or reset users to address a UI upgrade.
