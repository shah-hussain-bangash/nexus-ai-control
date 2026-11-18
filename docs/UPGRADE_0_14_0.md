# Upgrade to 0.14.0

1. Stop API/workers and back up existing source/private configuration/databases. Preserve .env, data and backups; never replace them with example settings.
2. Extract into a separate folder and review the new UI guide. Copy updated source/frontend/scripts/requirements into your working project while retaining private state. Do not copy a virtual environment or node_modules from another machine.
3. From C:\nexus-ai-control run `scripts\start.cmd`. It installs dependencies, builds the console, preserves initialized accounts and starts the application/worker. Schema remains 8; no schema-9 migration or account reset is introduced.
4. Use the newly printed URL and hard-refresh. Open Product UI walkthrough. The normal starter serves the compiled authenticated frontend; demo-preview is a separate synthetic QA harness.
5. Review a synthetic example, persona-specific decision, evidence and phase plan. Export before leaving the walkthrough. Existing design plans persist through Enterprise design studio; walkthrough examples/checkmarks are session-local.

This release changes the UI layer and release/catalog metadata. It preserves the working bounded APIs, document/OCR intake, worker, business adapter, metrics and encrypted backup paths from earlier releases. OCR remains opt-in; no customer connector, IdP or cloud service is enabled automatically.

If your installation predates schema 8, follow the document intake upgrade notes as well. Do not delete databases or reset users. Rollback requires stopped writers and matching verified pre-upgrade source/settings/backup; validate rollback in an isolated destination before reuse. Native Windows deployment acceptance remains to be performed by the operator.
