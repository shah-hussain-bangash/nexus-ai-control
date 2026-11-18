# Upgrade 0.4.0 → 0.5.0

This is a production-engineering build, not final production acceptance. If your requirement is to update only after the complete enterprise platform is accepted, keep the current installation running and retain this package for staging review.

For staging installation: stop API and worker; back up the entire previous project folder, environment configuration and all data; extract into a separate folder; preserve environment configuration and complete backend/data paths. Run scripts\start.cmd on Windows. The initialization migrates schema 3 to 4 by adding inference budget/call tables; existing accounts, passwords, actions and workbench records are preserved. Live inference defaults to OFF, so updating alone does not send requests or incur provider charges.

Do not copy old node_modules, .venv or frontend/dist into the new release. Follow MODEL_RUNTIME.md before enabling real calls. Existing model configurations must be checked by owner/security before use. Only owner/security may change guardrails; only owner may reconcile uncertain provider calls.

Rollback requires restoring the matching pre-upgrade source, complete database and configuration together. Older source refuses schema 4. Do not delete markers or tables to bypass this rule.

Native Windows 0.5.0 was not exercised in this environment. The user-verified launcher is retained, but the current automated verification runs on Linux/Python 3.12.
