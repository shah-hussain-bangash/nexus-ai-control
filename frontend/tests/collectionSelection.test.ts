import test from "node:test";
import assert from "node:assert/strict";
import { collectionSelection } from "../src/collectionSelection.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";
const complete = {
  searchable: true,
  index_ids: ["first", "second"],
  model: "embedding:test",
  model_digest: "a".repeat(64),
};
test("complete collection selection copies the whole set without executing search", () => {
  const ids = collectionSelection(
    complete,
    complete.model,
    complete.model_digest,
  );
  ids.pop();
  assert.equal(complete.index_ids.length, 2);
});
test("partial, mismatched, duplicate and over-capacity collections cannot become query selection", () => {
  for (const value of [
    { ...complete, searchable: false },
    { ...complete, model: "other:test" },
    { ...complete, model_digest: "b".repeat(64) },
    { ...complete, index_ids: [] },
    { ...complete, index_ids: ["same", "same"] },
    { ...complete, index_ids: Array.from({ length: 9 }, (_, i) => String(i)) },
  ])
    assert.throws(() =>
      collectionSelection(value, complete.model, complete.model_digest),
    );
});
test("lost collection replies retain a separate scoped queue intent", async () => {
  const data = new Map<string, string>();
  const store = {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
    removeItem: (key: string) => {
      data.delete(key);
    },
  };
  const scope = liveIntentScope("index-collection", "org", "user", "staging");
  let key = "";
  const body = { name: "Collection", sources: [{ id: "source", version: 1 }] };
  await assert.rejects(
    sendLiveIntent(store, scope, body, async (value) => {
      key = value;
      throw Error("Lost reply");
    }),
  );
  for (const other of [
    liveIntentScope("index-build-job", "org", "user", "staging"),
    liveIntentScope("index-collection", "org", "other", "staging"),
    liveIntentScope("index-collection", "other", "user", "staging"),
    liveIntentScope("index-collection", "org", "user", "production"),
  ])
    assert.equal(readRecovery(store, other), null);
  await sendLiveIntent(store, scope, body, async (value) => {
    assert.equal(value, key);
    return { id: "group", status: "queued" };
  });
  assert.equal(readRecovery(store, scope), null);
});
