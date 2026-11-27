import test from "node:test";
import assert from "node:assert/strict";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";
function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}
test("uncertain signed snapshot retains one recovery key without storing the note", async () => {
  const store = storage(),
    scope = liveIntentScope("signed-audit", "org", "user", "staging");
  const body = {
    expected_key_id: "a".repeat(64),
    limit: 200,
    note: "Private operator review note",
  };
  await assert.rejects(
    sendLiveIntent(
      store,
      scope,
      body,
      async () => {
        throw Error("lost response");
      },
      () => "signed-audit-intent-0001",
    ),
  );
  assert.equal(readRecovery(store, scope)?.key, "signed-audit-intent-0001");
  assert.equal(store.getItem(scope)?.includes(body.note), false);
  assert.equal(
    readRecovery(
      store,
      liveIntentScope("signed-audit", "org", "other", "staging"),
    ),
    null,
  );
  let sent = "";
  await sendLiveIntent(store, scope, body, async (key) => {
    sent = key;
    return { id: "original-snapshot", status: "ready" };
  });
  assert.equal(sent, "signed-audit-intent-0001");
  assert.equal(readRecovery(store, scope), null);
});
test("confirmed key rotation clears an uncommitted intent for a fresh review", async () => {
  const store = storage(),
    scope = liveIntentScope("signed-audit", "org", "user", "staging");
  await assert.rejects(
    sendLiveIntent(
      store,
      scope,
      { expected_key_id: "old" },
      async () => {
        throw Object.assign(Error("Reload key"), {
          status: 409,
          code: "AUDIT_SIGNING_KEY_CHANGED",
        });
      },
      () => "signed-audit-intent-0001",
    ),
  );
  assert.equal(readRecovery(store, scope), null);
});
