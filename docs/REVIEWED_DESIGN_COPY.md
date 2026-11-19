# Reviewed local design copying

An owner can copy a validated **prompt, guardrail or workflow design** from the currently selected environment to another assigned active environment in the same workspace. Open Workspace settings → Copy reviewed designs. Refresh the choices, inspect the source configuration, choose the target, name the new draft, enter a review reason and confirm the checkbox.

The server rechecks the source ID/version/status, configuration, target environment version/state and owner assignment under the workspace admission lock. The target receives a new ID, draft status, version 1 and one revision with source provenance. The original asset, target's existing assets and validation history stay unchanged. The new draft must be separately reviewed and validated after selecting the target environment. Copying never runs a model, changes a policy or grants access.

This is a design copy, not a general import or runtime promotion. Models, connector settings, credential bindings, document content/ACLs, agents, grants, approvals, execution history, usage, budgets and deployment acceptance are excluded. Prompt contents and description are copied as reviewed; inspect those contents and target membership before sharing them with the target environment. Pilot copying remains disabled.

## Workflow reference mapping

For a workflow, map every referenced step to an existing validated design of the matching type in the target: retrieval → knowledge, prompt → prompt, guardrail → guardrail. Target choices expose only IDs, names, kinds and versions; configuration and knowledge contents are not fetched or copied. Source dependencies must still be validated at the workflow's pinned versions. A stale source dependency, stale target version, wrong kind, missing/extra/duplicate mapping or unavailable target rejects the whole copy.

The new workflow receives only target IDs and their reviewed versions in its configuration. Dependencies and their history are not copied or overwritten. Its initial provenance revision records the source workflow and the explicit source-to-target reference mappings. A workflow with no references needs no mapping. The new workflow always starts as Draft v1 and must be reviewed and validated separately. This operation does not create a durable execution, resolve tools, authorize a business effect or run any workflow step.

Existing standalone-copy receipts and pending browser requests remain compatible: an omitted or empty mapping list retains the original fingerprint format. A nonempty workflow mapping list participates in the request fingerprint, so an uncertain request cannot silently be retried with different mappings. Cancellation fencing and receipt recovery apply to workflows as well.

## Uncertain outcomes

A request key is saved in this browser's session storage under workspace, account and source environment. The server stores a durable receipt under the same scope. Retrying the identical key/body returns the original created asset; changed intent with the same key is rejected. Receipts remain recoverable after source edits, and after target pause/retirement, provided the owner retains target assignment. Receipt recovery reveals outcome metadata, not target contents or current validation status.

If a response is interrupted, use **Recover copy result**. If no completed outcome is available, **Cancel pending copy** records a durable cancellation under that key. Copy and cancellation use the same lock: cancellation either returns the already-completed copy without deleting it, or prevents a delayed submission from creating any draft. A cancellation does not undo a completed copy. The UI clears its pending key only after an acknowledged copied/cancelled result. Access loss can require restoring assignment before a completed receipt can be recovered; the UI does not silently discard it.

Receipts store identifiers, versions, a request fingerprint and outcome metadata; they do not store a second copy of prompt contents or the raw request key. They are excluded from workbench execution history. Source audit events contain provenance and the review reason, without configuration contents. Each workspace supports up to 1000 copy/cancellation receipts, and copying requires fewer than 500 design records in the target, including archived drafts. These controls do not delete receipts or reset counters. Schema remains 11.

General configuration promotion, dependency copying, model/connector bindings, pilot lifecycle and deployment acceptance remain future work. Local copy tests do not certify a production environment.
