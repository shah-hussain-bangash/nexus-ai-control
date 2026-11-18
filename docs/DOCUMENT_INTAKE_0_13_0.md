# Reviewed file intake — 0.13.0

## Use the working dashboard

1. Start the authenticated application with `scripts\start.cmd` on Windows. Sign in as an existing owner or engineer with operate permission.
2. Open **Document library → Extract. Review. Publish. → Queue a file**. Quick UTF-8 text upload remains a separate option.
3. Select a plain-filename PDF, DOCX, PNG or JPEG, set its title/language and reader roles. No extra role grants are selected by default. The source author and owner/security administrators retain access. Existing explicit-user ACLs are supported by the API; the new upload form exposes role selection.
4. Queue the immutable file. The real worker moves it through queued → processing → awaiting review or failed. Reloading/restarting preserves jobs. The same-tab recovery button looks up an unacknowledged request using its scoped idempotency key; browser storage retains only recovery metadata, not file bytes/text.
5. Select the pending intake. Compare the extracted text with your local original file. Inspect extraction method, original fingerprint and declared readers. Parsing/OCR can omit or alter text.
6. Choose **Review and publish**, enter a meaningful review note, and check the source-comparison attestation. The expected version is pinned; stale controls are rejected. This is an authorized operator publication review, not a new independent second-person policy approval.
7. Select **Inspect published source**. Search and citations now use the existing authorized text/chunk path. The original filename/hash/byte count and extraction method are linked to the published version. Subsequent source/ACL revision marks whether that version still matches.

PDF/DOCX intake and publication are real API/worker operations. The demo-preview harness shows backend-generated synthetic fixtures and blocks runtime mutations; it is not a substitute for these steps.

## Supported boundaries

| Control | Current implementation |
|---|---|
| Original file | 1 byte–1 MiB; PDF/DOCX/PNG/JPG/JPEG; extension/signature checks |
| PDF | 1–12 pages; native text extraction; blank pages can use configured OCR |
| Images | PNG/JPEG, at most 8 million pixels; normalized before OCR |
| Extracted text | At most 32 KiB UTF-8; no silent truncation |
| DOCX | Main body paragraphs only; at most 200 ZIP entries; bounded main XML and compression ratio; macro/encryption/DTD/entity rejection |
| Parser | Separate subprocess; operator wall timeout 5–60 seconds, default 30; POSIX memory/CPU/file limits |
| Review | 24-hour window; expired publication is blocked even before cleanup |
| Capacity per organization | 10 active jobs, 50 nonarchived retained jobs, 500 lifetime intake receipts |
| Retry | Explicit, at most 3 attempts per original job; original file/grants stay immutable |
| Scope | Author and policy administrators can inspect private intake in their organization; publication applies document ACLs |

Mixed PDFs with sparse searchable text can need **Force OCR**; auto mode OCRs pages without extractable text. DOCX forced OCR is unsupported. This is plain-text extraction, not table recognition, page-layout preservation, bounding-box citations, handwriting-quality certification or enterprise source synchronization. Existing citations identify current text chunks, not original PDF coordinates. No vector/hybrid search, model answer generation or semantic duplicate detection was added.

## Configure OCR deliberately

OCR is off by default. Install a trusted Tesseract package and the required language data outside this source ZIP. Verify the executable and installed languages as the worker user:

```powershell
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --version
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs
```

Example private backend environment configuration, after verifying those paths/data:

```dotenv
NEXUS_INGESTION_OCR_ENABLED=1
NEXUS_TESSERACT_COMMAND=C:\Program Files\Tesseract-OCR\tesseract.exe
NEXUS_INGESTION_OCR_LANGUAGES=eng
NEXUS_INGESTION_TIMEOUT_SECONDS=30
```

English uses eng; Arabic requires ara; Bilingual requires eng+ara. Configure `NEXUS_INGESTION_OCR_LANGUAGES=eng+ara` only after both are installed. There is no fallback from Arabic to English. The capabilities endpoint describes configured languages; it does not certify installed language data. Missing data fails the job. Do not put quotes inside the executable path value; the process passes it as one argument. If configuration comes from your process manager, use its normal escaping rules. Restart the relevant workers after changes.

Real English image OCR and scanned-PDF OCR passed in the Linux test environment. Only eng/osd data were present. Arabic missing-language rejection was tested; Arabic extraction quality and native Windows execution were not accepted.

## Worker separation and recovery

The normal starter's execution worker processes one intake per loop by default. A parser can occupy that loop until its bounded timeout. For production separation, set `NEXUS_INGESTION_IN_ACTION_WORKER=0` on business execution workers and run a separately constrained intake worker with the same database/configuration:

```powershell
cd C:\nexus-ai-control\backend
..\.venv\Scripts\python.exe -m nexus.ingestion_worker
```

The separate process has no API endpoint and does not migrate an uninitialized database; initialize/migrate with the application first. Deploy it under a process manager with reviewed CPU/memory, filesystem and network controls. The parser receives a sanitized environment without NEXUS credentials. It does not run source instructions or use a model/network client, but this is resource containment, **not a complete OS sandbox or malware scanner**. Windows needs deployment memory controls; native Windows resource/timeout behavior remains to be verified. Allowlist approved source origins and complete parser/dependency security review before untrusted enterprise ingestion.

A processing lease expires after 90 seconds. Interrupted work becomes an explicit failed job for review/retry; there is no blind automatic retry. Cancel/expiry changes fence late parser results so they cannot publish. Version-checked controls and idempotent publication prevent duplicate sources. A revoked/moved author cannot continue to publish.

## Retention and deletion

Original bytes and pending extracted text live in your configured database, not an external object store. They are cleared when published, cancelled, archived, or expired by a running worker. If workers are stopped, physical cleanup waits until a worker resumes; the API still rejects expired publication. Published source text follows the existing document lifecycle. The original PDF/DOCX/image is not downloadable from NEXUS after publication: retain approved originals under your organization's separate records policy.

Archive hides an intake receipt; it does not remove a published document or its hash/audit record. The 500 lifetime receipt cap does not reset on archive. Database backups may retain previous bytes. Logical deletion is not secure erasure, a legal hold system, or a complete retention/purge scheduler. Temporary files are removed during normal completion/failure; machine crashes can leave remnants. Protect database, temporary storage and backup keys appropriately.

## Technical references

- [PDFium Python API](https://pypdfium2.readthedocs.io/en/stable/python_api.html)
- [Tesseract CLI and language selection](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
- [Tesseract installation guidance](https://tesseract-ocr.github.io/tessdoc/Installation.html)
