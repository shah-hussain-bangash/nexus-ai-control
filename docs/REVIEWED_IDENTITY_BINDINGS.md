# Reviewed SSO identity bindings for existing members

Settings → Workspace access includes **Reviewed SSO identity bindings** for owners.
This allows binding, replacing or clearing the trusted identity-provider subject
of an existing non-owner member. It is workspace-wide, like account activation,
role changes and offboarding, and applies across environments.

Every successful binding change **deactivates the target and revokes all of their
application sessions**. It preserves their role, local password, records and
environment assignments. Reactivation is a separate existing owner-reviewed
directory action. Clearing does not turn into automatic activation or a password
reset. In-flight external work cannot be undone by an account change.

## Review workflow

1. Obtain the exact subject from the trusted identity administrator. A subject is
   an identity identifier, not a password, token or assumed email match.
2. Reload the member directory and configured issuer. Select the target account,
   review its current bound/unbound state, role, active state and session count.
3. Choose bind/replace with the exact subject, or clear with no subject. Confirm
   the workspace-wide deactivation/session impact and provide a visible reason.
4. Submit the change. The server checks the reviewed member/session revision,
   configured issuer, permissions, workspace, subject uniqueness and intent key.
5. Inspect the refreshed directory. Review the member's intended access before
   separately activating them. In pilot mode, an account without a binding cannot
   be activated through the member administration endpoint.

The endpoint does not contact an IdP to validate the entered subject. Email,
subject and account correspondence must be reviewed by the administrator. Owners
and the caller's own identity remain protected, including replacement/clear.
Fresh pilot-owner bootstrap retains its separate CLI workflow requiring an exact
trusted `--oidc-subject`. This API does not transfer ownership or modify an
existing owner binding.

## Pilot sign-in boundary

Pilot SSO requires the active account's stored issuer/subject to exactly match the
validated token and the existing email lookup. It does not assign a previously
unbound identity merely because an email matches. Existing cryptographic issuer,
audience, nonce, PKCE, verified-email, expiry and configured MFA/ACR checks remain.
Local mode retains its existing first-login linking behavior for active unbound
accounts; it is not pilot identity acceptance. Clearing always deactivates first,
and pilot activation requires a binding.

If SSO completes before an identity change, the change removes its resulting
session. A later callback must observe the updated member state under the same
account lock and cannot bypass deactivation or the new exact binding.

## APIs and recovery

- `GET /v1/member-admin` supplies current member revisions and the configured
  public issuer to owners. Raw bound subjects are not returned. Unsafe issuer
  configuration (userinfo, query, fragment, invalid scheme/port or control text)
  fails with a generic error instead of disclosing credentials.
- `POST /v1/member-identity/{member_id}` requires CSRF, `Idempotency-Key`,
  `expected_revision`, `expected_issuer`, `command` (`bind` or `clear`), `subject`,
  visible 10–500 character `note`, and strict boolean `reviewed: true`.
- `POST /v1/member-identity/recover` requires CSRF and `{ "key": "..." }`. It
  returns the current actor's original workspace-wide operation receipt.

Subject text is exact, at most 200 characters, without padding or control
characters. Bind requires a configured issuer and nonempty subject; clear requires
an empty subject and can be used after an issuer is removed. The expected issuer
must match current server configuration. No issuer is accepted as a new trusted
provider through this request.

The operation stores an immutable receipt with the target ID, command, historical
session count, deactivated/bound outcome and a binding fingerprint. Raw subject
text is stored only in the existing identity record, not this receipt or its audit
detail. Notes are operator-provided; do not place subjects, tokens or credentials
in them. Duplicate identity errors do not reveal the conflicting account or
workspace, and the database uniqueness constraint handles concurrent conflicts.

Retries with the same intent and body return the original receipt. A different
body or target conflicts. Recovery/retry never repeats a change, including after
a later account reactivation, role change or issuer configuration change. The
receipt describes the original operation; the refreshed directory describes
current account state. Browser recovery stores only key/hash/timing in a
workspace/actor namespace; changing environments does not create a second
identity-change intent. Another owner cannot recover the original actor's key.

History is bounded to 1000 identity-change receipts per actor/workspace. At
capacity new binding changes fail before mutation, preserving existing receipts.
Existing account deactivation and session revocation remain available as separate
controls. Identity receipts are excluded from generic workbench listings. Uses
existing schema 12 storage, with no migration or new runtime setting.

## Verification and remaining scope

Focused checks use disposable users and cryptographic mock SSO tokens. They cover
bind/clear, session removal, preserved role/assignments, separate activation,
pilot prebinding, a normal-API mocked member sign-in and its authorization limit,
stale state, issuer changes, duplicate identity, protected targets, receipt replay,
workspace/actor isolation and bounded history. No real identity provider is
contacted and no active user, binding, password or configuration is changed.

This is manual owner-reviewed identity administration. Automated IdP provisioning
and offboarding, verified MFA acceptance, workload federation and deployment
acceptance remain separate work. No invitation is sent, IdP identity changed,
provider session revoked or ownership transferred by this feature.
