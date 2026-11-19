import test from "node:test";
import assert from "node:assert/strict";
import { copyPayload, copyOutcome } from "../src/environmentAssetCopy.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery, acknowledgeRecovery } from "../src/inferenceRecovery.ts";
const source = {
  id: "source-id",
  kind: "prompt",
  name: "Source",
  description: "Reviewed design",
  status: "validated",
  version: 3,
  config: { template: "Reviewed {{query}}" },
};
const target = { key: "production", name: "Production", version: 4 };
const result = {
  id: "a".repeat(64),
  status: "copied",
  source_environment: "staging",
  source_asset_id: "source-id",
  source_version: 3,
  target_environment: "production",
  target_asset_id: "new-id",
  target_created_version: 1,
  kind: "prompt",
  name: "New draft",
};
function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) || null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}
test("copy review pins source and target versions and requires a new draft name", () => {
  assert.deepEqual(
    copyPayload(
      "staging",
      source,
      target,
      " New draft ",
      " Reviewed contents ",
      true,
    ),
    {
      source_asset_id: "source-id",
      expected_source_version: 3,
      target_environment: "production",
      expected_target_version: 4,
      name: "New draft",
      note: "Reviewed contents",
      reviewed: true,
    },
  );
  for (const invalid of [
    { ...source, kind: "model" },
    { ...source, kind: "workflow" },
    { ...source, status: "draft" },
    { ...source, version: 0 },
    { ...source, version: 1.5 },
  ])
    assert.throws(() =>
      copyPayload(
        "staging",
        invalid,
        target,
        "New draft",
        "Reviewed contents",
        true,
      ),
    );
  assert.throws(() =>
    copyPayload(
      "staging",
      source,
      { ...target, key: "staging" },
      "New draft",
      "Reviewed contents",
      true,
    ),
  );
  assert.throws(() =>
    copyPayload(
      "staging",
      source,
      { ...target, version: 0 },
      "New draft",
      "Reviewed contents",
      true,
    ),
  );
  assert.throws(() =>
    copyPayload(
      "staging",
      source,
      target,
      "New draft",
      "Reviewed contents",
      false,
    ),
  );
  assert.throws(() =>
    copyPayload(
      "staging",
      source,
      target,
      "bad\nname",
      "Reviewed contents",
      true,
    ),
  );
});
test("copy and cancellation outcomes must match the original source and safe result contract", () => {
  assert.equal(copyOutcome(result, "staging").target_asset_id, "new-id");
  assert.equal(
    copyOutcome(
      {
        id: "b".repeat(64),
        status: "cancelled",
        source_environment: "staging",
      },
      "staging",
    ).status,
    "cancelled",
  );
  for (const invalid of [
    {},
    { ...result, source_environment: "production" },
    { ...result, status: "validated" },
    { ...result, target_created_version: 2 },
    { ...result, target_environment: "staging" },
    { ...result, target_asset_id: "" },
    { ...result, kind: "model" },
  ])
    assert.throws(() => copyOutcome(invalid, "staging"));
});
test("uncertain copies retain one key until recovery or server-fenced cancellation is acknowledged", async () => {
  const saved = storage(),
    scope = liveIntentScope("asset-copy", "workspace", "owner", "staging");
  const body = copyPayload(
    "staging",
    source,
    target,
    "New draft",
    "Reviewed contents",
    true,
  );
  await assert.rejects(
    sendLiveIntent(
      saved,
      scope,
      body,
      async () => {
        throw Error("Network interrupted");
      },
      () => "retained-copy-key-0001",
    ),
  );
  const pending = readRecovery(saved, scope)!;
  assert.equal(pending.key, "retained-copy-key-0001");
  await assert.rejects(
    sendLiveIntent(
      saved,
      scope,
      { ...body, name: "Changed intent" },
      async () => result,
    ),
  );
  assert.equal(
    readRecovery(
      saved,
      liveIntentScope("asset-copy", "workspace", "owner", "production"),
    ),
    null,
  );
  assert.equal(
    readRecovery(
      saved,
      liveIntentScope("asset-copy", "workspace", "another", "staging"),
    ),
    null,
  );
  assert.equal(
    readRecovery(
      saved,
      liveIntentScope("asset-copy", "another", "owner", "staging"),
    ),
    null,
  );
  acknowledgeRecovery(
    saved,
    scope,
    pending,
    copyOutcome(
      {
        id: "b".repeat(64),
        status: "cancelled",
        source_environment: "staging",
      },
      "staging",
    ),
  );
  assert.equal(readRecovery(saved, scope), null);
});
