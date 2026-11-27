# Optional signed audit metadata

Audit explorer includes **Signed audit metadata snapshots** for users with
`export` permission. Signing is disabled by default. It is separate from existing
unsigned JSON downloads and supplier/workflow checksum verifiers.

An operator can configure `NEXUS_AUDIT_SIGNING_KEY_FILE` to an existing dedicated
Ed25519 PKCS8 PEM private-key file. No signing key is generated, uploaded or changed
by the dashboard. The file must be a regular, nonsymlink file, at most 4096 bytes.
Encrypted PEM and other key types are unsupported. Protect the key with operating
system permissions restricting reads to the service identity and approved key
custodians. Keep it outside the repository, backups shared with reviewers, source
archives and web-served directories. Do not use a session secret or backup key.
This feature does not provide a key vault or hardware-backed key custody.

The status API discloses only availability, the public key and its SHA-256
fingerprint over the raw 32-byte Ed25519 public key. A configured but unreadable or
unsupported key disables new snapshots with a generic error; private paths,
contents and parsing diagnostics are not returned. Existing downloads do not
require the private key to remain available.

Before accepting evidence, establish trust in the public key through a separate
approved operator channel. Downloading a key together with evidence is insufficient
to establish that trust. Retain trusted public keys and their approved identities
across rotation. Revocation and custody procedures are operator responsibilities.

## Create and download

1. Open Audit explorer in the intended workspace/environment.
2. Confirm the configured fingerprint against the approved signing identity.
3. Choose 1–1000 latest event metadata records and enter a visible change note.
4. Create a snapshot, then download it from the recent snapshots list.
5. Verify the file offline against a separately trusted public key and expected
   workspace and environment.

The signed snapshot contains event IDs, event types, actor IDs, optional action
and trace IDs, and integer Unix timestamps in **microseconds** (`created_at_us`).
It excludes audit details, business arguments, prompts, source contents and
credentials. Treat metadata and operator notes as potentially sensitive. The list
is oldest first within the selected latest records; the `truncated` field states
whether more records existed at sampling time. Snapshot creation's own audit
event is recorded after sampling, so it is not part of that snapshot.

Each envelope uses format `nexus-audit-metadata-v1`, algorithm `Ed25519`, a key
fingerprint and a base64 signature. The signature covers the fixed domain prefix
`NEXUS-AUDIT-METADATA-V1` followed by a zero byte and canonical ASCII JSON of the
payload (sorted keys, compact separators, escaped non-ASCII, no nonfinite numbers).
Integer microseconds preserve the signed payload through browser JSON downloads.
The offline verifier rejects extra fields, duplicate keys, mismatched scopes,
unsupported algorithms, malformed records and files larger than 1 MiB.

## Offline verification

From `backend`, using the project's Python environment:

```powershell
python -m nexus.audit_signature --evidence 'C:\Evidence\signed-audit.json' --public-key 'C:\TrustedKeys\audit.pub.pem' --workspace northstar --environment staging
```

Replace those example paths with existing files. The verifier reads no runtime
settings, database, private key or network resource. Success returns
`authenticated_signature: true` and exit status 0. Invalid input returns a generic
failure and exit status 1; no evidence contents or file paths are printed.

## APIs and boundaries

- `GET /v1/signed-audit-evidence`: status/public key and latest 20 own receipts.
- `POST /v1/signed-audit-evidence`: CSRF-protected export with `limit`, `note`,
  `expected_key_id` and `Idempotency-Key`. A changed key identity requires reload.
- `POST /v1/signed-audit-evidence/recover`: own receipt lookup using `{ "key":
  "..." }`, with CSRF. It creates no new snapshot and never signs again.
- `GET /v1/signed-audit-evidence/{id}`: own unexpired snapshot, scoped to the
  current authorized workspace/environment, even after key rotation or disablement.

Original intent retries return the original receipt. Changed bodies with the same
key fail. Browser recovery stores only the key/hash/timing in an account/environment
namespace. New writes serialize per workspace and are capped at 100 snapshots per
environment, each at most 1 MiB. Downloads expire after seven days. Expiry is access
control, **not automatic deletion**; no retention job or destructive cleanup is
introduced. At capacity new writes fail and existing evidence is preserved. Uses
existing schema 12 storage; no migration is added.

A valid signature establishes possession of the trusted private key when this
snapshot was signed. It does not establish audit-log completeness, authenticity of
historical database contents, pre-export immutability, independent timestamping,
current server state, off-host archival, legal retention compliance or production
readiness. A compromised signing service/key can sign misleading snapshots.
External trust establishment, custody, revocation, immutable archival and retention
remain separate work. No live key is configured or live deployment changed by this
development increment.
