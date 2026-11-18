# NEXUS AI Control — 0.16.0

**Cursor on Windows:** start with [CURSOR_QUICKSTART.md](CURSOR_QUICKSTART.md).
Run `npm run setup`, then `npm start` from this folder.

Enterprise Agentic AI Governance, Security & Operations Platform.

New working services: **local hybrid document retrieval** and **owner-controlled member/session administration**, connected to Knowledge & RAG and Workspace settings. Existing governance, approvals, execution, reviewed document intake, provider controls, business adapter and UI design workflows are retained.

Windows: follow [Upgrade guide](docs/UPGRADE_0_16_0.md), run `scripts\start.cmd` and open the printed URL. Keep the API/worker terminal open. Schema remains 8; preserve private configuration, accounts and data.

- [Implemented source and verification](docs/IMPLEMENTATION_REPORT.md)
- [All production gaps and ordered next work](docs/PRODUCTION_GAPS_0_16_0.md)
- [Every planned function and connected boundary](docs/FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv)
- [Local hybrid retrieval](docs/HYBRID_RETRIEVAL_0_16_0.md)
- [Members, roles and sessions](docs/IDENTITY_LIFECYCLE_0_16_0.md)
- [Current UI baseline](docs/UI_BASELINE_0_16_0.json)
- [Machine-readable verification](docs/VERIFICATION.json)

The agreed design inventory remains 18 areas / 216 function previews. Design records, walkthrough roles/environments and exported review markers do not activate backend integrations. The isolated demo-preview harness blocks runtime writes; frontend and backend contain the authenticated application.

**Full enterprise production readiness is not claimed.** The roadmap has 1 implemented, 16 partial and 1 missing lifecycle workstream, with deployment acceptance still open. Read the gap report before rollout. No real customer, IdP, cloud or provider account was changed by this release.
