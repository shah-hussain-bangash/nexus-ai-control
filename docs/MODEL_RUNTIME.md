# Configure provider execution in staging

Execution is disabled by default. No provider key is bundled. The runtime API and console are separate from workbench configuration tests.

## Operator configuration

Set NEXUS_LIVE_INFERENCE=1 only after setting NEXUS_PROVIDER_HOSTS to the exact host, NEXUS_MONTHLY_BUDGET_USD to a positive organization-month limit, and NEXUS_PROVIDER_PRICES to a JSON map keyed by host|model. Each map value must contain positive input and output rates in USD per million tokens. Choose actual approved rates from your provider agreement; no market prices are assumed by this package.

The price shape is {"HOST|MODEL":{"input":"INPUT_USD_PER_MILLION","output":"OUTPUT_USD_PER_MILLION"}}. The symbolic values are placeholders, not valid numeric configuration. The server rejects nonnumeric, nonfinite or nonpositive rates.

Inject a provider key under a dedicated name such as NEXUS_PROVIDER_PRIMARY_KEY through your secret manager. The model asset stores only env:NEXUS_PROVIDER_PRIMARY_KEY. References to NEXUS_SECRET or unrelated server variables cannot be resolved by the inference adapter.

Supported endpoint bases: https://api.openai.com/v1 for OpenAI; https://RESOURCE.openai.azure.com/openai/v1 for classic Azure OpenAI. The exact host must be allowlisted and the exact requested model/deployment must have server rates. No redirects or arbitrary/local hosts are followed. TLS verification remains enabled and HTTP proxy environment variables are ignored for provider calls. Network egress enforcement and private-endpoint DNS are operator responsibilities.

## Console sequence

1. Owner/security: create or update a model route, including model/deployment, endpoint, credential reference, output cap and timeout. Save, then Check saved config. Editing later resets it to Draft.
2. Open Model gateway or AI FinOps and scroll to Live inference console. Refresh runtime to load checked routes.
3. Confirm the operator-enabled state and budget. Enter synthetic or approved text. Selecting the retrieval checkbox explicitly includes local evidence in the provider request.
4. Send once. The request key is retained for same-body retry while the page remains open. The response and usage enter the inference ledger. “Recheck same request” retrieves the existing record; “Start a new request” intentionally creates a new billable intent.
5. On Unknown, do not create another intent. An owner checks provider usage, enters verified token counts and an evidence note, and settles the reservation once. Pending calls can be reconciled after 300 seconds if the processing worker crashed; investigate the process/provider first.

Token rates and budget assets in the cost-planning workbench do not control this runtime. Runtime prices and monthly cap come from operator configuration. Account-level spending limits remain separate. Output is plain text; no tool calls, automatic actions, streaming or fallback are implemented.

An HTTP 200 response is not sufficient to complete a call. The adapter checks the JSON object, usage object, nonempty choices list, first choice and message object before reading the answer. Invalid containers, noninteger or out-of-range usage, nontext answers and tool-call responses are treated as Unknown. The reservation stays held; same-key replay and recovery return the existing record without another provider request. An owner must reconcile verified usage before the reservation is released. These malformed-response cases are tested with synthetic HTTP transports; live provider acceptance remains open.

The provider timeout is also an elapsed-time completion boundary. The adapter checks a monotonic deadline after headers arrive, during body reads and before returning the decoded, validated result after stream cleanup. A response finishing at or after that deadline becomes Unknown even if its HTTP status, answer and usage are otherwise valid. This does not cancel or undo provider work or prove that no charges occurred. The reservation stays held until owner reconciliation; replay and recovery do not resend the call. Boundary tests simulate time inside the adapter only and do not demonstrate real-network latency or live provider acceptance.

## API source references

- OpenAI Chat Completions: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- Azure OpenAI v1 lifecycle: https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle
- Azure OpenAI v1 endpoint pattern: https://learn.microsoft.com/en-us/azure/ai-studio/ai-services/concepts/endpoints

The implementation uses non-streaming chat messages, max_completion_tokens and returned usage fields. Unit tests use an HTTP mock transport, not a live provider. A live staging smoke test remains mandatory for the chosen deployment/model.


## 0.6.0 admission and recovery

Set the same NEXUS_INFERENCE_REQUESTS_PER_MINUTE and NEXUS_INFERENCE_MAX_INFLIGHT values on all workers (defaults 30 and 4). Admission is database-coordinated per organization; pending concurrency uses a 300-second window. Saturation returns 429 without a new provider dispatch. Idempotent replay returns the recorded call.

After a same-tab reload, Recover saved request retrieves the existing author's call without submitting again. Only the key/fingerprint/timestamp recovery envelope is stored in sessionStorage. Unknown/pending outcomes block starting a different intent from that saved envelope until resolved; recover again after owner reconciliation. If no record can be recovered, inspect the scoped ledger and investigate before creating another intent. Browser storage must be available; no recovery guarantee spans closed tabs or other devices.

Use Inference history for status/reference search, 10-item pages, previous/next navigation and current-page JSON export. Cursor expiry or changed search requires starting at the first page. No automatic inference retention deletion is introduced.
