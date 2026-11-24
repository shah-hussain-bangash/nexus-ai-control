# Offline recovery evidence consistency checker

`scripts/verify_recovery_evidence.py` checks a provided `nexus-disposable-recovery-evidence-pack` version-2 ZIP. It uses only Python's standard library. It does not import NEXUS, load `.env`, open an application database, execute bundled scripts, extract ZIP entries, contact a server, or modify the input. It is a reviewer utility for an existing evidence pack, not a backup/restore command or a generator of that pack. Ordinary `test:recovery` JSON reports and encrypted database archives are different input formats and are not accepted here.

From the project root, after your review workflow assigns an existing archive and independently obtained expected values:

```powershell
python scripts/verify_recovery_evidence.py "$nexusEvidenceArchive" --expected-sha256 "$nexusExpectedArchiveSha256" --expected-revision "$nexusExpectedRevision"
```

The three variables are inputs you supply, not defaults. The optional hash pins the archive bytes being reviewed, and the optional revision pins the recorded source revision. Omitting either leaves that external comparison unperformed; internal checks still run. A hash obtained from the same untrusted source as the ZIP does not independently authenticate it.

Success exits 0 and prints `verification: consistent`, `byte_integrity_valid: true`, `recorded_results_consistent: true`, the recorded revision/schema, nine verified stages and the declared skipped-check count. Invalid evidence exits 1 with a fixed `error_code`; it does not print submitted record contents or driver errors. Successful output retains `authenticated_signature: false`, `bundle_scripts_executed: false` and `application_or_database_opened: false`; invalid output retains `authenticated_signature: false`.

The supported pack contract records these separate rehearsals: functioning restored API; interrupted copy/retry; synthetic schema-marker compatibility; snapshot isolation; actual prior-revision schema upgrade; migration rollback; abrupt owned-process exit; committed-WAL recovery; and rejection of invalid declared relationships. The checker compares index/receipt/artifact/script hashes, source/schema fields, fixed recorded API outcomes, JUnit counts and declared skips. Test counts overlap across stages and must not be presented as unique aggregate coverage.

Required proof fields must be present and true. Empty rollback, fresh-process or file-validity dictionaries cannot prove success. Relationship scenarios must cover their three distinct cases, cleanup claims must agree, and the index must acknowledge overlapping tests. This corrects a reproduced prototype weakness where recomputing hashes around incomplete proof could still yield a consistency pass. It also rejects an auditor-write result changed from the expected 403 to 200, even when hashes are recomputed.

The reader caps compressed input at 16 MiB, entries at 128, each uncompressed member at 2 MiB and total uncompressed members at 16 MiB. It rejects duplicate/case-alias names, absolute or parent paths, Windows separators in ZIP names, symlinks, encrypted members, unsupported compression, ambiguous JSON and XML DTD/entity declarations. Early receipts with Windows separators in relative artifact references are normalized without relaxing ZIP-entry rules. It reads the same bounded archive bytes for optional hash verification and parsing.

These are consistency checks, not authenticated execution evidence. A fully fabricated but internally consistent unsigned pack cannot be distinguished from real execution by checksums alone. The checker does not prove producer identity, current server state, live deployment recovery, historical runtime-image behavior, power-loss durability, concurrent-writer snapshot consistency, PostgreSQL/customer acceptance or production RPO/RTO. Unit fixtures deliberately contain invented metadata and non-executable recovery-script placeholders; passing those parser tests is not a restore demonstration. Actual recovery reports remain separate evidence.

Focused validation: `python -m pytest backend/tests/test_recovery_evidence_verifier.py`. No new dependency, database schema, server setting, secret, scheduled task or runtime route is introduced.
