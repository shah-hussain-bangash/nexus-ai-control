# NEXUS implementation and remaining phases

Release 0.1.0 | 13 November 2026 | Delivery: runnable local synthetic MVP + source code

## Main conclusion

The source implements the central governed-action workflow end to end and a professional sign-in/portal. It does **not** complete every enterprise feature in the planning documents. Use this report as the current implementation status; PDFs in `docs/reference` are the design baseline, not proof that a capability is finished.

The current backend acceptance run passed **55 tests**, including three real OPA HTTP integration cases. **Five additional Rego policy tests passed** with OPA 1.0.1. React/TypeScript production build and Python compilation passed. `test-results.xml` contains the backend result record. Optional OPA cases explicitly skip when `OPA_BIN` is absent.

## Phase-by-phase status

| Gate | Status | Implemented evidence | Remaining before enterprise acceptance |
|---|---|---|---|
| G0 Product/design | Baseline supplied; scope implemented narrowly | Original requirements, security/API/UI/architecture reference PDFs included | Resolve real customer region, data, retention, recovery and pilot decisions |
| G1 Foundation/identity | Local core implemented and tested | React + FastAPI, version-1 schema, local sessions, CSRF, role checks, signed workload token, tenant-scoped reads | Live OIDC/Keycloak/MFA verification; multi-membership/environment switching; advanced assigned-object permissions; migration upgrade strategy |
| G2 Enforcement | Local workflow and OPA integration tested | Typed fixed tools, explicit grants, immutable envelope, threshold rules, denial before mock invocation, real OPA HTTP checks | General tool registration, custom resource constraints, real connectors, managed secret retrieval and verified network bypass isolation |
| G3 Independent review | Local core implemented and tested | Payload/version binding, expiry, self-review denial, compare-and-set, parallel-decision test | Customer role provisioning, SSO step-up, multi-stage delegation and production concurrency/load review |
| G4 Execution/evidence | Synthetic workflow implemented and tested | Persisted action outbox, separate worker, revocation recheck, mock idempotency, verification and unknown-outcome lookup | Vendor-specific retry/timeout/lease semantics, remote connector credentials and real outcome verification |
| G5 Operations | Basic portal implemented; integrations partial | Live counts, audit timeline, expiring owner-scoped JSON export, runtime policy evaluation, containment, local backup utility, Compose/CI source | PostgreSQL/Compose execution, cloud deployment, OpenTelemetry/Langfuse, restore drill, actual billing, budget reservations, retention automation, distributed limits and security review |
| G6 Customer pilot | Not started | Pilot restrictions and next steps documented | Authorized customer workflow, data agreement, deployment review, measured acceptance and operational ownership |

## Requirement coverage

| Requirement | Current implementation | Status |
|---|---|---|
| P0-001 Human identity | Local hashed-password session and CSRF verified. OIDC code and a Keycloak realm fixture supplied. Local MFA is not implemented. | Partial |
| P0-002 Registry | Register Draft; inspect identity; grant; activate/suspend/rotate/contain. Retirement and a guided setup wizard not included. | Local core verified |
| P0-003 Workload identity | Per-agent credential exchange, 5-minute signed token, issuer/audience/tenant/env/expiry checks and generation revocation. Shared server signing secret is a local design, not enterprise workload federation. | Local core verified |
| P0-004 Tool schema | Two versioned, typed fixed mock tools. Unknown arguments/actions/resource types rejected. No arbitrary external tool registration. | Partial |
| P0-005 Grants | Explicit action scopes and tenant/environment constraints; missing grant denied. Custom per-resource ABAC remains. | Local core verified; granular expansion remains |
| P0-006 Policy | Reference engine + real OPA adapter; versioned limits; activation runs boundary checks; outages fail closed. Not a general policy authoring studio. | Verified supported rules |
| P0-007 Execution boundary | Mock invocation is private Python worker code with no public connector execution route. No managed secret service or deployed egress-isolation proof. | Partial |
| P0-008 Approval binding | Canonical full SHA-256, policy version, expiry and immutable envelope. | Verified locally |
| P0-009 Independent decision | Requester cannot review own action; role check; atomic version compare; concurrent test has one winner. | Verified locally |
| P0-010 Dispatch checks | Current lifecycle/generation, grant, policy, hash and approval checked. PostgreSQL row-lock semantics included but not tested on a live PostgreSQL server. | Verified SQLite path; PostgreSQL pending |
| P0-011 Idempotency | Stable logical intent and mock business key. Sequential duplicates return original action; concurrent conflicts require retry with the same key. | Verified local supported cases |
| P0-012 Outcome verification | Expected supplier, amount, currency and external reference matched; discrepancy never Verified. | Verified mock connector |
| P0-013 Unknown outcomes | Commit-then-timeout -> Unknown; lookup resolves original without duplicate. Expired worker lease never blindly replays. | Verified mock connector |
| P0-014 Audit | Durable correlated SQL events, UI timeline and expiring owner-scoped JSON export. Not WORM/certified immutable storage; CSV/PDF exports not included. | Local core verified |

## Portal status

Implemented: local sign-in, workspace overview, agent registry/detail, fixed tool catalogue and schema viewer, structured policy limits/version history, approval inbox/detail, action ledger/evidence, audit browsing/export, runtime evaluation results, containment incidents and settings/member view.

