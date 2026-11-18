# Document lifecycle and retrieval checks — 0.11.0

Use the real local app from scripts/start.cmd; the isolated demo harness has read snapshots only. Keep the API/worker terminal open. Use synthetic data until deployment security/retention is accepted.

## Check a source and replace it safely

1. Sign in as owner@nexus.local with your own saved password. Open Document library, upload a UTF-8 .txt file containing `Synthetic purchasing approval is required above USD 5,000.` Give it a clear title.
2. Search `purchasing approval`. Select **Verify citation and inspect**. Confirm the current source version/hash/content and citation confirmation.
3. In source detail select **Replace content**. Choose a new UTF-8 file containing `Synthetic procurement review is required above USD 5,000.` Review its title/language and enter a meaningful content update note. Submit **Replace and reindex document** once.
4. Confirm the source version increased, permissions stayed unchanged, and a new search finds the replacement content. Old citation references now fail as stale. This update replaces current content; it does not retain readable historic content or provide rollback.
5. If submission times out, use **Recover pending update** in source detail. Do not clear the pending key and submit a different update blindly. A stale-version error means you must refresh, review the current source and reopen replacement with its current version.

## Create measurable retrieval evidence

1. Scroll to **Retrieval quality checks → New retrieval check**.
2. Name the suite `Synthetic procurement evidence`. Set top ranked chunks to 5.
3. Case 1: query `procurement review`; expectation **Retrieve expected sources**; select your new source. Select up to five expected sources per positive case.
4. Add Case 2: query `unmatchablewordxyz`; expectation **Return no results**. This is a simple deterministic negative example, not a security certification.
5. Select **Run and save check** once. Inspect cases passed, mean document recall@k, mean reciprocal rank, source citations and corpus fingerprint. A positive case passes only if all expected documents appear in the top k chunks.
6. Replace a source or change the readable corpus, then reopen the saved check. It should show **Corpus changed — rerun**. Use **Review and rerun suite** to create new evidence after reviewing the cases. Historic scores do not update automatically.
7. If the original operator loses access to a referenced source, saved detail is blocked. Author/owner administrators can remove obsolete active evidence with a note. Removing a check does not delete its source document; backup/audit retention remains separate.

Each suite supports 1–20 cases and top 1–10 chunks; each organization retains up to 100 check records. Test definitions/results are private backend data. Only the author or owner/security policy administration can read a saved suite. No source excerpts are retained in results; IDs, citations, actor, metrics and fingerprints are retained. Use **Recover pending check** after uncertain creation. SessionStorage holds only key/fingerprint/time, never query text or file content.

These are lexical retrieval checks. OCR, vector/semantic retrieval and LLM answer quality are separate remaining capabilities. A 100% score on your chosen cases does not establish production readiness.
