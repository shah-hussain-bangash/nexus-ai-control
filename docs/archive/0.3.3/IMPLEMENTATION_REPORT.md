# NEXUS implementation and remaining phases

Release 0.3.0 | 13 November 2026 | Enterprise Agentic AI Governance, Security & Operations Platform (NEXUS AI Control)

## Delivered in this release

The full application source now includes a redesigned sign-in screen, an original SVG governance illustration, a refined portal, searchable audit pagination, owner-controlled member revocation, an operations readiness view and expired-record cleanup. The earlier PostgreSQL, OPA and Keycloak integration is retained. This is a tested integration prototype; it is not the finished enterprise production platform.

The hosted Site is a private, read-only design preview using synthetic snapshots and simulated sign-in. It is separate from the server-backed application. Both source variants are included so the preview cannot be mistaken for the enterprise authentication implementation.

## UI and UX improvements

- Sign-in shows the requested full project title, an original governance shield illustration, and a clearer enterprise workspace description.
- Navy, indigo and teal styling connects the sign-in and portal. Cards, form inputs, selected navigation, spacing and status presentation were refined.
- Quick navigation opens with Ctrl/Cmd+K or the search button. It filters workspace views and supports keyboard navigation through native buttons.
- Active navigation has an accessible current-page attribute. A skip link moves focus to workspace content; focus indicators, modal focus restoration and reduced-motion handling are included.
- Audit explorer performs server-side search, loads 25 records at a time and shows loading, no-result and error states. Refresh restarts the search.
- Operations readiness separates configured controls, local components and pending integrations. It does not label an unconnected provider as live.
- Responsive layouts are supplied for smaller screens. Browser review in this release covered the desktop preview, not a comprehensive mobile-device or accessibility certification.

## Additional backend work completed

### Audit search and pagination

The new GET /v1/audit-page endpoint filters by organization and search text before pagination. Stable descending created/id ordering prevents tied timestamps from dropping records. Signed cursors expire after 15 minutes and are bound to the organization and search. Tampering, expiry and cross-organization reuse fail closed. Page size is bounded at 200 and search text at 120 characters. The previous list endpoint remains for compatibility.

### Member revocation

A dedicated owner-only permission controls POST /v1/members/{id}/revoke. The request requires session authentication, CSRF and a reason. One transaction disables the member, removes local sessions and records an audit event. Cross-tenant targets are hidden. Self-revocation and owner revocation are rejected to protect ownership; security, engineer, approver and auditor roles cannot perform this operation.

The change blocks later local and SSO login for the revoked membership. External IdP offboarding, back-channel logout and owned agent containment remain separate controls. Revoking a human account does not silently revoke every workload identity.

### Expired operational records

The maintenance CLI defaults to a dry run. The explicit apply option removes expired sessions and export snapshots, plus OIDC transactions expired for at least one hour. Audit events, actions, approvals, members and business effects are preserved. Repeated cleanup is safe when no eligible rows remain. The command uses the configured database across organizations and is intended for authorized operators. An operator must configure and monitor its schedule; none is enabled by this delivery.

## Verification evidence

| Check | Result | Boundary |
|---|---|---|
| Full PostgreSQL integration suite | 97 passed; 0 failed; 0 skipped | Real PostgreSQL 16.2, OPA 1.0.1 and Keycloak 26.0.7 test services; verified HTTPS for Keycloak |
| SQLite regression | 85 passed; 12 skipped; 0 failed | The six Keycloak and six PostgreSQL-specific tests are excluded from this matrix |
| New operations cases | 9 passed within the suites | Pagination ties, search-before-limit, cursor scope/tampering/expiry, validation, cleanup preservation, revocation and tenant-local counts |
| Native policy suite | 5 passed in the preceding release | Policy source unchanged; historical result retained, not counted as a new run |
| Frontend build | TypeScript and Vite passed | Both application and synthetic preview builds |
| Browser review | Desktop sign-in, portal, quick navigation and readiness reviewed | Synthetic hosted-preview variant; no customer SSO or comprehensive device certification |

The 97-test total already includes the six Keycloak and six PostgreSQL race cases. Do not add these subsets again. The SQLite matrix overlaps the PostgreSQL suite. Detailed JUnit files and VERIFICATION.json are included. Two upstream test-dependency deprecation warnings remain; there were no test failures. CI configuration is supplied but was not run on a remote CI service here.

## Implemented versus remaining

| Area | Implemented now | Still open |
|---|---|---|
| Identity and access | Local sessions, tested OIDC/PKCE, role permissions, owner-controlled revocation | Multi-membership/environment switching, assigned-object access, workload federation, automatic IdP lifecycle and owner-transfer workflow |
| Governed execution | Scoped tools, policies, independent approvals, persisted worker queue, mock idempotent effects and reconciliation | General connector onboarding, customer resource constraints and one real authorized business connector |
| Operations | Dashboard, audit export/search/pagination, evaluations, containment, readiness and cleanup command | Redacted external telemetry/alerts, actual usage/billing, atomic spend reservations, scheduler installation and verified backup/restore |
| Security and infrastructure | Tested PostgreSQL/OPA/Keycloak paths, HTTPS verification, tenant-scoped APIs and supplied Compose/CI files | Managed secret retrieval, reviewed egress isolation, distributed edge abuse controls, cloud IaC, key rotation and hardened audit storage |
| Release readiness | Full source, compiled frontend, synthetic preview source, run/upgrade instructions and test evidence | Actual cloud deployment, customer configuration, independent security/load/accessibility review and pilot acceptance |

Some remaining items need further software development, not just credentials. Customer integrations also require the chosen system's API contract, sandbox permissions and credential delivery through a secure environment. Production deployment requires a selected cloud account, region, identity policy, data/retention rules and operational ownership. A different chat model does not supply these prerequisites or validate a customer pilot.

## Run, upgrade and maintain

For a new installation use README.md and the included Windows or Linux/macOS startup scripts. Initialization generates local development passwords. Run both the API and the separate execution worker. The installed application uses actual server authentication; demo placeholder credentials will not work there.

For an existing installation follow docs/UPGRADE_0_3_0.md. Stop the API and worker, back up both databases and preserve the private .env. Install dependencies, build the frontend if required, run the migration command and restart. Schema version remains 2; version-1 data-preserving migration is retained. No data reset is required.

From backend, python -m nexus.cli maintenance previews cleanup. Add --apply after reviewing the counts. Schedule it through a reviewed operating-system or cloud job runner. This cleanup is not an audit-retention policy, backup system or legal deletion mechanism.

## Package contents and practical limits

The ZIP contains backend and frontend source, compiled assets, the original SVG image, the separate demo-preview source, dependencies/lockfiles, API contracts, schema scripts, tests, SDK examples, startup/upgrade guidance, Compose/CI files and original project reference documents. Prior reports are archived by release. Runtime databases, real credentials, temporary certificates, test-service binaries, virtual environments and node_modules are excluded.

The connector still produces synthetic effects in a separate mock database. The private UI preview is deployed; the full Python control plane is not deployed to the customer cloud. Production readiness, a completion percentage, billing savings and an increase in profile value are not claimed.
