# Bounded CSV document intake

Document intake accepts `.csv` in addition to PDF, DOCX and supported images.
CSV is extracted locally by the existing bounded worker process, with the same
review, publication, permissions, cancellation, expiry and receipt workflow.
It does not require OCR or a model provider.

## Supported shape and limits

- UTF-8 text, with an optional leading UTF-8 BOM. Delimiter is a comma, quote is a
  double quote and doubled quotes are supported. No dialect or encoding guessing.
- At most 1 MiB of original file bytes, 500 nonempty CSV records, 32 columns,
  2048 UTF-8 bytes per cell and 32 KiB total extracted text. Combined limits apply;
  satisfying the individual cell/row limits does not guarantee the text fits.
- All nonempty records must have the same number of columns. Empty physical
  records with no cells are ignored; empty cells inside a record are retained.
  A file containing only whitespace/empty cells has no extractable text.
- Quoted commas and quoted line breaks are supported. Invalid UTF-8, binary
  control characters, malformed quoting, ragged records and exceeded limits fail
  the whole extraction. No truncated table is offered for publication.
- Header inference is not performed. The first record is included as data.
  Numbers, leading zeroes and formula-looking values remain literal strings.
  There is no formula evaluation, spreadsheet engine, hyperlink execution,
  relational query engine or conversion/export into an executable spreadsheet.

Extracted text uses deterministic records such as `Row 1: ["sensor","value"]`.
Cell values are JSON-quoted to preserve commas, quotes, empty cells and embedded
line breaks without introducing ambiguous row boundaries. Row numbers identify
nonempty logical records, not physical source lines. Reviewers must compare this
representation with the original source before publication. The text remains
untrusted reference material for the existing retrieval/inference controls.

## Dashboard workflow

Choose a CSV file in Document intake, select its language and intended reader
roles, and queue it. CSV uses automatic text extraction; forced OCR is rejected.
The upload form displays the limits and keeps CSV/DOCX in text mode. The worker
must be running separately under the existing operator workflow.

A successful job enters Awaiting review with extracted text and fixed metadata:
`method: csv-text`, record/column counts, no page count, zero OCR pages and required
review. Original checksum/byte count remain in the intake provenance. Search does
not expose the source before publication. Reviewed publication creates one
permission-scoped document and clears the job's pending original/extracted buffers
using the existing lifecycle. A repeated publication returns the original result.

Failed jobs expose fixed error codes, not row contents or parser diagnostics:
`CSV_TEXT_ENCODING`, `CSV_MALFORMED`, `CSV_ROW_LIMIT`, `CSV_COLUMN_LIMIT`,
`CSV_COLUMN_MISMATCH`, `CSV_CELL_LIMIT`, or the existing extracted-text/file-size
and no-text codes. Pending buffers retain the existing private retry/expiry/archive
behavior; a running worker is needed to sweep expired jobs. Failed extraction
never publishes a partial document.

## APIs and compatibility

`GET /v1/ingestion-capabilities` adds `csv` and its row/column/cell, encoding and
delimiter limits. `POST /v1/ingestion-jobs` uses the existing filename, base64
content, language, ACL and idempotency fields. No new request field is required.
The filename is treated as metadata; it does not become an arbitrary filesystem
path. The worker enforces CSV encoding and parser limits after queuing.

The existing detail, control, recover and publish APIs are reused with their
current authentication, CSRF, organization/environment and author boundaries.
CSV metadata is normalized before storage; booleans masquerading as counts,
out-of-range dimensions and contradictory OCR/method metadata are rejected.
Existing extraction formats and historical request fingerprints remain unchanged.
No schema migration, dependency, environment variable or automatic worker start
is introduced.

## Focused verification

From `backend` in a development checkout:

```text
python -m pytest tests/test_csv_intake.py tests/test_ingestion.py tests/test_extraction_results.py tests/test_ingestion_completion_deadlines.py -q
```

Disposable checks cover exact bounds, English/Arabic UTF-8, BOM, quoted commas and
line breaks, leading zeroes, literal formula strings, malformed/oversized input,
metadata sanitization, real child-process extraction, review-before-search,
publication idempotency, provenance, ACLs and failed-source archival. Existing
intake/cancellation/deadline checks are retained. OCR checks may skip when the
operator's OCR engine/language data is unavailable; CSV has no OCR dependency.

This feature does not provide XLSX/TSV support, macro execution, malware scanning,
external source synchronization, OCR quality acceptance or production certification.
No actual customer file, live account, database, credentials or running app is
changed by this development increment.
