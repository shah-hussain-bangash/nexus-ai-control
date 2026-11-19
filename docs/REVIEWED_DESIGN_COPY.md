# Reviewed local design copying

An owner can copy a validated **prompt or guardrail** from the currently selected environment to another assigned active environment in the same workspace. Open Workspace settings → Copy reviewed designs. Refresh the choices, inspect the source configuration, choose the target, name the new draft, enter a review reason and confirm the checkbox.

The server rechecks the source ID/version/status, configuration, target environment version/state and owner assignment under the workspace admission lock. The target receives a new ID, draft status, version 1 and one revision with source provenance. The original asset, target's existing assets and validation history stay unchanged. The new draft must be separately reviewed and validated after selecting the target environment. Copying never runs a model, changes a policy or grants access.

Only standalone prompt and guardrail fields are supported. This is not a general import or runtime promotion: workflows, linked references, models, connector settings, credential bindings, document content/ACLs, agents, grants, approvals, usage, budgets and deployment acceptance are excluded. Prompt contents and description are copied as reviewed; inspect those contents and target membership before sharing them with the target environment. Pilot copying remains disabled.

## Uncertain outcomes

A request key is saved in this browser's session storage under workspace, account and source environment. The server stores a durable receipt under the same scope. Retrying the identical key/body returns the original created asset; changed intent with the same key is rejected. Receipts remain recoverable after source edits, and after target pause/retirement, provided the owner retains target assignment. Receipt recovery reveals outcome metadata, not target contents or current validation status.

If a response is interrupted, use **Recover copy result**. If no completed outcome is available, **Cancel pending copy** records a durable cancellation under that key. Copy and cancellation use the same lock: cancellation either returns the already-completed copy without deleting it, or prevents a delayed submission from creating any draft. A cancellation does not undo a completed copy. The UI clears its pending key only after an acknowledged copied/cancelled result. Access loss can require restoring assignment before a completed receipt can be recovered; the UI does not silently discard it.

Receipts store identifiers, versions, a request fingerprint and outcome metadata; they do not store a second copy of prompt contents or the raw request key. They are excluded from workbench execution history. Source audit events contain provenance and the review reason, without configuration contents. Each workspace supports up to 1000 copy/cancellation receipts, and copying requires fewer than 500 design records in the target, including archived drafts. These controls do not delete receipts or reset counters. Schema remains 11.

General configuration promotion, reference remapping, pilot lifecycle and deployment acceptance remain future work. Local copy tests do not certify a production environment.
