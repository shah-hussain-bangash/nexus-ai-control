# UI layers — 0.11.0

| Layer | Defined coverage |
|---|---|
| Primary navigation | 24 views |
| Module workspaces | 18 modules; 9 sections each |
| Module settings | 161 fields |
| Dedicated operational experiences | 18 |
| Operational record controls | 97 fields |
| Operational rehearsal transitions | 126 commands |
| Legacy module API handoffs | 54 planned action contracts |
| Detailed function designs | 216 shared-pattern screen definitions |
| Function design controls | 648 fields |
| Function review interactions | 3 per function; browser-local previews |
| Function screen states | 8 per function |

The full named list is LONG_TERM_UI_MASTER_SPEC.md and PLATFORM_FUNCTION_INVENTORY.csv. Existing operational coverage details are archived under archive/0.8.0/UI_COVERAGE_MATRIX.md. Counts describe different layers and are not an overall production-completion percentage.

## Actual runtime workspaces added in 0.11.0

Agent execution: persisted bounded sequence, independent review, pause/resume/cancel/recovery and governed action links. Document library: bounded UTF-8 intake, current source ACLs, lexical citations and logical active-store deletion. These working paths do not implement the entire corresponding design modules. See IMPLEMENTATION_REPORT.md.

Document library additionally includes content replacement, current citation verification and saved lexical quality evidence. These are real authenticated paths, separate from the retained Evaluation lab design experience. Navigation remains 24 views.
