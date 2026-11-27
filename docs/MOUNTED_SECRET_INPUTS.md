# Optional mounted secret inputs

Settings includes an owner-only **Secret input sources** panel. It reports input
sources and aggregate provider-namespace counts, without reading files or returning
secret values, paths or provider variable names. It is not an authentication or
file-readability check. No credential is uploaded, changed or rotated by the panel.

## Supported inputs

Runtime startup supports either the existing nonempty value or a companion file
variable for each of these four secrets:

| Existing value | Optional companion path | Reload behavior |
| --- | --- | --- |
| `NEXUS_SECRET` | `NEXUS_SECRET_FILE` | Restart required |
| `NEXUS_AGENT_SECRET` | `NEXUS_AGENT_SECRET_FILE` | Restart required |
| `NEXUS_OIDC_CLIENT_SECRET` | `NEXUS_OIDC_CLIENT_SECRET_FILE` | Restart required |
| `NEXUS_METRICS_TOKEN` | `NEXUS_METRICS_TOKEN_FILE` | Restart required |

Provider routes retain an `env:NEXUS_PROVIDER_...` reference, for example
`env:NEXUS_PROVIDER_TEAM_KEY`. The operator may supply either
`NEXUS_PROVIDER_TEAM_KEY` or `NEXUS_PROVIDER_TEAM_KEY_FILE`. Paths are resolved
only from the server's environment, never from model configuration or a request.
References ending in `_FILE` are reserved and rejected; reference the base name.

The HTTP business adapter similarly supports the configured `business_token_env`
name (default `NEXUS_BUSINESS_API_KEY`) or that name plus `_FILE`. The selected
base name cannot itself end in `_FILE`. Synthetic connectors and local Ollama
remain unaffected and do not require a credential file.

Provider and business credentials are resolved before dispatch. Inference checks
them during preparation and again under its admission lock, and uses the value
resolved at admission for the one outbound call. Business resolves once per HTTP
dispatch. An
atomically replaced file can be picked up on the next dispatch without changing
the saved route reference. Already admitted/in-flight requests retain the value
they resolved. There is no retry or fallback to another source when resolution
fails. Missing, conflicting or invalid provider credentials fail before network
dispatch and before a new inference reservation is stored. Business resolution
also fails before its HTTP request; existing worker outcome handling is unchanged.

## File and ambiguity rules

- File paths must be absolute and refer to regular files. Direct symlinks,
  Windows reparse-point targets at the selected path, directories and special
  files are rejected. Parent-directory links/mount layout remain the operator's
  responsibility; no approved-root policy is imposed by this loader.
- Contents must be nonempty UTF-8 without a BOM, at most 16384 bytes. Exactly one
  terminal LF or CRLF is removed for mounted text files. Other control characters,
  embedded newlines, invalid UTF-8 and oversized files fail. Other whitespace is
  preserved. Provider/business credentials also retain their ASCII token rules;
  business tokens remain limited to 16–4096 characters.
- The loader checks the opened file's identity and size, bounds the read and
  rejects detectable in-place changes while reading. Use atomic replacement for
  rotation. This is not a guarantee against a privileged filesystem attacker.
- A nonempty direct value plus a nonempty companion path is an error. Neither
  source wins silently. An empty direct value permits a configured file. If neither
  is set, existing disabled/required-secret behavior applies.
- Errors do not include the file path, credential value or parser diagnostics.
  Resolved values are not copied into environment variables or saved to the
  application database. They remain in process memory as needed for authentication.

Settings loaded with `Settings.from_env()` capture the four startup source labels
at startup. Refreshing the panel does not reload those values. Programmatically
supplied settings are labelled as supplied at startup. Provider/business labels
describe current environment configuration only. Conflicts are shown as blocked;
file readability and remote acceptance are deliberately not inferred.

## Operator setup

Provision files through your deployment's approved secret mount mechanism, outside
source control and web-served directories. Restrict file and parent-directory
permissions to the service identity and approved custodians. Remove the nonempty
direct value from the process and any loaded `.env` before enabling its companion
file path. Do not put file contents in source, dashboard fields, evidence or chat.
Mounts that expose the selected file as a symlink are not supported; provide an
approved regular-file view instead. No deployment mount layout is created here.

The `.env.example` contains blank optional companion names. No path is enabled by
default. The audit Ed25519 signing key has its existing separate
`NEXUS_AUDIT_SIGNING_KEY_FILE` configuration and PEM validation; it is not loaded as
a single-line secret. Database URLs and backup encryption keys retain their
existing configuration and are outside this increment.

Core signing-secret rotation requires coordinated restart and review of session,
workload-token and pending OIDC transaction consequences. Mounted-file support
does not demonstrate that rotation, key custody or a vault integration has passed
acceptance. No vault API, automatic rotation scheduler, credential validation call,
cloud deployment or network isolation is introduced here.

## Checks and boundaries

The read-only `GET /v1/secret-inputs` endpoint requires owner `members` permission
and current environment membership. It performs no credential-file reads, test
dispatches, secret mutation or audit-data export.

Focused checks use disposable files, startup configurations and mock HTTP
transports. They cover invalid inputs, ambiguity, bounded reads, file replacement,
startup reload semantics, per-dispatch credential changes, denied access and
source-view redaction. The actual symlink test is skipped on Windows identities
that cannot create symlinks; it remains enabled where supported. No permission
change is requested just to run that check.

No active credentials, file paths, configuration, database or running application
are changed by this development increment. Deployment secret custody, rotation
acceptance and enforced egress isolation remain separate work.