The usage screen intentionally states that billing is not connected; it displays no fabricated spend. Member invitation/editing is not implemented in the portal; a CLI can provision local users. General tool onboarding, a full setup wizard, notification delivery, advanced reports and retirement remain expansion work. Navigation uses browser hash routes; direct API resources are separate from UI routes.

Responsive CSS is included. Desktop sign-in/dashboard/approval dialog were visually reviewed; draft registration and actual evaluation submission were exercised in the browser. The QA session used an isolated synthetic fixture outside the shipped source. No browser authentication bypass or QA credential is packaged. A comprehensive mobile-device and assistive-technology audit remains open. Some controls have compact visual targets; no WCAG certification is claimed.

## Verification record

- Backend: 55 passed; 0 failed in the recorded run. This includes tenant/role/CSRF/session checks, policy thresholds, missing grants, payload substitution, expiry, independent/parallel approval, idempotency, revoked grants/suspension, lease recovery, timeout reconciliation, result mismatch, workload token claims/signature, scoped polling, export expiry, containment, OIDC invalid callback and policy activation outage.
- Real OPA integration: three of those 55 cases use a live OPA HTTP server (allow / approval / deny).
- OPA Rego: 5/5 additional native policy tests passed.
- Frontend: TypeScript compile and Vite production bundle passed.
- Python: source compilation passed.
- Clean ZIP extraction: fresh initialization, generated-password sign-in, built portal serving, independent approval, worker verification and auditor export passed using the extracted source.
- Browser: sign-in and portal layout; persisted draft registration; self-review controls disabled; actual 5/5 runtime boundary evaluation. Do not confuse that five-case UI result with the full security suite.
- External services not verified: PostgreSQL server/Compose topology, live Keycloak MFA, AWS, managed secrets, external telemetry and real business APIs.
- Test runner emitted two dependency deprecation warnings (AnyIO/pytest and Starlette/httpx); no application test failure. Update the dependency matrix deliberately before upgrading frameworks.

## Remaining phases in recommended order

### R1 - Identity and database integration

Run PostgreSQL migrations and the security/concurrency suite on PostgreSQL. Start the supplied Keycloak fixture and verify OIDC issuer/JWKS, PKCE/state/nonce, email mapping, MFA, session expiry and recovery. Implement real multi-workspace/environment memberships and assigned-object permissions. Replace local signing-key management with the selected workload identity design. Add an upgrade migration workflow.

Exit evidence: real identity-provider journeys and PostgreSQL concurrency/isolation results, with no critical failures.

### R2 - Real connector and secret boundary

Implement one approved business API with managed secret references and endpoint/egress controls. Specify business idempotency, bounded timeouts, worker lease/heartbeat and authoritative reconciliation. Run direct-bypass, SSRF, payload visibility and secret-redaction tests. Keep critical actions out of scope.

Exit evidence: allow/deny/approval/timeout paths against a permitted customer test system; credentials unavailable to agent and browser.

### R3 - Operational assurance

Integrate redacted OpenTelemetry/Langfuse, real alerting, provider usage/billing, atomic spend reservations and retention/deletion jobs. Generalize exports and pagination. Add payload-view permissions and policy rollout review. Restrict database audit mutation permissions. Exercise backup/restore with external reconciliation and measure actual RPO/RTO.

Exit evidence: monitored correlated actions, accurate usage labels, no leaked secrets, restored environment with safe dispatch.

### R4 - Cloud and customer pilot

Implement reviewed Terraform for the selected cloud/region, private data tiers, TLS, managed secrets, image/security scanning, deployment/rollback and support ownership. Conduct an independent security review and representative load/accessibility testing. Agree customer data scope, retention, pilot acceptance and exit/deletion procedures.

Exit evidence: a restricted authorized pilot with measured outcomes, known limitations and a signed-off operational owner. No claim of enterprise production readiness before those gates.

## Security and operational boundaries

This release is for synthetic local use. Local login and a reference policy mode are disabled/forbidden by pilot configuration guards, but configuration checks alone are not a production security review. There is no public signup, committed shared password, real payment connector or automatic destructive replay. Do not expose the local service publicly.

Raw synthetic action arguments are retained in SQL for review; real-data payload minimization, encryption/access policies and redaction need customer design. Tenant-scoped read access is broader than the future assigned-object model. Rate limits are process-local, and the request-size header guard is not a complete reverse-proxy/body-stream limit. Audit events use append-only application behaviour; database administrator privileges can alter them.

The mock store is a separate SQLite database, even when the control plane is configured for PostgreSQL. External calls are outside the control database transaction. A committed dispatch authorization is the revocation cutoff; later suspension cannot undo an external effect. The worker conservatively treats an expired executing lease as unknown and needs connector-specific timing/heartbeat design for longer calls.

## How to start

Use `scripts/start.ps1` on Windows or `bash scripts/start.sh` on macOS/Linux. Read README.md for manual steps and the two-terminal API/worker setup. On first initialization, the terminal prints random development credentials for owner, reviewer and auditor accounts. The ZIP contains no preinitialized database or `.env`; your local initialization creates new credentials.

The archive includes complete implemented source, dependency lockfile, built portal, OpenAPI JSON, initial PostgreSQL DDL, SDK examples, CI/Compose source, test evidence and the original design PDFs. Dependencies must be installed; virtual environments, node_modules and runtime secrets are excluded.
