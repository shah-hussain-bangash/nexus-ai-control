# 0.5.0 provider demonstration boundary

The earlier local demo sequence below is retained. For the new inference path, first read MODEL_RUNTIME.md. Use only approved/synthetic text and a separately configured provider account. Demonstrate the checked route, reservation, response usage and idempotent replay. The source was tested with a controlled HTTP transport; do not describe that as a live provider integration already deployed to your account.

Current production gaps are in PRODUCTION_ACCEPTANCE.md. Do not add a complete production-system claim to the resume yet.

---

# NEXUS: flagship engineering demonstration

## The story to demonstrate

Show how an AI proposal becomes an inspectable, policy-controlled action with human review and durable evidence. Connect the experience to GenAI engineering, agent governance, bilingual retrieval and full-stack software design. Explain the implemented boundaries as engineering decisions.

## Suggested sequence (15 minutes)

1. Sign in as the local owner and open the AI command center. Load the 18 synthetic starter designs. Explain which metrics come from business records and which are design assets/runs.
2. Workflow Studio: open Procurement decision pipeline. Show Input → Guardrail → Retrieve → Prompt → Policy → Approval → Tool → Verify → Output. Edit a label, save a revision and inspect history. Link a saved prompt if desired; the reference is pinned to its version.
3. Knowledge & RAG: inspect Procurement policy handbook and the Arabic governance document. Use Test bench with a procurement or Arabic query. Show source text, chunk, score and citation version/hash. Explain BM25 lexical retrieval versus a future vector/semantic pipeline.
4. Prompt registry: inspect Evidence-first assistant, render it with the required variables and review assertions. This composes a prompt; it does not fabricate a model answer.
5. Safety workbench: test a synthetic email or known override phrase. Compare block and redaction modes; do not describe the rules as comprehensive prompt-injection prevention.
6. Evaluation lab: run Knowledge retrieval regression. Inspect each expected title and retrieved result; explain title recall@K and its limited relationship to answer quality.
7. Workflow Studio: dry-run Procurement decision pipeline with USD 12,500. Explain why the local preview stops for independent approval. It does not submit or execute a purchase.
8. Use **Run governed action** in the real application: Procurement Atlas → explicitly select **Purchase requests**, enter SUP-DEMO-104, USD 12,500 and a synthetic purpose. Submit once. Open a separate browser session as reviewer@nexus.local; find the new Pending request and review it before the displayed expiry. Use the note “Reviewed synthetic supplier, amount and purchase purpose.” Approve only the intended synthetic payload. Return to Execution ledger and verify the worker outcome. Do not approve an expired record or use the requesting account as independent reviewer.
9. Traces & observability: inspect the saved workflow/retrieval/evaluation run, measured local duration, steps and JSON export. Audit explorer shows business governance events separately.
10. AI FinOps and Release readiness: calculate a token-cost scenario from explicit assumptions; show the rollback/checklist plan and the external integration gates still open.

## Evidence to prepare for interviews

A concise architecture discussion; a source walkthrough of tenant scopes, idempotency, optimistic updates and version pinning; a reproducible test run; a short demo recording with synthetic data; a realistic failure/recovery example; and a candid roadmap. Publicly share selected source only if you own it and it contains no credentials or employer data. The source can remain private with a guided demo and architectural write-up.

## Accurate project description

“Built NEXUS AI Control, a React/TypeScript and FastAPI engineering workspace for versioned agent workflows, bilingual retrieval, prompt validation, deterministic policy evaluation, independent approval and audit evidence. Implemented tenant-scoped persistence, revision checks and repeatable local tests; designed provider, connector, FinOps and deployment interfaces with explicit integration boundaries.”

Do not add cloud adoption, user counts, savings, model quality improvements or production certifications without measured evidence. Keep the eight years of career experience distinct from this project's age and scope.
