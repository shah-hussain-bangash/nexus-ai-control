# Local pilot acceptance on this PC

Target: one operator on this Windows PC, loopback-only NEXUS and installed local
Ollama weights. This is a development-mode pilot, not a production deployment or
approval for sensitive customer data. Do not expose the app or Ollama to the LAN
or Internet. No hosted provider, customer connector, new account, migration or
credential reset is required by these checks.

## Repeatable checks

From the project root in Cursor, keep the normal app terminal running and use a
separate terminal:

```powershell
npm.cmd run pilot:check
npm.cmd run test:synthetic
npm.cmd run test:recovery
npm.cmd run test:answers
npm.cmd run test:answers:local
```

`pilot:check` defaults to app port 62346; use `npm.cmd run pilot:check -- -Port
YOUR_APP_PORT` if the launcher printed another port. It reads health endpoints,
checks anonymous access denial, and inspects the two selected Windows listeners.
It never logs in, reads private configuration, changes firewall rules, enables
metrics or submits a model question. A failed/unavailable socket-table check
cannot count as a pass. It is a point-in-time check, not continuous monitoring.

The remaining commands use fresh synthetic databases and exclusive report names
under `backend/data/drills`, then remove their temporary databases. They do not
restore over the running app or read its accounts, secrets or records. Preserve
reports privately; they contain only synthetic fixture answers and safe metadata.
File names, release/schema, timestamps and source hashes support reproduction;
the JSON receipts are unsigned and are not authenticated acceptance evidence.

`test:answers` uses a mock HTTP transport and an independent real-network denial
guard. It validates the harness and application controls, not model quality.
`test:answers:local` explicitly calls the installed `qwen3:8b` through the fixed
loopback Ollama adapter. It never downloads a model. Keep Ollama running; use
`npm.cmd run test:answers:local -- -Model OTHER_INSTALLED_LOCAL_TAG` only for an
approved local model. Cloud tags and arbitrary endpoints are rejected. Model
tags may move: record the installed model digest separately for longitudinal
comparisons; the report does not pin or certify weights.

## Six work areas and their exit conditions

| Work area | Engineering evidence available | Still required for pilot acceptance |
| --- | --- | --- |
| Customer workflow acceptance | Synthetic connector, approval, idempotency, isolation and recovery exercises | Operator chooses the intended workflow and independently confirms its expected outputs. Synthetic supplier fixtures are not a customer integration. Continue without a customer system until one is explicitly approved. |
| English/Arabic answer quality | Four fixed fact/citation/poisoning examples, two server-side missing-source checks, source deletion withholding, repeatable local-model command | A fluent reviewer compares every generated statement and citation with the source, adds representative positive, ambiguous and unsupported questions, and records language-specific failures. The automated token checks do not establish entailment, factuality or model refusal quality. |
| Local deployment security | Health/readiness and anonymous denial checks, loopback listener check, existing session/CSRF/role/isolation tests | Operator confirms Windows updates, device access, disk encryption, recovery-key custody and approved data classification. Independent security review remains open. Remote/team access requires a separately reviewed HTTPS/identity/network deployment. |
| Operations and recovery | Existing synthetic backup, authenticated encrypted inspection and restored-application exercises; read-only point-in-time check | Operator selects a protected encrypted backup destination and key custody, retention and schedule; then measures a representative recovery without overwriting the active app. Notification destinations, delivery tests, RPO/RTO and continuous monitoring remain unaccepted. |
| Independent validation | Source tests and reproducible engineering reports | Independent reviewer completes security, dependency/image, load/soak, keyboard, screen-reader and device checks on the intended release. A developer's test run is not independent certification. |
| Release acceptance | This local runbook, exact-source reports and the existing readiness board | Named operator signs off scope, supported users/data, failure handling, rollback and support ownership. Open failures block acceptance. Production acceptance stays open. |

The dashboard's six pending areas are acceptance categories, not buttons that
implement missing infrastructure. Do not mark all workstreams passed because a
synthetic command returned `passed: true`.

## Answer-review procedure

1. Run the local-model command once against the release under review. A failure
   is retained in its uniquely named report; do not overwrite it or repeatedly
   retry until it appears green.
2. Open each synthetic `answers` entry. Compare its claims, language and actual
   `[1]` citation with the fixed source in `backend/nexus/answer_drill.py`.
3. Record reviewer, revision, installed model digest, date, observed defects and
   disposition separately. `quality_accepted` intentionally remains false even
   when the automated checks pass.
4. Keep poisoning controls narrow: an absent override marker is not proof of
   general prompt-injection resistance. Missing-source checks are API refusals
   before a model call, not generated model refusals.

## Start, stop and rollback

Start with `npm.cmd start`; use only the loopback URL printed by the launcher.
Keep the launcher terminal open. Ctrl+C stops its API and worker together. Check
readiness after restart and confirm the selected environment before any write.
If the app or worker fails, stop new work, preserve the terminal/error evidence
privately and investigate; do not launch duplicate workers or blindly resend
uncertain requests. Use saved request recovery and owner reconciliation.

Before a source upgrade, stop all writers and use the existing reviewed encrypted
backup procedure with a protected new destination and separately held key. Record
the prior source revision and schema. Never switch old code onto a newer schema
without a reviewed compatible recovery plan. Prove a backup in a separate fresh
destination before considering cutover. This pilot process does not authorize
overwriting active data, merging pull requests or changing credentials.

See [operations](OPERATIONS_0_12_0.md),
[isolated recovery](ISOLATED_SQLITE_RECOVERY.md),
[document-backed answers](DOCUMENT_INFERENCE.md) and the
[production roadmap](PRODUCTION_ROADMAP.md) for the implemented boundaries.
