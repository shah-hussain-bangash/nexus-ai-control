# Release 0.4.0 — AI engineering workspace

17 November 2026. The portal now has 20 views grouped by building, governance and operations. Nine new versioned design asset kinds support create, edit, duplicate, archive, configuration validation, revision history and JSON export. Eighteen opt-in starter designs connect the UI to a persistent local workbench.

Added real local execution for bounded workflow previews, prompt rendering/assertions, bilingual BM25 retrieval with versioned SHA-256 citations, guardrail checks/redaction, retrieval benchmarks, cost calculations and saved run evidence. Workflow references are pinned to asset versions and fail closed if stale. External tool effects remain in the original governed dispatcher.

Schema 3 adds WorkspaceAsset, AssetRevision and WorkbenchRun. Optimistic version checks reject stale edits; existing organization/environment scopes, roles and CSRF protect the endpoints. Starter loading is local-mode only. Provider and connector endpoints are validated but never contacted. Only environment-variable references may be saved in their credential fields.

Validation: 106 backend tests passed; 15 external integration tests skipped; five frontend regression tests passed; TypeScript/Vite builds passed for the full application and separate read-only preview. Desktop visual inspection covered dashboard, workflow canvas, configuration editor/history and stored run evidence. Mobile-device testing and a formal accessibility audit remain outstanding.

Read IMPLEMENTATION_REPORT.md for production gaps and UPGRADE_0_4_0.md before installing over existing data.
