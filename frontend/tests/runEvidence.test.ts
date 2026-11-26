import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { canonicalEvidence } from "../src/supplierEvidence.ts";
import { verifyRunEvidence } from "../src/runEvidence.ts";

const context = {
  workspace_id: "workspace",
  user_id: "auditor",
  environment: "staging",
  revision: 1,
  binding_id: "binding",
};
function report() {
  const payload = {
    format: "nexus-durable-run-evidence",
    format_version: 1,
    boundary: "Unsigned snapshot.",
    exported_at_utc: "2026-11-26T00:00:00.000000Z",
    schema_version: 11,
    scope: {
      workspace_id: "workspace",
      account_id: "auditor",
      environment: "staging",
    },
    run: { id: "run", status: "outcome_unknown", version: 4 },
    connector: { mode: "synthetic" },
    steps: [
      { position: 0, kind: "checkpoint", status: "completed", action: null },
      {
        position: 1,
        kind: "governed_action",
        status: "outcome_unknown",
        action: { status: "outcome_unknown", verified: false },
      },
      { position: 2, kind: "output", status: "pending", action: null },
    ],
  };
  return {
    payload,
    integrity: {
      algorithm: "sha256",
      canonicalization: "sorted-ascii-json-v1",
      authenticated_signature: false,
      digest: createHash("sha256")
        .update(canonicalEvidence(payload))
        .digest("hex"),
    },
  };
}
test("run report retains unknown effect and verifies checksum", async () => {
  const value = report();
  assert.equal(await verifyRunEvidence(value, context, "run"), value);
  assert.equal(value.payload.steps[1].action?.verified, false);
});
test("run evidence rejects tampering and stale account or environment", async () => {
  const changed = report();
  changed.payload.run.status = "succeeded";
  await assert.rejects(verifyRunEvidence(changed, context, "run"), /checksum/);
  for (const c of [
    null,
    { ...context, user_id: "other" },
    { ...context, workspace_id: "other" },
    { ...context, environment: "other" },
  ])
    await assert.rejects(verifyRunEvidence(report(), c, "run"), /account/);
  await assert.rejects(
    verifyRunEvidence(report(), context, "another-run"),
    /account/,
  );
});
test("signed claims, unbounded steps and false verification claims are rejected", async () => {
  const signed = report();
  signed.integrity.authenticated_signature = true;
  await assert.rejects(verifyRunEvidence(signed, context, "run"), /format/);
  const large = report();
  large.payload.steps = Array.from(
    { length: 13 },
    () => large.payload.steps[0],
  );
  await assert.rejects(verifyRunEvidence(large, context, "run"), /format/);
  const falseClaim = report();
  falseClaim.payload.steps[1].action!.verified = true;
  await assert.rejects(verifyRunEvidence(falseClaim, context, "run"), /format/);
});
