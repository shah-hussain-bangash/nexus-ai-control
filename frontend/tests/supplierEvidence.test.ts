import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { canonicalEvidence, verifyEvidence } from "../src/supplierEvidence.ts";

const context = {
  workspace_id: "workspace",
  user_id: "owner",
  environment: "staging",
  revision: 1,
  binding_id: "binding",
};
function report() {
  const payload = {
    format: "nexus-supplier-check-evidence",
    format_version: 1,
    exported_at_utc: "2026-11-19T00:00:00.000000Z",
    boundary: "Unsigned local snapshot.",
    scope: {
      workspace_id: "workspace",
      account_id: "owner",
      environment: "staging",
    },
    check: {
      id: "check",
      status: "queued",
      supplier_id: "SUP-104",
      verified: false,
    },
    connector: { mode: "synthetic" },
    operation: { action: "supplier:read", resource: "suppliers" },
    audit_events: [],
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
test("Python and browser canonical checksums match for Unicode and nested values", () => {
  assert.equal(
    createHash("sha256")
      .update(canonicalEvidence({ z: [true, null, 42], a: "مرحبا 😀" }))
      .digest("hex"),
    "ad60c2f7273c87c5c67253c6edc376a0f7619c1db916bcbfe35495a3e21b3978",
  );
  assert.throws(() => canonicalEvidence({ value: 0.5 }));
});
test("valid unsigned report retains unresolved outcome", async () => {
  const value = report();
  assert.equal(await verifyEvidence(value, context, "check"), value);
  assert.equal(value.payload.check.verified, false);
});
test("tampering and account, environment, check or format mismatches prevent download", async () => {
  const tampered = report();
  tampered.payload.check.verified = true;
  await assert.rejects(verifyEvidence(tampered, context, "check"), /checksum/);
  for (const c of [
    null,
    { ...context, user_id: "another" },
    { ...context, workspace_id: "other" },
    { ...context, environment: "production" },
  ])
    await assert.rejects(verifyEvidence(report(), c, "check"), /match/);
  await assert.rejects(
    verifyEvidence(report(), context, "another-check"),
    /match/,
  );
  const signed = report();
  signed.integrity.authenticated_signature = true;
  await assert.rejects(verifyEvidence(signed, context, "check"), /match/);
});
