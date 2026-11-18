# Release 0.6.0 — clearer UI and operational workflow functions

Schema 5 adds ReadinessEvidence; existing accounts, business records, inference ledger and workbench records remain intact. The release retains all 0.5.0 provider/budget/backup controls and adds the readiness board, evidence history via audit events, database-backed inference admission, paginated evidence and same-tab reload recovery.

Readability changes apply to sign-in, original governance views, workbenches, forms, tables and the new readiness board. Comfortable mode uses a 14px body and 13px navigation; Larger text uses 16px body and 15px navigation. Small labels use a 12px floor in comfortable mode and 14px in larger mode. Desktop review verified the selected sizes, no document-level horizontal overflow at the tested width, keyboard tabs, the evidence form and readiness export. This is not a formal accessibility certification or a comprehensive mobile-device test.

The 18-item roadmap is defined in backend/nexus/readiness.py and documented in PRODUCTION_ROADMAP.md. Source delivery and operator-attested acceptance remain distinct. A fresh database has no supplied acceptance attestations. No real provider, customer connector, cloud deployment or external-service acceptance was performed here. See VERIFICATION.json for the final checks.
