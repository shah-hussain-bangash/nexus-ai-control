# Governed supplier checks

Owners in local mode can open Workspace settings → Governed supplier check. Review the configured connector destination, choose an active granted supplier route, enter a supplier reference and a reason, then confirm the review checkbox. The screen cannot change connector configuration or submit purchases. The existing operator-configured `nexus-business-v1` adapter remains the only HTTP destination.

The business connector configuration is shared across this deployment. Selecting another local environment does not provision a separate remote sandbox or remote tenant. Review the configured host and the customer's isolation contract before admitting a lookup.

Submission pins connector destination, agent generation, tool version and grant ID. The server rechecks those values and environment access, then uses the existing policy evaluator and transactional action outbox. It does not call the business connector from the request handler. Denials and independent approvals remain authoritative. The worker rechecks authorization and the reviewed destination before dispatch. HTTP supplier checks use only the adapter's supplier GET operation, with existing tenant/organization/operation binding and bounded responses. No automatic HTTP retry is added.

The default synthetic connector remains unchanged. Its results are labelled **Verified synthetic lookup** and establish no customer acceptance. An HTTP **Verified supplier lookup** proves the verified result for one supplier read; purchase handling, tenant isolation, recovery and deployment acceptance still require separate evidence. This feature does not configure or certify a customer sandbox. The owner must provision their reviewed endpoint and secret privately through the existing operator configuration before running HTTP checks.

## Results and uncertain requests

The current account's last 20 checks are shown for the selected environment. Refreshing or polling results reads only local records; it never calls the remote lookup endpoint. Queued/executing checks refresh periodically. Approval, uncertain and unrecognized states require operator attention. A nonterminal check blocks new checks for that account/environment until it is finished or reconciled in the existing execution ledger. Reconciliation remains an explicit, separately authorized operator action.

Browser request keys are scoped to workspace, account and selected environment. Durable intake receipts support identical replay, recovery and cancellation fencing. If an intake response is interrupted, use Recover supplier check. Cancel pending check request either returns the already-admitted check or stores a cancellation that prevents a delayed request from admitting work. It does not cancel or delete an admitted action. Pending keys are cleared only after acknowledgement. Receipt recovery returns the current action state without dispatch or reconciliation.

The configured host and destination binding, supplier reference, result status and trace identifiers are visible to the owner. Raw credentials, remote response bodies and private diagnostics are not exposed. Receipts contain a request fingerprint and action identifier; raw request keys are not stored in the receipt. The ordinary action record retains its established idempotency key/envelope under the existing retention contract. Intake receipts are excluded from workbench execution history. Each workspace supports up to 1000 check/cancellation receipts; this feature does not purge receipts or reset counters.

Schema remains 11. No migration, connector-setting changes or automatic checks occur during deployment. Pilot-mode UI checks, broader customer contract acceptance and production deployment remain future scope.
