# Dedicated enterprise UI coverage — 0.8.0

All 18 defined roadmap modules have eight sections and a dedicated operational UI. There are 161 configuration fields, 97 operational fields, 54 planned runtime contracts and 126 UI state-transition commands. These counts describe separate layers; they must not be summed as implemented runtime services.

| # | Module | Dedicated operational experience | Form fields | UI commands |
|---|---|---|---:|---|
| 1 | Connector & MCP hub | Connection schema & authorization | 5 | Request review; Record UI approval; Activate in preview; Disable in preview; Return for rework |
| 2 | Agent runtime & orchestration | Run graph & checkpoint timeline | 4 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 3 | Document ingestion & OCR | Ingestion queue & extraction review | 5 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 4 | Semantic search & reranking | Search, citations & relevance feedback | 5 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 5 | Knowledge access & data controls | Principal-resource permission matrix | 5 | Request review; Record UI approval; Activate in preview; Disable in preview; Return for rework |
| 6 | AI quality & evaluation lab | Dataset, rubric & comparison | 8 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 7 | Model routing & resilience | Primary, fallback & failure handling | 5 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 8 | Capacity & traffic policy | Admission, concurrency & backpressure | 4 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 9 | AI FinOps & usage reconciliation | Cost planning and invoice variance | 5 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 10 | Identity, SSO & workload federation | Members, role scope & SSO review | 5 | Request review; Record UI approval; Activate in preview; Disable in preview; Return for rework |
| 11 | Organizations, workspaces & environments | Membership and environment boundaries | 4 | Request review; Record UI approval; Activate in preview; Disable in preview; Return for rework |
| 12 | Secrets, egress & isolation | Reference inventory and rotation drill | 5 | Request review; Record UI approval; Activate in preview; Disable in preview; Return for rework |
| 13 | Observability, alerts & service objectives | Alert queue, service signals & response | 5 | Triage alert; Acknowledge; Resolve in preview; Reopen case |
| 14 | Audit archive & evidence integrity | Event chain and retention review | 5 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 15 | Backup, restore & continuity | Recovery points and restore verification | 5 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 16 | Cloud delivery, environments & rollback | Release pipeline and rollback review | 5 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview; Rehearse rollback |
| 17 | Security, performance & resilience testing | Test matrix and finding triage | 8 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |
| 18 | Accessibility, UX & device acceptance | Device, keyboard & screen-reader checklist | 9 | Queue preview; Start preview; Pause; Resume; Complete preview; Record synthetic failure; Cancel preview; Retry preview |

All modules: list/detail/edit/duplicate/remove, search/filter/page, owned records, command confirmation, required notes, event history, review export, manual UI-state previews and parent-plan revision persistence. Domain-specific components are rendered by OperationalConsole.tsx from the versioned operations catalog. Blueprint/runtime contracts are separately retained.

Known acceptance limits: desktop browser review does not establish mobile/screen-reader conformity. Runtime adapters, real-data timing and deployment acceptance follow PRODUCTION_ROADMAP.md. Complete scope means these 18 defined modules, not every possible future enterprise feature.
