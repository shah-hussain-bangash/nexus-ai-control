# UI completion and resumable review — 0.15.0

18 November 2026. This release closes practical gaps in the 18-area/216-function UI baseline. It delivers a connected review interface for the agreed scope. It does not certify every device/state or turn planned backend services into production services.

## Start and review

Run scripts\start.cmd from the project root, retain the terminal and use its printed URL. Sign in with existing credentials and open Product UI walkthrough. Start from a workspace, direct function link or connected journey. Existing six detail views, eight state previews, role-specific example decisions, inbox, event timeline, coverage/search and phase plan remain available. See the prior UI_FIRST_GUIDE_0_14_0.md for the original navigation walkthrough; the resume and retention rules in this current guide replace its older session-only/no-import limitation.

Use synthetic data and secret references only. Walkthrough actions remain UI-only and invoke no planned service route or customer command. The separate implemented-workspace links still reach working authenticated services. Source/reference data stays subject to its own real backend controls.

## Export and resume

1. Choose whether Include synthetic examples in export is enabled. Full export includes your example configurations/events, manual checklist criteria and review markers. Metadata-only export retains criteria/markers without examples.
2. Select Export UI handoff. Keep the downloaded JSON privately. It includes organization/user identifiers for scope checks; it is not a credential and grants no access. The download-start notice does not prove that the browser completed a file save: verify the downloaded file before leaving.
3. A full export clears the local unexported-change indicator. A metadata-only export keeps the warning if examples remain, so excluded examples are not silently treated as retained.
4. After a reload or later visit, sign in to the same account/workspace, select Import UI handoff and choose your JSON. File parsing is local; no handoff bytes are uploaded to the server.
5. Inspect the replacement summary. Import never merges silently. Confirm that you want the imported examples/checklists to replace the current local UI session. Export the current session first if you need to preserve it.
6. Restore UI review. The examples and review markers reappear without changing actual server records, user roles, environments or production readiness gates.

No automatic browser persistence was added; your own file is the resume mechanism. The Enterprise design studio continues to provide its separate server-persisted versioned design plans.

New handoffs use format nexus-ui-review, schema 1 and release 0.15.0. They are restricted to the exporting account and organization. Imported catalog definitions are never trusted as executable field schemas: the current authenticated catalog supplies allowed functions/types/validation. The import checks the complete known catalog, unique module/function/example identities, field keys/types/bounds, statuses, integer revisions, event bounds and manual review criteria. Unsafe JSON object keys and requests to claim backend activation/production acceptance are rejected. No HTML, scripts, endpoints or file paths from a handoff are executed.

An imported JSON file is not signed evidence. Configurations, UI events and checklist claims remain user-authored design metadata, not an authoritative audit trail or proof of real independent approvals.

## Legacy 0.14 handoffs

The importer accepts 0.14.0 exports for migration of valid examples. Those older files have no scope binding or four-part review checklist. The replacement dialog highlights that limitation and asks you to confirm the examples are yours. Legacy review markers are cleared and must be re-reviewed with the current checklist. Missing/unknown/duplicate catalog entries or invalid current fields fail validation. No legacy file is imported automatically.

## Review checklist

Each function now requires four explicit manual checks before Mark this function UI reviewed becomes enabled:

- Configuration, confirmation, result and evidence journey.
- Intended roles and denied-access behavior.
- Validation, dependency, timeout and stale-revision recovery.
- Service handoff and implementation boundaries.

Unchecking a criterion clears that function's review marker. Imports cannot set reviewed markers without all criteria. These are your UI attestations, not automatic tests or production acceptance. No functions are accepted by default in source or generated inventories.

## Prevent lost work

Saving or changing an example, adding an event, or editing a review checklist marks the local UI session as having unexported changes. Leaving the main workspace or signing out offers Stay and export handoff, Keep reviewing, or Leave without exporting. Unsaved configuration has its separate discard confirmation; if saved session work would also be lost, the export warning follows. Browser close/reload requests a native leave warning when work is unexported. Browsers control how that warning is displayed.

A rendering failure in the walkthrough shows a recovery panel instead of a blank application. Retry remounts the local UI session; a previously exported handoff can restore it. Return to command center exits the failing route. This fallback does not restore an unexported session or certify protection against every crash/device failure. Runtime APIs are not automatically retried by this UI recovery.

## Limits and accessibility

| UI control | Bound |
|---|---|
| Imported handoff | JSON, 1 byte–8 MiB |
| Examples per UI session | 300; enough for one example per agreed function |
| Events per example | 50 |
| Example name / owner | 1–120 characters |
| Field values | Current catalog type/options/bounds; at most 2,000 characters |
| Event review note | 5–500 characters |
| Review criteria | Four known criteria per function |

Oversized full exports are rejected with guidance to export review-only metadata or fewer examples; no silent truncation occurs. Keep separate handoff files for large or long-running design exercises. The event cap prevents endlessly extending an individual rehearsal; export it and create a new example.

Inputs now expose their visible label, invalid state and associated field guidance to assistive technology. Invalid fields have a visible border/text treatment. Table headers use column scope. Existing readable light/dark layouts, larger text, focus outlines, native dialogs and responsive rules remain. Formal WCAG/screen-reader/native Windows/mobile device acceptance and full Arabic translation/RTL remain outstanding; a localization design screen is not a working translation engine.

## Verification

50 frontend tests passed, including handoff round-trip, account/organization isolation, catalog drift/duplicate rejection, unsafe JSON, field/secret-reference checks, review-gate integrity, legacy migration, metadata-only export and a single handoff with one example for all 216 functions. Existing UI model tests remain green. Backend regression remains 268 passed, 15 external-service skips. Both builds passed.

Browser QA used the isolated synthetic harness. It verified a saved example's leave warning, full export, a fresh session's import/replacement confirmation and restored example, checklist disabled after zero/one criterion and enabled after four, and resumed handoff export. A 1363px desktop viewport had no document-level horizontal overflow. No live customer/IdP/cloud action occurred. Error-boundary recovery was compiled/reviewed but not browser fault-injected; all 216 × 8 states were not manually accepted.

## Implement next

Use the retained five-phase plan and current implementation report. Identity/environment lifecycle, broader connectors/agent execution, semantic retrieval/source synchronization, operational integrations and deployment acceptance require their own implementation evidence. UI completeness against the agreed inventory remains separate from service readiness.
