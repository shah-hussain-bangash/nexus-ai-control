# Upgrade to 0.6.0 in staging

If you want to update only after complete production acceptance, keep the current Windows installation unchanged. This package is for source review and staging validation; it is not a full production sign-off.

For a staging upgrade: stop API/worker, privately back up the complete previous source, environment configuration and all data, then extract into a separate folder. Preserve your private configuration and complete backend/data paths. Do not copy old .venv, node_modules or built frontend files. Windows: run scripts\start.cmd from the new root. Linux/macOS: bash scripts/start.sh. Initialization migrates forward to schema 5 and does not reset users or passwords.

New table: readiness_evidence. Rate/concurrency controls use existing organization/inference tables; no inference records are deleted. Live provider execution remains OFF by default. Existing explicit server enablement is preserved if you copy your private configuration, so review it before staging tests. The standalone read-only preview cannot perform real mutations.

New settings: NEXUS_INFERENCE_REQUESTS_PER_MINUTE=30 and NEXUS_INFERENCE_MAX_INFLIGHT=4. Limits are per organization; pending concurrency uses a 300-second window. Coordinate identical settings across workers/replicas. Run the external PostgreSQL concurrency suite before deployment.

Rollback requires restoring the matching pre-upgrade source, configuration and full database together. Older source refuses schema 5. Do not remove markers or tables to force a rollback.

Native Windows 0.6.0 was not exercised here. Tests/builds ran on Linux. See VERIFICATION.json and the acceptance report.
