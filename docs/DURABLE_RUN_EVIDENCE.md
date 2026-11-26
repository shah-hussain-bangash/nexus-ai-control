# Durable run evidence snapshots

This development increment adds **Review run evidence** to the durable execution
dashboard for signed-in users with the existing `export` permission (owner,
security and auditor). It is available for queued, waiting, uncertain and
terminal runs. Select a run, review the recorded snapshot and choose **Download
run evidence JSON**. The dashboard checks the checksum and binds the response to
the current account, workspace, environment and selected run before download.

`GET /v1/agent-runs/{id}/evidence` uses the normal human session, environment
membership and export permission. Other workspaces/environments cannot retrieve
the run. A single database statement captures the run, up to 12 ordered steps,
their linked actions, business approvals and recorded application schema. The
response is marked `Cache-Control: no-store` and does not create an audit event,
change records or call a worker/connector. It never retries or reconciles an
action.

The allowlisted JSON contains the release/schema, export time, scope, run status
and version, cursor, immutable definition fingerprint, recovery/cancellation
state, step kinds/statuses, recorded independent checkpoint decisions and linked
action verification/approval states. Connector mode comes from the recorded
workflow destination, not the operator's current configuration. Pending and
unknown actions remain unresolved even if a workflow checkpoint was approved.
The export validates definition fingerprints, step ordering, action ownership,
request binding and verified result consistency. Missing/inconsistent records
return a generic conflict instead of a report claiming valid evidence.

Names, step labels, request arguments, supplier references, purchase amounts and
purposes, external references, review notes, credentials, raw connector responses
and audit history are excluded. Identifiers and fingerprints remain operational
metadata: store/share downloaded files according to the pilot's access policy.

The envelope uses `nexus-durable-run-evidence`, format version 1, with SHA-256 of
the payload serialized as sorted, compact ASCII JSON. The checksum detects
accidental changes; it is **not a signature or proof of authenticity**. Export
time identifies when records were read, not a deployment or source revision
attestation. A file does not establish current server state, complete audit
history, customer acceptance or production readiness. The existing
`evidence:verify` command supports supplier-check evidence only; do not use it to
validate this different format.

No database migration or running-app change is required by this source change.
It does not add autonomous model planning, workflow graphs/parallelism,
scheduling, compensation, an immutable archive or authenticated evidence.
Customer workflow and deployment acceptance remain separate future work.

Development checks are in `backend/tests/test_durable_evidence.py` and
`frontend/tests/runEvidence.test.ts`. They use disposable fixtures and cover
privacy/read-only export, export permissions and scope, pending approvals,
uncertain/cancelled/reconciled effects, inconsistent records and browser checksum
and account binding. These checks are not formal pilot acceptance.
