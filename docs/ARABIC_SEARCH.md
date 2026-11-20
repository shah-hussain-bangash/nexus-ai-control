# Arabic text matching in local search

Document-library search, local hybrid retrieval and knowledge workbench previews share the `arabic-search-v1` search tokenizer. Queries such as **ادارة المشتريات** can now match original text such as **إِدَارَة المَشْتَرَيَات**. Both the query and the authorized source text receive the same normalization during ranking.

To try it, upload your UTF-8 Arabic or bilingual source in Document library, then search for its words without vowel marks. In Knowledge & RAG, use Search evidence for local hybrid results. Inspect the returned original excerpt and citation; normalized matches may include spelling variants.

The tokenizer applies Unicode canonical composition, expands Arabic presentation-form letters/ligatures, removes Arabic combining vowel/recitation marks and tatweel, and folds أ/إ/آ/ٱ to ا, ى/ی to ي, and ک to ك. English case folding, numbers and underscore identifiers remain supported. It preserves unrelated letters such as ة versus ه and ؤ/ئ, and does not strip Latin accents, translate, stem, remove the Arabic definite article or supply OCR. This broadens text matching; it is not a benchmark of Arabic semantic relevance or generated-answer quality.

Only temporary search tokens are normalized. Source text, stored chunks, document versions, original content hashes, excerpts and citation identifiers are preserved. Existing indexed documents need no migration or reupload because current ranking tokenizes their original chunks on demand. Current workspace, environment, author/reader permissions, source-version checks, deletion filtering, corpus limits and worker deadlines still apply before/after ranking. No provider call or customer connector is introduced.

New lexical regression results and hybrid receipts record the tokenizer version. A saved regression from an older or unversioned method is stale and must be rerun under a new intent key, even when the source corpus is unchanged. Replaying its existing key still returns the original historical record. Hybrid history preserves saved scores and adds `normalization_current: false` and an earlier-method notice for older receipts; it does not relabel their scores as newly computed. Old source-access and version checks still apply to historical results.

No schema change, stored-document rewrite, automatic search rerun or deployment acceptance is performed. Broader bilingual relevance evaluation, Arabic morphology, translation, learned reranking and answer grounding remain separate work.
