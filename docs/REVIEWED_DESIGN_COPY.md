# Reviewed local design copying

An owner can copy a validated **prompt, guardrail, workflow, model or connector design** from the currently selected environment to another assigned active local environment in the same workspace. Open Workspace settings → Copy reviewed designs. Inspect the source and target preview, choose the target, name the new draft, enter a review reason and confirm the checkbox.

The server rechecks the source ID/version/status, configuration, target environment version/state and owner assignment under the workspace admission lock. The target receives a new ID, draft status, version 1 and one revision with source provenance. Original assets and validation history stay unchanged. The new draft must be separately reviewed and validated after selecting the target environment. Copying never runs a model, changes runtime policy or grants access.

This is a local design copy. Credential bindings, document content/ACLs, agents, grants, approvals, execution history, usage, budgets and deployment acceptance are excluded. Source content, endpoint and description are copied as reviewed; inspect those fields and target membership before sharing them. Pilot copying remains disabled. An environment named production is still a local database partition, not a deployment or acceptance result.

## Model and connector draft resets

Model copies preserve their reviewed provider, model, endpoint and bounded generation settings, but always clear `credential_ref`. Hosted models cannot reuse the source credential reference after target validation. Ollama retains its fixed numeric-loopback configuration and still requires the existing server opt-in and allowed installed model. Copying does not resolve credentials, inspect models, download weights, contact endpoints or change allowlists.

Connector copies preserve protocol and endpoint, clear `credential_ref`, replace `scopes` with an empty list and set `read_only` to true. Source write preferences and scopes are not transferred. The target requires an explicit new review before setting its own references or permissions. Connector designs do not configure the separately controlled business adapter.

The dashboard previews these reset target settings alongside the reviewed source. Configuration is not accepted from the copy request: the server derives and resets it from the pinned source version. Initial provenance, audit detail and the saved receipt record `reset_fields` (`credential_ref` for models; `credential_ref`, `scopes`, `read_only` for connectors). The structured `credential_ref` field is empty in both the target configuration and its initial revision. The client requires that reset acknowledgement before retiring a pending route-copy intent.

All copies start as Draft v1, without copied validation history, credentials, runtime flags, budgets, model rates, execution records or connection acceptance. Existing source configurations are not mutated. Knowledge and other unsupported kinds remain excluded. Only workflows accept reference mappings.

## Workflow reference mapping

Map every referenced workflow step to an existing validated target design of the matching type: retrieval → knowledge, prompt → prompt, guardrail → guardrail. Choices expose only IDs, names, kinds and versions. Source dependencies must remain validated at the pinned versions. Stale dependencies/versions, wrong kinds, missing/extra/duplicate mappings or unavailable targets reject the whole copy.

The new workflow receives only target IDs and reviewed versions. Dependencies and their history are not copied or overwritten. Provenance records the explicit source-to-target mappings. A workflow without references needs no mapping. The copy does not create a durable execution, authorize a business effect or run any step.

## Uncertain outcomes and compatibility

Browser request keys are scoped by workspace, actor and source environment. The server retains a durable receipt under that scope. An identical retry returns the original outcome; a changed body conflicts. Recovery remains available after source edits and target pause/retirement when target assignment is retained. It returns historical copy metadata, not current target contents or validation state. Later target edits are never overwritten by replay.

Use **Recover copy result** after an interrupted response. **Cancel pending copy** either returns an already-completed copy without deleting it or records a tombstone preventing delayed submission from creating a draft. Copy and cancellation share the same lock. A cancellation cannot undo a completed copy. The client clears its key only after an acknowledged copied/cancelled result; access loss does not silently discard it.

Prompt/guardrail/workflow receipts and pending requests remain compatible. No new request field or fingerprint format is introduced. An omitted/empty reference mapping list retains its existing fingerprint behavior. Model/connector receipts add the required reset metadata; they contain no configuration or raw request key.

Each workspace supports up to 1000 copy/cancellation receipts, and copying requires fewer than 500 target design records, including archived drafts. Existing receipts and counters are preserved. Uses existing schema 12 storage; no migration or new runtime setting is introduced.

## Verification and remaining scope

Focused disposable checks cover route resets, unmodified sources, target revisions/provenance, replay after target edits, required versions/mappings, draft execution refusal, cleared hosted-model references, existing copy/cancellation races and local environment switching. Frontend checks cover source/target pinning, immutable reset previews and reset-aware receipt acknowledgement. No real provider or customer system is contacted.

General runtime configuration promotion, dependency copying, new model/connector bindings, pilot lifecycle and deployment acceptance remain separate work. Local copy checks do not certify a production environment. The running app, actual records, credentials and configuration are unchanged by this development increment.
