# Operational UI implementation report — 0.8.0

This release extends the complete 18-module interface catalog with dedicated operational user experiences, not just blueprint tables. It remains a UI-first implementation. UI rehearsal transitions cannot execute cloud, identity, document processing, model, network or business operations.

## Delivered

- Eighteen domain-specific operational views in the Enterprise design studio, each with its own fields, visual review surface and state machine.
- 97 additional operational form fields and 126 valid UI-transition commands, separate from the retained 161 configuration fields and 54 planned runtime API contracts.
- Eight sections per module: Overview, Configuration, Operational console, Record blueprint, Workflow preview, API handoff, Acceptance and History (144 module sections; 21 main navigation views).
- Records support add/edit/inspect/duplicate/remove, search, state filter, pagination, examples, JSON export and responsible owner. Limits: 50 operational records and 100 review events per interface plan. Removal affects the draft; previous saved revisions are retained.
- Domain-specific record data and event histories persist with the parent blueprint revision in the real application. Typed server validation checks exact fields, bounded values, command/state consistency, failure-state preservation, event references, timestamp timezone and secret-reference syntax. No new database tables or schema migration are required; schema remains 5.
- Queue/start/pause/resume/complete/fail/cancel/retry flows; review/approve/activate/disable/rework design flows; alert triage/acknowledge/resolve/reopen; deployment rollback rehearsal. These are explicitly synthetic UI operations.
- Loading/unavailable/permission/empty screen-state reviews with retry or return actions, visible error feedback, command confirmation and mandatory review notes. Failure scenarios retain the prior state with no automatic retry.
- Global studio dirty-plan protection for dashboard hash navigation and sign-out, in addition to internal module/plan switching and browser unload. Keep-editing and discard-and-switch are explicit choices. This guard covers unsaved parent studio drafts and unapplied operational record edits. Closing an edited operational form also asks whether to keep or discard its edits. Legacy form coverage remains separate.
- Native modal dialogs, labelled fields, focus return, keyboard-operable tabs, wrapping controls, responsive record/detail layouts and brighter 15px operational record titles in larger-text mode. A measured 1363px desktop viewport had no document-level horizontal overflow. Formal mobile/screen-reader acceptance remains open.

## Specialized experiences

See UI_COVERAGE_MATRIX.md for every module. Connector schema editing; supervised run graph/timeline; document intake file chooser/drop target; retrieval query/citation detail; principal/resource access matrix; evaluation rubric; primary/fallback routing; capacity estimator; cost variance; identity lifecycle; environment cards; secret references/egress review; synthetic signal chart/alert handling; SHA-256 UI payload digest; recovery target review; canary/rollback planning; security/load and device/accessibility finding checklists.

File intake only validates extension/size and stores filename/size metadata: up to 20 MiB, TXT/PDF/DOCX/CSV/MD. File bytes are not read, uploaded, OCRed or indexed. Citation search is browser-local keyword matching over synthetic excerpts, not semantic retrieval. Rubric/test outcomes are manually entered reviews, not measured benchmarks. Signal charts are labelled illustrative. Capacity/cost numbers are calculations from entered values, not live telemetry or bills. A payload digest does not provide immutable audit storage. Recovery RPO/RTO values are targets, not measured outcomes. UI account/deployment actions grant no access and perform no rollout.

## Verification and remaining acceptance

The current test run passed 189 backend tests and 21 frontend tests. Fifteen external integration tests were skipped (6 PostgreSQL, 6 Keycloak, 3 OPA). Both builds passed; the synthetic preview bundle still reports a size advisory.

Cloud-browser checks exercised every module's populated operational surface; revision saves; queue/start and uncertain-pause event history; global navigation keep/discard; intake file chooser metadata; keyword citation results; unavailable/retry state; larger-text colour/size and desktop overflow. Backend tests persist operational fields/events across all 18 modules and reject forged transitions, raw reference credentials and malformed schemas. Frontend tests cover transition graphs, rollback, failure preservation, estimates, file limits, calendar dates and navigation guard lifecycle.

No real provider was contacted; no cloud deployment or Windows installation was modified. Independent mobile/device, screen-reader, security, load, restore and deployment acceptance are not completed by this release. The runtime roadmap is unchanged: 6 missing, 11 partial and 1 source-implemented item awaiting production acceptance. Do not describe this as a certified complete production runtime. The backend implementation sequence remains in UI_IMPLEMENTATION_SEQUENCE.md.
