# Read-only identical indexed-text review

Document library provides **Review identical text** below an inspected source.
The preview lists other currently readable document records with exactly the same
stored indexed text. Opening a listed record uses the normal document API and
checks current access again. A refresh recomputes the preview; it is not a saved
attestation of continuing access or content equality.

## Supported API

`GET /v1/documents/{id}/copies?expected_version=1&offset=0&limit=20`

The normal human session and current workspace/environment binding are required.
The displayed source version is mandatory. Missing or unreadable sources return
404; changed versions return 409. A source whose indexed-text digest is
inconsistent also fails closed with 409. Query limits are 1–50, offsets 0–10000.

One database statement reads the source and matching-hash candidates, including
their current versions and reader permissions. The source digest is verified;
candidates must also have identical text. Hash equality alone is insufficient.
Reader checks happen before comparison results are counted and paginated.
The response includes actor/workspace/environment scope, source ID/version/hash,
minimal matching-record metadata, visible count, and next offset. No unreadable
counts, original file content, excerpts or reader lists are returned. Responses
use `Cache-Control: no-store`.

The existing admission limit is 200 active documents per workspace/environment.
This is a bounded library review, not scalable corpus deduplication. It performs
no writes, merges, deletions, reindexing, or model/provider calls. Existing source
versions, citations and access controls are preserved. No schema upgrade is needed.

## Meaning and limits

- Equality concerns the full **stored indexed text**, after existing intake or
  reviewed extraction, not original binary files, titles, filenames or metadata.
- Whitespace differences, Unicode variants, near copies, OCR quality, paraphrases
  and semantic similarity are not normalized or compared by this feature.
- Equal records do not establish independent evidence, provenance, authenticity,
  ownership or permission to delete either source.
- The preview is a point-in-time read. Access or content can change afterward;
  refresh before making a separate document-management decision.
- The browser clears previews when the source or session context changes and
  ignores superseded requests. It binds replies to the captured account,
  workspace, environment, source version and page.

## Verification

`backend/tests/test_document_copies.py` exercises the normal API on disposable
databases: exact equality, near-copy exclusion, ACL-first pagination/counts,
revocation, tenant/environment isolation, deleted/replaced sources, inconsistent
hashes, version conflicts, query bounds, authentication, and unchanged audit,
chunks and citation behavior. Frontend tests reject foreign-scope, stale-version
and inconsistent-page replies. These checks do not constitute customer or
production acceptance.
