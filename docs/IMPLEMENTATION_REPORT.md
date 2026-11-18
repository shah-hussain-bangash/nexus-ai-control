# NEXUS AI Control implementation — 0.16.0

This release adds two connected runtime capability sets while preserving the existing 18-area/216-function UI baseline and previous working services.

- Knowledge & RAG now runs local corpus-fitted LSA/BM25 search with source revision fencing, current ACL filtering, score controls, citations, bounded subprocess execution and recoverable saved receipts. This is not neural embedding/vector-database or generated-answer delivery.
- Workspace settings now supports owner-only reviewed member provisioning, conditional exact OIDC subject binding, role/activation changes, offboarding, optimistic member revisions and session revocation. Everyone can inspect their own active session handles and revoke other sessions. A local-only password CLI replaces PowerShell string-injection reset snippets. No invitation email or password is issued by the dashboard.
- Search labels, member names/buttons and dialogs received explicit light/dark contrast rules. New runtime code is lazy-loaded. The product design walkthrough still cannot activate services and now exports 0.16 handoffs while retaining validated earlier import compatibility.

Full backend regression: 288 passed, 15 skipped out of 303; frontend: 51 passed. Both builds pass. New search/member backend tests: 20 passed. Catalog/readiness metadata targeted regression: 33 passed. Native Windows and external-service/deployment acceptance remain open.

**This is not a complete production-ready enterprise platform.** Current roadmap: one implemented awaiting acceptance, sixteen partial and one not implemented, with zero accepted default gates. Read PRODUCTION_GAPS_0_16_0.md for every workstream and FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv for every catalog function, including planned features. There is no invented percentage or certification. Follow UPGRADE_0_16_0.md; schema stays 8 and private configuration/data must be preserved.
