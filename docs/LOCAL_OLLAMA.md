# Local Ollama connection

This opt-in adapter connects NEXUS local mode to an already installed Ollama
server and already downloaded local model. It never installs software, downloads
or pulls a model, signs in to a cloud account, or provisions a provider key.
Ollama is disabled by default. The adapter is not available in pilot mode.

## Prerequisites

- Run Ollama and NEXUS in the same host/network namespace. The adapter fixes the
  address to `http://127.0.0.1:11434`. It cannot reach a Windows host from a
  separate Docker container through that container's loopback address.
- Install Ollama separately using its [official download](https://ollama.com/download).
  Select a model compatible with the available RAM/VRAM and download it separately.
  NEXUS does not choose or download a model automatically.
- Disable cloud features on the **Ollama server**, using `OLLAMA_NO_CLOUD=1` or
  `disable_ollama_cloud: true` in its server configuration, and restart Ollama to
  apply that setting. Setting the variable only on the NEXUS process does not
  disable cloud features in a separate Ollama process. See the
  [official local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).
- Use `ollama list` to identify an installed model's exact `name:tag`.

The connector checks `/api/show` before sending the question: remote-model/host
metadata is refused, and local GGUF weight metadata is required. Known cloud-tag
suffixes are rejected. These checks trust the local server's metadata and are
not attestation against a malicious local process or a model alias changed
between inspection and inference. The operator must disable Ollama cloud features
and enforce local server/network access. Public/local does not establish model
license suitability, bilingual quality or customer acceptance.

## NEXUS operator configuration

After reviewing this source and arranging a maintenance window, configure the
NEXUS server's environment. Replace the symbolic model below with an actual
installed `name:tag`; it is not a download command:

```text
NEXUS_OLLAMA_ENABLED=1
NEXUS_OLLAMA_MODELS=your-installed-model:tag
```

Restarting NEXUS is required to load changed server settings. Multiple allowed
models can be comma-separated (at most 100 distinct tags). Empty lists, untagged
names, duplicate tags and known cloud suffixes are refused. Do not enter secrets.
For a local-only setup leave `NEXUS_LIVE_INFERENCE=0`. Local execution needs no
provider host allowlist, provider API key, token-price map or positive USD budget.
Do not reset existing hosted-provider settings or usage records when adding the
local option to an already configured workspace.

Local calls record zero **provider-token cost**, excluding hardware, electricity,
model-license costs and any separately configured service. They preserve the
existing hosted-cost ledger, including held reservations; they do not consume or
reset its USD balance. All model calls still share workspace request/concurrency
limits. Hosted execution remains separately disabled unless its own opt-in,
positive token rates, host allowlist and budget requirements are met.

## Owner setup in the app

1. Create a model asset and choose **Ollama**. The UI selects the fixed local
   endpoint and clears/disables the credential reference.
2. Enter the exact installed and operator-allowed `name:tag`. Choose output and
   timeout limits appropriate for the local model; first model loading can be slow.
3. Save and **Check saved config**. This validates configuration only; it does not
   prove connectivity or run a model.
4. Open the existing Live inference console, refresh runtime and select this
   checked model route. Start with a short synthetic question in English, then
   Arabic. Select retrieval only when the included evidence is appropriate.
5. A completed result must include the actual answer and token counts. The normal
   API still enforces role/workspace/environment boundaries, guardrails, version
   checks, idempotency and shared admission limits. Model output never dispatches
   business tools. The adapter uses a bounded non-streaming `/api/chat` request.
   When model metadata advertises thinking support, thinking is disabled so the
   bounded output allowance is available for the answer.

On an unknown result, reuse/recover the same intent; do not submit a different
intent automatically. Missing models, remote metadata, redirects, malformed/late
responses and timeouts produce an unknown outcome without an automatic retry.
No question/evidence is sent when local weight inspection fails. The metadata
inspection receives only the allowed model name. Inspection and chat share one
overall deadline, ignore HTTP proxy environment settings, follow no redirects
and forward no provider credentials.

## Verification boundary

Automated tests use disposable databases and an HTTP mock transport. They check
API flow, zero-cost accounting, credential/egress boundaries, guardrails, roles,
rate admission, remote metadata rejection, malformed completions and uncertainty
recovery. They do not prove a live Ollama installation, GPU support, inference
speed, English/Arabic answer quality or production readiness. A live smoke test
against an installed downloaded model remains required before acceptance.

API references: [Ollama chat](https://docs.ollama.com/api/chat),
[local API introduction](https://docs.ollama.com/api/introduction),
[official model response types](https://github.com/ollama/ollama/blob/main/api/types.go).
