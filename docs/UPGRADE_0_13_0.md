# Upgrade to 0.13.0

1. Stop every API/worker process with Ctrl+C or your process manager. Back up existing application/business databases and preserve private .env, data and backups. Read the prior encrypted backup operations guide; never overwrite active data with files from this ZIP.
2. Extract this source into a separate folder first. Review the intake guide and compare private settings. Copy application source/scripts/requirements/frontend files into your working project while keeping your private settings/data. Do not copy a virtual environment or node_modules from another machine. Neither is included here.
3. From `C:\nexus-ai-control`, run `scripts\start.cmd`. It installs Python dependencies (including pinned pypdfium2 and Pillow), builds the frontend, preserves initialized accounts, applies additive schema 8 migration and starts API plus worker. Native Windows extraction/resource acceptance has not been performed in this release; verify on a disposable copy before using sensitive sources.
4. Use the newly printed URL. Hard-refresh browser assets. Existing passwords are not reset. Do not run a seed reset or delete the database to fix sign-in.
5. Open Document library. Test a small approved DOCX or searchable PDF through queue → extracted review → publish → search. Confirm role denial with a separate user. OCR remains disabled unless separately provisioned and enabled; follow DOCUMENT_INTAKE_0_13_0.md.
6. After verification, retain your pre-upgrade backup under your retention policy. Do not start older code against the upgraded database. For rollback, stop all writers and restore the separately tested pre-upgrade source and backup together to an isolated destination first. New schema-8 intake records are not readable by older source.

Schema 8 adds the ingestion_jobs table. Existing schema-7 documents, actions, users and approvals are preserved. Migration is idempotent. Production configurations retain the existing production-mode validation and require operator-managed identities/secrets/resources.

For a separated intake worker, set NEXUS_INGESTION_IN_ACTION_WORKER=0 on business workers and deploy `python -m nexus.ingestion_worker` with the same database and reviewed resource/network policies. Keep this worker running for processing and expired-buffer cleanup.

Changes: backend/requirements.txt; schema/migration; intake API/extractor/worker; action-worker wiring; document provenance; UI queue/styles/request validation; tests, docs, demo fixtures and built frontend. The HTTP adapter, encrypted backups and metric controls from 0.12 remain available. This upgrade does not provision Tesseract, Arabic language data, cloud infrastructure or external acceptance services.
