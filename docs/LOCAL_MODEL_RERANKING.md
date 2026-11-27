# Optional local model passage reranking

This development increment adds a second ordering pass over a saved indexed-search
result, using an operator-pinned local completion model. It builds on PR #91,
requires schema 12 and adds no migration. It does not activate a model or update
the running application.

## Scope and operator opt-in

New environment-only settings default to disabled:

```
NEXUS_OLLAMA_RERANK_ENABLED=0
NEXUS_OLLAMA_RERANK_MODEL=
NEXUS_OLLAMA_RERANK_DIGEST=
```

An enabled configuration requires local mode, an explicit installed model:tag and
its exact 64-character lowercase digest. This opt-in is separate from embedding
and answer-generation settings. No model is installed/pulled, no credential is
accepted, and no remote endpoint or environment proxy is used. Only fixed numeric
loopback `http://127.0.0.1:11434` is contacted during actual enabled execution.

The client uses Ollama's [chat endpoint](https://docs.ollama.com/api/chat) and
[structured-output format](https://docs.ollama.com/capabilities/structured-outputs).
It checks the installed digest before and after the request and requires local
GGUF weight metadata and completion capability before sending text. The protocol
has a 20-second elapsed HTTP deadline and a 22-second isolated child-process
deadline, bounded response bytes, 512 output tokens and an 8,192-token context
option. Prompt serialization is bounded to 16 KiB. Actual tokenizer/context
behavior and model quality still require representative acceptance.

## Dashboard and normal API

Open your original completed indexed-search result with 2–10 current passages.
In **Optional local passage reranking**, repeat its exact query. The server checks
the original author's private query identity, the current saved-search digest,
every selected index/version/hash and every source ACL before dispatch and again
at completion. Older searches without a query identity must be run again first;
rotating the identity key also requires a fresh original search. Administrative
read access does not authorize submitting another actor's search for reranking.

`POST /v1/neural-indexes/rerank` accepts only `search_id` and `query`, plus the
usual intent-key header. It reserves a normal search receipt and shares retrieval
rate/history/in-flight limits. Intent replay and the existing hybrid-search
recovery endpoint return the original receipt without another model call, even
after reranking is disabled. Recursive reranking is rejected; start from the
original saved result rather than creating an unbounded chain.

The model receives numbered passage text and query data, not source IDs, vectors,
tools or credentials. It must return a complete permutation of existing integer
positions. Duplicate, missing, out-of-range, boolean or invented positions fail
the whole operation, as do malformed/ambiguous JSON, extra prose/fields, tool
calls, truncated/late completion or model/configuration/source changes. There is
no silent fallback or partial reordered result. Passage/query instructions cannot
activate business actions; resistance to malicious influence on ordering still
requires separate quality/security evaluation.

The new receipt contains the same candidate passages and original cosine scores
in a different order, with server-derived ordinal positions and pinned reranker
identity/protocol. It does not add sources, answer the query, create a new
confidence score, retrain a model or provide a dedicated cross-encoder service.
The original search remains unchanged. Original similarity scores may no longer
descend in model order; the dashboard labels this explicitly. Raw query text,
prompts, excerpts and free-form model output are not copied into the receipt.

Successful reranking reports four local HTTP requests separately from the parent
search's call count. Failed/interrupted reranking has unknown call counts. Raw
model output is discarded after validating the permutation and bounded usage.

## Saved quality reviews

The existing reviewer-labelled quality flow can measure and compare original and
reranked receipts under matching query/actor/labels/search controls. It discloses
reranking/model changes while retaining index/corpus change flags. Recall and
precision over the unchanged candidate set should remain unchanged; reciprocal
rank can improve or worsen. A format-valid order and a favourable saved metric
do not establish representative relevance, bilingual quality or causal model
improvement. Source access and stale-evidence rules continue to apply.

## Focused development checks

Synthetic HTTP transport and disposable API checks cover digest/locality fences,
strict permutations/JSON, deadline/size bounds, input snapshots, disabled/default
configuration, exact-query binding, source/configuration/parent changes during
execution, scoped access, recursive rejection, lost-reply recovery and saved
rank-quality comparison. Related indexed runtime/review/comparison checks and
the frontend build cover compatibility. No live model/customer system was called.
Full acceptance, model selection/download, merging and deployment remain deferred.

Larger-scale indexing/storage and the other unfinished roadmap workstreams remain
development work. Representative model/context, bilingual and prompt-injection
acceptance remain later testing work.
