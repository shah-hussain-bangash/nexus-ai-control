# Operator-enabled local neural search

The search workspace now offers **Local neural similarity** alongside default
LSA/BM25. The new option is disabled until the operator configures it. No setting,
model, application database or running app is changed by this source increment.
No model download or real-model acceptance was performed during development.

## Operator configuration

Three separate environment settings control the feature:

- `NEXUS_OLLAMA_EMBEDDING_ENABLED=0` by default; explicit `1` enables the path.
- `NEXUS_OLLAMA_EMBEDDING_MODEL` must be an exact installed local model:tag.
- `NEXUS_OLLAMA_EMBEDDING_DIGEST` must be the corresponding 64-character lowercase
  digest reported by the local Ollama model list.

Enabling requires `local` mode. These controls are separate from chat-generation
settings. No operator configuration or credential can be supplied by a search
request. Configuration files are not modified by the API or dashboard.

The client uses fixed numeric loopback only. Before sending text it checks the
model-list digest and local embedding-capable GGUF metadata. It checks the digest
again after the embedding request and rejects mismatches. This binds results to
operator-selected, **server-reported** model identity; it is not cryptographic
attestation against a malicious local server or a swap-and-restore race. Metadata
checks use the [official model-list API](https://docs.ollama.com/api/tags), and
embedding requests use the [official embedding API](https://docs.ollama.com/api/embed).

## Request and processing

`POST /v1/hybrid-search` accepts `retrieval_mode: "local_neural"`. Omitted or
explicit `"local_lsa"` retains the legacy LSA request fingerprint and behavior.
The new mode uses positive cosine similarity only. LSA dimensions and blend
weights cannot be customized for neural requests; omit those controls. Existing
query, pinned source versions, minimum score, top-k and one-per-document controls
remain available. One-per-document grouping happens before top-k.

The API selects only current readable documents/chunks in the session's workspace
and environment **before** any text is sent to the worker or local model. Neural
requests support at most 20 documents, 32 passages, a 500-character query and
64 KiB total UTF-8 input. Oversized corpora are rejected rather than truncated.
The existing per-workspace limits apply across both modes: 30 new searches per
minute, two processing searches, and 1,000 stored receipts.

The neural child runs with a minimal environment, a 12-second parent wait, bounded
input/output files, and a 10-second local HTTP deadline. POSIX memory/CPU/file-size
limits and the existing cross-platform process-tree cleanup apply. Cleanup and
database admission add overhead; this is not an end-to-end latency SLO. The worker
receives no application DB/session credentials and never loads operator `.env`.

The parent validates the worker's model/digest, dimensions, request counts, score
shape/range/order and document diversity before saving hits. It rechecks the
session, source access/version/hash and operator model settings at completion.
Source or configuration changes discard results. There is no fallback or retry.
An empty corpus makes no local model request.

## Receipts, recovery and display

Saved parameters identify the mode, model tag and expected digest. Neural results
use their own method version, without claiming that LSA Arabic normalization was
applied. Raw queries, vectors and newly copied excerpts are not saved in history;
excerpt inspection still reads current authorized chunks. History filters sources
again after later revision or access changes.

A successful nonempty neural search reports four local HTTP requests: two
model-list reads, one metadata inspection and one embedding call. Failed or
interrupted neural searches report unknown call counts rather than zero. Local
hardware/electricity costs are not provider billing acceptance.

Idempotent replay and recovery return the original receipt without another model
call, including after operator configuration changes. A new model configuration
does not relabel old receipts; a new intent is required for a new execution.
The dashboard uses one shared request body for intent hashing and submission.

## Verification and remaining scope

Focused tests cover synthetic real-client transport, digest changes before/after
embedding, normal API source isolation and revocation, completion races, legacy
hashes, request bounds, worker protocol validation and parent process timeout.
A real child rejects an unpinned payload before HTTP; valid embedding exchanges
use mock transports only. No test contacts the PC's Ollama service.

This direct-search route adds bounded authorized neural ranking. The subsequent
[stored-index runtime](RUNTIME_NEURAL_INDEXES.md) adds persistent build/query APIs;
scalable indexing, learned reranking, generated-answer evaluation and independent
bilingual quality acceptance remain. No real model has been selected or accepted for the running
pilot. The roadmap remains partial. This review change builds on PR #84; merges,
active configuration, model installation and deployment remain separate decisions.
