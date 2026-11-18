# Runtime progress — 0.10.0

Agent execution and Document library now have real bounded backend paths. Use RUNTIME_QUICKSTART_0_10_0.md to validate those paths before extending the retained design plan below. Linked working features state their current limitations; broader designs remain planned.

# Long-term UI-first development sequence — 0.9.0

1. Open Platform function map and review all 216 function definitions by module.
2. Assign feature owners and configure the domain controls for the intended environment.
3. Review all eight screen states and the permission/recovery journey.
4. Record four manual UI checks, add implementation notes and Save revision.
5. Export the function/module scope as the backend work package.
6. Implement each service with real authorization, isolation, validation, idempotency, audit and outcome handling.
7. Replace the relevant rehearsal with real request/result wiring only after sandbox tests pass.
8. Collect deployment-specific evidence in Release readiness before production activation.

The retained sequence below provides the dependency order. Function dependencies in the catalog show control relationships; they can be cyclic and are not an execution DAG.

---

# Step-by-step activation after UI review

## Review the UI first

1. Start the real local app and open Enterprise design studio as the owner.
2. Load interface examples. Choose one of the 18 modules.
3. Review its six-stage journey and three action dialogs.
4. Configure the three-step wizard. Open Operational console, add domain records and rehearse valid actions. Record blueprint remains available for generic future list/detail metadata.
5. Save the revision, check its schema and run happy-path and failure previews.
6. Review the planned API contracts; export the plan and contract for implementation.
7. Record the four manual UI checks and advance the planning phase. This does not approve production operation.

## Implement in dependency order

| Stage | Modules | Concrete exit evidence |
|---|---|---|
| 1. Foundation | Identity, workspaces, secrets/network | Tenant/role isolation tests, lifecycle audit, reviewed secret references and egress controls |
| 2. Governed integration | Connector/MCP hub, durable agent runtime | Sandbox adapter contract tests; idempotency, approval boundaries, durable resume/cancel and unknown outcomes |
| 3. Enterprise knowledge | Ingestion/OCR, semantic retrieval, document permissions, answer evaluation | Real document pipeline; access-filter tests, citation/quality evaluation, deletion and index consistency |
| 4. Runtime assurance | Model resilience, traffic, FinOps | Provider sandbox evidence, bounded retries, load/admission tests, measured cost and reconciliation |
| 5. Operations | Telemetry, audit archive, recovery, cloud delivery | Alert drill, archive integrity, restore drill, staging rollout and rollback |
| 6. Acceptance | Security/performance and accessibility/device review | Independent findings resolved; keyboard/screen-reader/device checks; representative load and failure results |

For every planned command: implement its reviewed API and server-side authorization; connect a real adapter behind an explicit environment control; add request/response validation, idempotency and audit; wire UI loading/success/error states to the actual result; test cross-tenant/role denial and stale revisions; run staging dependency and outage tests; document and resolve uncertain outcomes; attach actual evidence to Release readiness. Never convert a preview result into runtime acceptance evidence.

## Release gate

Run the existing tests and all applicable external integration suites. Test backups and rollback before enabling a capability in production. Use PRODUCTION_ACCEPTANCE.md for evidence, accountable owner and environment scope. UI checkboxes alone cannot satisfy these gates. Keep unimplemented runtime actions visibly planned until these steps are complete.
