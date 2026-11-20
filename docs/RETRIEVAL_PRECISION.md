# Document precision in saved retrieval checks

Open **Document library**, scroll to **Test what your sources return**, and open a saved check or create a **New retrieval check**. Results now show document precision overall, by query language and for each positive test case. Expand **Unlisted returned sources** to inspect saved source identifiers outside that case's expected list.

The measure uses the distinct document identifiers represented in the saved top-k returned chunks:

```text
document precision = expected returned documents / all returned documents
```

Each document counts once even when several returned chunks belong to it. A positive case with no returned documents has precision 0. Negative/no-result cases have no precision value; their existing no-result pass rate measures that expectation. Overall and language-group mean precision average positive cases only. Groups without positives show **Not applicable**.

For example, a case expecting one document can find it together with an unlisted second document. Its recall is 100% and its precision is 50%. Without an opted-in target its pass status is preserved because all expected sources were found. Optional [minimum precision targets](PRECISION_TARGETS.md) can require a chosen score in a new run. Review the unlisted source and the completeness of the expected-source list: an unlisted document may still be relevant. A small high-scoring suite does not establish bilingual relevance or generated-answer quality.

Precision is derived from the saved source identifiers after the existing author/admin, workspace, environment, source access and deletion checks. Historical reads and replay requests calculate it without rerunning retrieval, rewriting saved JSON or changing request fingerprints. Cached precision fields, if present, are recomputed from the identifier lists. Existing corpus/source/tokenizer staleness still applies. Original excerpts are not added to evidence, and source access changes can still block historical detail.

Create/detail responses add `result.mean_document_precision_at_k`. Each returned case adds `document_precision_at_k`, `retrieved_document_count`, `matched_expected_document_count` and `unexpected_document_ids`. Language groups add `mean_document_precision_at_k`. These measurement fields are derived in responses. Listing/recovery summary shapes, untargeted historical pass/fail rules and deployment readiness remain unchanged. The separate optional target request field and saved target outcome are described in [Precision targets](PRECISION_TARGETS.md).

No database migration, dependency, provider call, customer connection, automatic search or stored-document rewrite is introduced.
