# Local neural embedding foundation

This development increment provides a bounded local embedding client, cosine
ranking helper, and an explicit synthetic exercise. It does **not** change the
current dashboard search, answer-generation retrieval, database schema or active
operator configuration. Existing LSA/BM25 behavior remains unchanged.

## Implemented source

`backend/nexus/local_embeddings.py` exposes `embed_texts` and `rank_texts`.
There are no mounted application routes, settings loads or database reads.
Callers must authorize text before passing it to these helpers; the helpers
themselves make no account, workspace, environment or document-ACL decision.

The client accepts an explicit local model:tag and uses only numeric loopback
`http://127.0.0.1:11434`. It first calls `/api/show` without query/source text and
requires local GGUF weight metadata and the embedding capability. Remote host or
model metadata and cloud tags are rejected. These are checks of server-reported
metadata, not authentication or proof of network isolation/model provenance.

It then makes one `/api/embed` batch with `truncate: false`. It has no model-pull,
remote endpoint, redirect-following, proxy, credential, retry or fallback path.
The current Ollama API contract is documented in the
[official embedding endpoint](https://docs.ollama.com/api/embed).

Input is limited to 33 strings, 4 KiB per string and 64 KiB total UTF-8 text.
Input lists are snapshotted before validation or metadata I/O; later caller
mutations cannot change transmitted text or reported corpus counts.
Ranking uses one query and at most 32 explicitly supplied passages. Responses
are limited to 2 MiB and vectors to 4,096 dimensions. Vector counts, dimensions,
numeric types, finiteness, nonzero norms, model name and token-count types are
validated. Duplicate JSON keys, non-finite JSON values, malformed or oversized
responses and late completions fail closed with stable, sanitized error codes.

The default elapsed deadline is 10 seconds (configurable up to 30 seconds).
Remaining-time socket limits and deadline checks reject late results; they are
not hard process isolation against a blocking custom transport or compromised
local runtime. Transport injection is reserved for trusted in-process tests.

Vectors are normalized in memory. Ranking returns positive cosine similarities,
optionally filtered by a minimum score, with top-k 1–10 and ties in emitted
six-decimal scores ordered by original passage position. Scores are uncalibrated
similarities, not probabilities or relevance acceptance. Vectors are not cached
or stored. The selected model tag is not an immutable weight/version identity.

## Explicit synthetic exercise

After source integration and normal environment setup:

```powershell
npm.cmd run embeddings:check
```

The default command reports the opt-in requirement and makes **no HTTP request**.
It does not inspect or certify the installed server/model. No model is installed,
selected or downloaded by this feature.

An operator who already has an approved embedding-capable local model can opt
into the fixed English/Arabic synthetic exercise. Replace the example model tag
with an actual installed embedding model; it is deliberately not a recommendation:

```powershell
npm.cmd run embeddings:local -- -Model 'your-installed-embedding-model:tag'
```

Portable equivalents use `python scripts/check_local_embeddings.py` and explicit
`--run-local --model`. Only fixed synthetic text is submitted; there is no user
query/file input. One metadata request precedes the single embedding request.
The tool writes an unsigned JSON technical receipt under `backend/data/drills`
only after complete validation. It contains dimensions, counts, elapsed time,
the source hash and the requested tag, without vectors, queries, text or scores.
`completed: true` means the technical exercise completed; semantic quality and
production readiness remain explicitly false. Failed publication cannot report
success or leave a partial receipt.

No actual local model was contacted during this implementation's automated
checks. Tests use synthetic HTTP transports. No real-model or bilingual quality
acceptance follows from those tests.

## Next development and acceptance

The next source increment adds [authorized local neural search](AUTHORIZED_LOCAL_NEURAL_SEARCH.md)
with explicit operator configuration, server-reported model digest checks,
ACL-first selection/completion rechecks, admission controls, worker isolation and
scoped history. It remains disabled by default and does not enable this PC's model.
Persistent vector indexing, content/version/ACL invalidation, retention,
learned reranking and representative English/Arabic evaluation remain separate
work. The roadmap stays partial. The feature builds on integration PR #83;
merging, model setup and deployment are outside this development increment.
