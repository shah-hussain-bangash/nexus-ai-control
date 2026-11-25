# Document-backed model answers

The Model gateway inference console can include authorized indexed Document
library excerpts when **Include authorized source excerpts** is selected. The
checkbox is off by default. This applies to existing local Ollama and hosted
provider routes; it does not enable or select a provider automatically. Excerpts
are transmitted to the chosen model, so review the route before sending approved
information.

## Staging sequence

1. Add a small synthetic UTF-8 source through Document library, or review and
   publish an extracted file using the existing intake workflow.
2. Confirm its indexed status and intended role/user access. Document-library
   authorization and the selected workspace/environment apply.
3. In Model gateway select a checked model, enter a question matching the source
   and select the source-excerpt checkbox.
4. Send once. A document-backed result records the source document ID, version,
   chunk, exact excerpt and hash. The UI displays its title, version and chunk
   next to the answer. Citation numbers correspond to the supplied excerpts.

Selection uses existing ACL-first lexical document search and up to five matched
excerpts. When no indexed document matches, existing saved design-source retrieval
remains a fallback. The ranking corpora are not mixed or assigned comparable
scores. This is not neural retrieval, reranking or an automatic factuality judge.
With no matching source the existing inference path still runs without citations;
a missing citation does not establish grounding or an appropriate refusal. Review
generated text against its actual source.

## Source changes and saved answers

Current document access, indexed status, version and chunk hash/text are checked
again before admission. A changed source snapshot rejects preparation before a
provider call or budget reservation. Input guardrails still inspect original
question/evidence before redaction. Provider outcomes are not retried automatically.

After model execution, accounting is settled first. Current source checks then
apply before delivery. If a source became inaccessible, deleted, replaced or
failed integrity checks, the **entire answer and all source excerpts are
withheld**. Removing only citations would still expose facts in the answer.
Usage totals and the stored historical result are preserved; this is read-time
filtering, not a rewrite of evidence or a refund.

The same filtering applies to runtime summaries, fresh paginated history reads,
same-intent replay and recovery. It uses the current viewer's document
access, including when another workspace member reads shared history. History
helper callers without a viewer fail closed for document-backed answers. Existing
legacy results without document-library provenance are unchanged.

Client exports serialize the history page already loaded in the browser; refresh
that page to apply current server checks before exporting. Revocation cannot
unsend evidence already delivered to a model, erase a response
already displayed in another browser tab or revoke a previously downloaded file.
Filtering happens on subsequent server reads. Local Ollama avoids a hosted API for
local weights; hosted routing still follows its separately enabled controls.
No schema migration, dependency change, customer acceptance or production claim
is introduced by this bridge.
