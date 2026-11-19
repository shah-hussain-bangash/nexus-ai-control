# Phase 1: environment-scoped request recovery

Review increment based on 0.16.2/schema 9. Browser recovery keys now include the
authenticated workspace, account and environment for inference, durable runs,
document intake/replacement, queued file intake, retrieval checks and hybrid
search. This prepares those workflows for future environment selection; it does
not enable switching or change any server authorization boundary.

## Recovery behavior

- Runtime recovery namespaces move from v1 (workspace/account) to v2
  (workspace/account/environment). Document replacement also retains its document
  reference suffix. Context identifiers are encoded independently and validated.
- Earlier runtime requests could only use staging. A staging v2 lookup may read a
  valid corresponding v1 receipt, keeping its original key, fingerprint and time.
  Other environments cannot adopt it. Reading does not delete or rewrite it.
- Retrying the unchanged intent persists the same metadata under v2 before any
  request is sent. Failed storage reads/writes prevent submission. Prompts, file
  content and credentials are not copied into recovery records.
- A valid acknowledgement retires only records with that key **and** fingerprint.
  A different pending v1/v2 receipt survives, including late or repeated cleanup.
  A late pending/unknown response also cannot overwrite a different saved receipt.
  Missing or malformed recovery responses retain the receipt.
- Inference keeps pending/unknown outcomes recoverable. Its existing explicit
  same-request recheck and Start a new request controls retain their behavior;
  another pending receipt prevents starting a new request.
- Account provisioning remains on its workspace-wide v1 namespace: it is not an
  environment runtime operation. Moving between runtime environments must not
  hide an unacknowledged provisioning receipt.

The managed execution, document, inference and hybrid-search panels use keys
containing workspace/account/environment, resetting their component state if that
authenticated context changes. The session bootstrap validates this context before
displaying these panels. Missing context is not silently treated as staging.

## Limits

Storage namespaces are client isolation and recovery behavior, not authorization.
The backend remains authoritative. There is no environment selector or activation
route in this change. API context routing, all server resource/worker propagation,
root application caches/dialogs, design drafts and exported UI handoffs still need
their own context review before switching can be enabled. The complete workspace
lifecycle gate remains open.

Existing invalid/corrupt receipt data is still ignored by the defensive reader;
this change cannot reconstruct a lost or corrupted original key. Recover the
recorded server outcome rather than assuming it is safe to repeat a business
effect. Keep all old app tabs refreshed after applying the source update.

## Validation and activation

- 66 frontend tests pass. Coverage includes environment/account/workspace/kind
  isolation, legacy staging adoption, resource suffixes, safe key reuse after a
  lost response, malformed acknowledgements, storage failures, independent pending
  receipts, late cleanup and workspace-wide provisioning.
- Both the app and synthetic preview production builds pass on Windows.
- Disposable browser check: one already accepted run with a v1 staging receipt
  was recovered by its original key; its receipt was retired and the database
  still contained exactly one run. No worker or external connector ran.
- Backend source and schemas are unchanged. Full backend, PostgreSQL, frontend
  and policy checks run in GitHub CI on the candidate.

Review the pull request before source activation. Rebuild and restart normally
after approval; no database migration, account change or live assignment change
is required. Existing browser staging receipts are kept recoverable through the
compatibility reader rather than discarded during the update.
