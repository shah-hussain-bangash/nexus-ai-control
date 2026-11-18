# Long-term production-platform UI design — 0.9.0

This release adds the remaining enterprise capabilities to a searchable, configurable UI scope. It is a long-term design and implementation workspace. Planned services remain inactive until their real backend and deployment evidence are completed.

## Delivered interface scope

- New Platform function map in main navigation: 18 modules, 216 detailed function screen definitions and 648 function-specific input controls (two domain controls plus implementation environment per function).
- Search across function names, modules and control labels; area/module/priority/planning-phase filters; pagination; open a specific screen; export the full scope.
- New Function catalog section in each module, bringing the studio to nine sections per module (162 module sections) and the portal to 22 primary views.
- Each function has four design views: Screen & states; Journey & roles; API & data; UI review. Each definition includes intended personas, capability dependencies, six journey checkpoints, three UI review actions, eight screen states, a planned API contract, conceptual data/evidence objects and four manual review checks.
- Function owner, phase, field values, notes and checks are saved with the existing parent blueprint revision. Up to twelve distinct function plans per module are validated server-side. No new database migration is required; schema stays 5. References accept env:/secret:// patterns, URLs require credential-free HTTPS and numeric values are bounded.
- Existing 18 dedicated operational rehearsals, 97 operational fields, 126 state-transition commands, 161 module configuration fields, 54 legacy module action contracts, sign-in and working control-plane functions are retained. These are separate layers and their counts must not be combined as implemented backend services.
- Function forms use shared typed rendering with domain-specific definitions. These are configurable design screens, not 216 independently implemented runtime applications. UI actions produce browser-local review traces with zero live effects. Trace exports are available; input/review plans persist through Save revision in the real app.

## Remaining capabilities represented in the UI

Connector REST/MCP/OAuth/webhooks/scopes/idempotency; durable agent identity/graphs/delegation/memory/triggers/approvals/escalation/checkpoints/replay/cancellation/dead letters; source sync/OCR/layout/chunking/metadata/lineage/deletion/quarantine; embeddings/vector indexes/hybrid retrieval/reranking/citations/cache/context; ACL/RBAC/ABAC/tenant filters/PII/DLP/retention/legal holds/data-subject requests/consent/residency; evaluation datasets/graders/comparisons/drift/feedback/red teams/poisoning/language/regression gates; model streaming/batch/multimodal/version/fallback/token controls; rate/concurrency/priority/abuse boundaries; budgets/reservations/invoice reconciliation/chargeback/forecasting; OIDC/SAML/SCIM/MFA/passkeys/sessions/service accounts/API credentials/delegation/offboarding; organization/workspace/project/environment lifecycle; vault/key rotation/TLS/private endpoints/egress/SSRF/log redaction; traces/logs/metrics/SLOs/on-call/incidents/runbooks/notifications; archive/integrity/control mapping/evidence/custodianship; backup/restore/failover/RPO/RTO; build/SBOM/scans/canary/rollback/migrations/feature flags; security/load/soak/chaos/exceptions/retests; responsive design/contrast/keyboard/screen readers/RTL/date and currency/help/UX findings.

The complete named inventory is in LONG_TERM_UI_MASTER_SPEC.md and PLATFORM_FUNCTION_INVENTORY.csv. backend/nexus/interface_catalog.json is the machine-readable definition used by the UI. Dependencies describe control relationships, not a strict deployment DAG.

## Review behaviour and boundaries

The Screen state selector reviews empty, loading, ready, permission denied, validation error, dependency unavailable, uncertain timeout and stale revision feedback. Three confirmation-based actions generate a six-checkpoint UI trace; no planned API endpoint is called. UI review status is manual planning metadata and never updates production readiness gates.

The map reports the latest non-archived plan per module. Review a specific saved plan in the studio when multiple plans exist. Definitions are available immediately; configurations become persistent after Save revision. The separate demo harness stores edits in memory and resets on reload. It has no real authentication, credentials, uploads or service access.

Formal Arabic localization/RTL, actual SCIM or SAML, live restore/failover, independent accessibility, runtime streaming and every other listed future service are designed here rather than implemented by these screens. Existing bounded provider capabilities and source-state limitations remain described in earlier runtime reports. No account, access grant, business purchase, provider call or cloud deployment is performed by function review actions.

## Verification

210 backend tests passed; 15 external-service integration tests skipped. All 26 frontend tests passed. Tests cover all 216 default screen definitions, 648 controls and all 5,184 function/action/state preview combinations, real persisted function-plan revisions across the 18 modules, review gating, cross-module rejection, secret-reference syntax and invalid numeric input. These are automated design/logic/API tests, not 5,184 browser clicks.

Browser checks covered inventory/search/filter navigation, opening selected connector/durable/OCR/vector/SCIM designs, changing a function field, assigning an owner, reviewing all four checks, saving revision 2, showing the reviewed plan in the map, timeout trace with zero effects, API contract/dependency display, linked form help and full-scope JSON export. Desktop width was 1363px without document-level horizontal overflow. Builds and final verification details are in VERIFICATION.json.

Windows/device/browser-matrix, screen-reader, live infrastructure, penetration/load/restore and production acceptance remain separate work. The production roadmap is unchanged (6 missing, 11 partial, 1 source-implemented awaiting acceptance). This release completes the expanded defined design inventory; it cannot guarantee every future requirement for every enterprise.
