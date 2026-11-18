# Complete navigable UI baseline — 0.14.0

18 November 2026. This release completes a connected UI baseline for the agreed **18 areas and 216 functions**. It does not define every possible future business requirement or certify all screens/devices. Backend implementation and production acceptance remain separate.

## Start and find the new workspace

Keep existing sign-in credentials and private configuration. Read UPGRADE_0_14_0.md, then start Windows from the project root with `scripts\start.cmd`. Open the newly printed URL, sign in and select **Product UI walkthrough** in the sidebar. Existing implemented workspaces, function map and detailed design studio remain available.

The walkthrough is the UI review layer. It reads the authenticated screen catalog; its example transitions do not send backend commands, notifications, requests to planned service routes or customer operations. Preview persona/environment selectors change the rehearsal only. Server permissions, actual workspace membership, MFA and deployment settings are unchanged.

## Review the UI end to end

1. Start from Workspace or End-to-end journeys. Quick links cover organization setup, access/sessions, environments, notification preferences, help/ownership and branding/language. All 18 enterprise area cards open their 12 function screens.
2. Select a function. The six views are Overview, Configuration, Review, Activity, Access and API handoff. Create a synthetic example as the Operator preview persona. Domain fields use catalog types, options and bounds; secret fields accept references only.
3. Save the example in this mounted UI session. Review its scoped values and pinned revision, then submit it with both scope/effect confirmations and a note.
4. Open Review inbox, select the request, switch to Reviewer, and approve, reject or return for rework. Inspect the activity timeline and resulting state. Auditor inspects without mutations. These are designed persona behaviors, not substitutes for server authorization or independent real-person approvals.
5. Rehearse all eight states: ready, empty, loading, permission denied, validation error, dependency unavailable, timeout unknown and stale revision. Restricted state hides example detail; validation recovery exposes the field to correct. Uncertain outcomes offer reconciliation rather than blind resubmission. Shared model tests exercise denial, versioning and unknown-outcome behavior.
6. Inspect Access and API handoff. Planned routes are metadata and are not registered merely because the UI shows them. Where a bounded runtime path exists, Open implemented workspace takes you to it explicitly.
7. Mark a function's UI reviewed only after human review. UI coverage shows all 216 screens, their areas/phases and review status. This manual marker does not change backend readiness or acceptance gates.
8. Export UI handoff before leaving. It contains the catalog, phases, connected journeys, checked UI reviews and local examples. No secret values or source files belong in this export. Treat any manually entered notes as your data.

Examples and review checkmarks exist only while this Product UI walkthrough component is mounted. Navigation inside it retains them; leaving for another main workspace or reloading discards them. Unsaved configuration has a discard dialog/navigation guard. Export is the retention mechanism for this walkthrough; there is no import/restore of the exported rehearsal in this release. Use the existing Enterprise design studio for persisted versioned design plans. The UI session is bounded to 200 example records. No examples or acceptance checks are pre-created as passed.

## Six connected journeys

| Journey | Five connected steps |
|---|---|
| Enterprise onboarding | Organization → IdP design → member invitation → environment → access certification |
| Governed agent | Tool mapping → agent capability → human checkpoint → workflow graph → correlated audit |
| Reviewed knowledge | Document intake → OCR review → document roles → hybrid retrieval design → evaluation gate |
| Incident recovery | Alert rule → incident timeline → runbook → isolated restore → evidence chain |
| Release review | Artifact → image scan gate → deployment approval → canary → rollback |
| AI spend | Budget → admission precheck → provider usage → invoice reconciliation → billing evidence |

Next/Previous controls preserve the journey context while opening the next function. Each target resolves to an existing catalog function. A direct feature URL uses `?ui_feature=FUNCTION_ID#product`; it restores the function selection, not previous local examples.

## Coverage and visual standards

UI_BASELINE_0_14_0.json and UI_SCREEN_COVERAGE_0_14_0.csv enumerate every function. All 216 use the same shared list/detail, form, confirmation, state and evidence patterns with their own titles, fields, roles, steps, entities and planned routes. They are reusable screen templates, not 216 bespoke product editors or live services. Additional domain-specific charts, graph/canvas editors, translated content and actual integration behavior can be refined during the relevant implementation phase.

The new workspace uses readable dark text on light surfaces, a dark navy/cyan feature hero, a dark appearance option, visible focus outlines, labels/hints, native confirmation dialogs and responsive layout rules. Forms use 46px minimum controls. New body text is 16px by default; supporting labels are at least 14px in the new stylesheet. Large-text mode is retained. Wide coverage tables scroll inside their own container; small-screen layouts stack the workspace and function panes. Responsive rules are implemented; the full native device/browser matrix, Arabic translation/RTL and formal WCAG/screen-reader acceptance still need review. The localization function screen is not an implemented translation engine.

Browser review sampled overview, the complete 216-row coverage table/search, connected journey navigation, configuration validation, draft discard, Operator submission → inbox → Reviewer approval → evidence, denied-access display, export, phase board and light/dark contrast. A 1363px desktop viewport had no document-level horizontal overflow. Do not interpret these samples as manual acceptance of all 216 × 8 states or every device.

## After UI review

Use IMPLEMENTATION_PHASES_0_14_0.md. Each phase needs working services, identity/integration configuration, negative and recovery tests, staging evidence and agreed deployment acceptance. The new UI does not expand the existing source implementation claims. Schema remains 8 and existing accounts/data are preserved.
