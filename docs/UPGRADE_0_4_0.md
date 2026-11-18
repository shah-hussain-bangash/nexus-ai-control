# Upgrade to 0.4.0

1. Stop every NEXUS API and worker terminal with Ctrl+C. Do not copy a live SQLite file while it is being written.
2. Back up the complete current project folder privately, including environment configuration, all database files, exports and any PostgreSQL backup. Keep the old source with that backup.
3. Extract the new ZIP into a separate folder. Copy your existing environment configuration and complete `backend/data` directory to the corresponding locations. Preserve any other configured database/export paths. Do not use the synthetic `demo-preview` as the application.
4. On Windows, run `.\scripts\start.cmd` from the new project root. The launcher installs dependencies, builds the console, runs initialization/migration and starts API plus worker. The SQLAlchemy migration adds three workbench tables and schema marker 3; it does not reset users, passwords or business records. For PostgreSQL, run the authorized migration in a maintenance window and retain a verified backup.
5. Open the launcher's newly printed URL. Sign in with your existing owner credentials. Select **Load synthetic starter designs** once to add 18 editable design templates. The button is additive and idempotent.
6. Verify prior actions and audit records remain visible. Open Workflow Studio and run a saved design in its test bench. Use the independent reviewer only for real synthetic business-action approvals, before the displayed expiry.

Do not copy `.venv`, `node_modules` or a previous built console into the new release. No generated credentials or development database is shipped in this archive.

## Rollback

Schema 3 is a forward upgrade. Older source refuses newer schemas. To roll back, stop all processes and restore the matching pre-upgrade source, configuration and complete database backup together. Do not remove schema markers or drop tables to force older source to run.

## Verification boundary

This release was tested on Linux/Python 3.12. Native Windows installation, live PostgreSQL, OPA and Keycloak were not rerun for this release; the existing integration harnesses are retained. No customer cloud environment was deployed.
