# Check a downloaded workflow report offline

After this source is integrated, the existing `npm.cmd run evidence:verify`
command accepts both supplier-check and durable-run evidence, format version 1.
It uses only Python's standard library and needs no running app, database,
credentials, customer endpoint or network. It does not load `.env` or alter any
workflow/action. No dependency installation, migration or app restart is added.

First download the JSON through **Review run evidence** in Durable execution.
From the updated project root, this PowerShell example selects the most recent
matching run report in Downloads, displays its path, and checks it:

```powershell
$runReport = Get-ChildItem -LiteralPath "$env:USERPROFILE\Downloads" -Filter 'nexus-run-evidence-*.json' -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $runReport) { throw 'Download a run evidence JSON file first.' }
$runReport.FullName
npm.cmd run evidence:verify -- $runReport.FullName
```

For a different saved file, pass its actual full path to the same command.
Optional `--workspace`, `--account` and `--environment` checks on the portable
Python entry point compare the file's scope labels with expected values. The
account is the report exporter, which may differ from the run author; those
labels are not authentication. The historical portable entry-point name is
retained for script compatibility:

```text
python scripts/verify_supplier_evidence.py <actual-report.json>
```

The Windows wrapper also supports `-Workspace`, `-Account` and `-Environment`.
Run it directly for those named PowerShell parameters. Existing supplier-report
output fields and invocation remain unchanged.

## What a valid result means

Exit 0 and `file_integrity: valid` mean the supported file's structure,
internal recorded relationships and SHA-256 checksum agree. Exit 2 reports an
invalid/unsupported file. Workflow summaries identify the file format and run,
recorded status, step/action counts, recorded verified/unverified action counts,
condition outcomes and skipped-step count. They do not print request contents,
review notes or raw file text. Pending and unknown outcomes remain recorded as
such; the command never retries or reconciles them.

The check validates up to 12 ordered steps, saved schedule timestamps, approval
shapes, verified-action flags, fixed condition destinations, prior-source
references and skip origins. Unexpected fields, inconsistent outcomes and signed
claims are rejected. The shared parser retains its 512 KiB bound, nesting limit,
duplicate-key rejection and finite safe integer rules. Standard UTF-8/BOM and
the existing sorted ASCII JSON canonicalization are supported.

This is **format and checksum verification only**. Anyone who edits an unsigned
file can recompute its checksum. `authenticated_signature` remains false. The
file omits the original workflow, source envelopes, supplier values/allowlist,
reviewer identities and complete audit history; the offline command cannot
independently establish the business predicate, permissions, actual effects or
current server state. A recorded verified action remains a claim in the file.
Scope flags, schema/release labels, a successful file check and workflow success
are not customer acceptance, a functioning restored application or production
readiness. Retain the original and handle operational identifiers under your
pilot access policy.

Development checks use actual exports from disposable synthetic runs, including
pending approvals, uncertain purchases, scheduled starts and conditional skips.
The standalone check also runs with third-party packages, database modules and
networking unavailable and an invalid local `.env`. Formal pilot/customer and
deployment acceptance remain separate work.
