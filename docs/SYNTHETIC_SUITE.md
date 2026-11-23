# Run all disposable synthetic checks

From the project root in Cursor's PowerShell terminal:

```powershell
npm.cmd run test:synthetic
```

Your app can stay open. Runtime dependencies must already be installed; the Windows wrapper uses the project's `.venv`. No server URL, account password, backup key or existing report path is required. The portable command is `python scripts/run_synthetic_suite.py`; optional `--output-dir` chooses the combined report directory. Pytest is not required.

The command runs the existing drills sequentially in eight separate Python processes, each with its own newly created output/working directory inside a disposable workspace. It uses the current interpreter and fixed project entry scripts with argument lists, without a shell. The parent never loads operator Settings or `.env`; the child drills continue to use their explicit disposable settings and synthetic fixtures. The knowledge entry uses the retrieval drill's existing hybrid option. No active database is restored or overwritten, and no customer system or live model provider is contacted.

| Drill | Existing individual command | Current checks |
| --- | --- | ---: |
| Connector | `npm.cmd run test:connector` | 15 |
| Retrieval | `npm.cmd run test:retrieval` | 18 |
| Knowledge | `npm.cmd run test:knowledge` | 36 |
| Ingestion | `npm.cmd run test:ingestion` | 25 |
| Agents | `npm.cmd run test:agents` | 24 |
| Inference | `npm.cmd run test:inference` | 27 |
| Backup | `npm.cmd run test:backup` | 34 |
| Recovery | `npm.cmd run test:recovery` | 39 |
| **Total** | | **218** |

Each child has a 60-second timeout, including process startup. If a child fails, times out or cannot start, its row fails and the remaining drills continue. A successful child must also provide consistent summary/report metadata for this release/schema, a matching drill format/version, a positive check count and uniquely identified passing steps. Reports must be regular files directly inside that child's directory, with a 256 KiB size limit; symbolic report paths and paths outside it are rejected before reading report contents. The summary is limited to 64 KiB of text for validation. These checks validate local results produced by the fixed project entry scripts.

Child stdout/stderr are captured; private errors, child record contents, report paths and arbitrary extra fields are not copied into the aggregate. Only fixed drill identifiers, pass flags, validated counts and fixed statuses are retained. Status values are `passed`, `drill_failed`, `timed_out`, `could_not_run`, `invalid_report` and `not_run`. A failure's `checks_passed` is zero; totals include checks only from fully validated passing drills. For detailed diagnosis, rerun the corresponding individual command in the table. Interruption aborts the suite rather than certifying a completed run.

Success prints `"passed": true`, `"drills_passed": 8`, currently `"checks_passed": 218` and `"source_status": "unchanged"`, plus a unique `synthetic-suite-` report path under ignored `backend/data/drills`. Exit 0 indicates success; reported failures return 1. Format `nexus-synthetic-suite`, version 2, includes release/schema metadata, eight safe result rows and source fingerprints. Counts are taken from the validated child reports, so future drill changes may change the total. Older version-1 reports remain unchanged and contain no source fingerprints.

Before starting children and after they finish, the runner fingerprints the recursive Python source under `backend/nexus`, excluding `__pycache__`, plus the suite entry script and its fixed child entry scripts. Scope is `nexus-python-and-drill-entries-v1`. It hashes sorted relative filenames, byte lengths and content hashes with SHA-256; each report stores only the combined hash and file count at each checkpoint, without absolute source paths, filenames or contents. Fingerprints use exact bytes, so line-ending changes also change the result. Identical source bytes in another project folder produce the same fingerprint. Git is not required. Inventory limits are 4,096 files and 32 MiB of content; missing, unreadable or redirected source files/directories fail source validation.

`source_status: "changed"` means the two fingerprints differ. `"unavailable"` means a checkpoint could not be read; a failed initial checkpoint leaves the drills `not_run`. Either status prevents an overall pass even if all executed drills passed. Finish saving your edits and rerun the command. `drills_passed` and `checks_passed` still describe validated child results, so always check the overall `passed` flag too.

The fingerprint covers those Python files only. It excludes `.env`, account/database contents, existing reports, caches, documentation, frontend code, shell wrappers, dependency manifests and installed dependencies. Matching checkpoints do not prove that files stayed unchanged between reads: a change reverted before the final checkpoint can escape detection. This is local diagnostic provenance, not an immutable code snapshot, a Git commit identity or authenticated evidence of the instructions executed.

The combined report is written only after child reports, databases, archives and temporary plaintext fixtures have been removed during normal workspace cleanup. A report-write or cleanup error cannot report success; an operating-system cleanup failure may leave disposable files for protected local review. Cleanup is not secure erasure or memory zeroization. Running the suite does not rewrite or delete existing drill reports.

This combined result inherits each drill's limits. It is an unsigned local synthetic summary, not authentication of source, report or server state. It does not replace the full pytest/CI suites, customer/provider acceptance, OCR or generated-answer quality evaluation, deployment/PostgreSQL recovery, measured RPO/RTO or production acceptance. `active_database_restored`, `customer_acceptance` and `production_ready` remain false.
