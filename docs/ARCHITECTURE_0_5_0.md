# NEXUS 0.5.0 runtime relationships

```mermaid
flowchart TD
 UI["Authenticated portal"] --> API["FastAPI role and CSRF checks"]
 API --> WB["Versioned workbench previews"]
 API --> LIVE["Explicit inference request"]
 API --> GOV["Governed synthetic action"]
 LIVE --> RULES["Checked route, input rules and operator allowlist"]
 RULES --> RESERVE["Atomic monthly reservation and idempotency ledger"]
 RESERVE --> PROVIDER["OpenAI or Azure OpenAI HTTPS"]
 PROVIDER --> RESULT["Usage settlement or unresolved hold"]
 RESULT --> DB["Scoped SQLAlchemy persistence"]
 WB --> DB
 GOV --> REVIEW["Policy and independent approval"]
 REVIEW --> WORKER["Synthetic execution worker"]
 WORKER --> DB
```

Provider requests are synchronous and non-streaming; they do not execute business tools. Workbench pipelines remain local dry runs. Durable multi-step agent execution and real customer adapters remain unimplemented. The deployment candidate adds an HTTPS edge and external IdP/PostgreSQL configuration, but is not proof of cloud readiness.
