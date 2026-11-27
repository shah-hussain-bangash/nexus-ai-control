import test from "node:test";
import assert from "node:assert/strict";
import {
  retentionApplyRequest,
  retentionConfirmation,
} from "../src/auditRetentionRequest.ts";
import { liveIntentScope } from "../src/liveIntent.ts";
const plan = { id: "saved-preview", status: "previewed", policy_version: 3 };
const note = "Reviewed expired metadata removal.";
test("retention confirmation binds the saved policy and accepts no new target list", () => {
  assert.deepEqual(
    retentionApplyRequest(plan, 3, retentionConfirmation, note),
    { expected_version: 3, confirmation: retentionConfirmation, note },
  );
  assert.throws(() =>
    retentionApplyRequest(plan, 4, retentionConfirmation, note),
  );
  assert.throws(() => retentionApplyRequest(plan, 3, "yes", note));
  assert.throws(() =>
    retentionApplyRequest(
      { ...plan, status: "unknown" },
      3,
      retentionConfirmation,
      note,
    ),
  );
  assert.throws(() =>
    retentionApplyRequest(plan, 3, retentionConfirmation, "short"),
  );
});
test("retention policy, preview and signed snapshot recovery scopes stay separate", () => {
  const scope = liveIntentScope(
    "audit-retention-plan",
    "org",
    "user",
    "staging",
  );
  assert.notEqual(
    scope,
    liveIntentScope("audit-retention-policy", "org", "user", "staging"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("signed-audit", "org", "user", "staging"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("audit-retention-plan", "org", "other", "staging"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("audit-retention-plan", "org", "user", "development"),
  );
});
