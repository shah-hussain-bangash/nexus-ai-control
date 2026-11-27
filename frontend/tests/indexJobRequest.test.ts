import test from "node:test";
import assert from "node:assert/strict";
import { indexJobRequest } from "../src/indexJobRequest.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";
test("queued build pins copied source versions and sends no text, model or vectors", () => {
  const sources = [{ id: "source", version: 2 }];
  const body = indexJobRequest(" Snapshot ", sources);
  sources[0].version = 3;
  assert.deepEqual(body, {
    name: "Snapshot",
    sources: [{ id: "source", version: 2 }],
  });
});
test("lost queue replies retain a separate environment-bound intent", async () => {
  const data = new Map<string, string>();
  const store = {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
  };
  const scope = liveIntentScope("index-build-job", "org", "user", "staging");
  const body = indexJobRequest("Snapshot", [{ id: "source", version: 1 }]);
  let key = "";
  await assert.rejects(
    sendLiveIntent(store, scope, body, async (value) => {
      key = value;
      throw Error("Lost reply");
    }),
  );
  for (const other of [
    liveIntentScope("index-build-job", "org", "user", "production"),
    liveIntentScope("index-build-job", "other", "user", "staging"),
    liveIntentScope("index-build-job", "org", "other", "staging"),
    liveIntentScope("neural-index-build", "org", "user", "staging"),
  ])
    assert.equal(readRecovery(store, other), null);
  await sendLiveIntent(store, scope, body, async (value) => {
    assert.equal(value, key);
    return { id: "job", status: "queued" };
  });
  assert.equal(readRecovery(store, scope), null);
});
