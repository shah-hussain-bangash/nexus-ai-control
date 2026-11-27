import test from "node:test";
import assert from "node:assert/strict";
import { rerankRequest } from "../src/rerankRequest.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";
test("reranking submits only saved search identity and the explicit repeated query", () => {
  assert.deepEqual(rerankRequest("saved", " query "), {
    search_id: "saved",
    query: "query",
  });
});
test("lost reranking replies retain a separate key without storing private query text", async () => {
  const values = new Map<string, string>();
  const store = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
  const scope = liveIntentScope("local-rerank", "org", "user", "staging");
  let key = "";
  const body = rerankRequest("saved", "private repeated query");
  await assert.rejects(
    sendLiveIntent(store, scope, body, async (value) => {
      key = value;
      throw Error("Lost reply");
    }),
  );
  assert.ok(![...values.values()].join("").includes("private repeated query"));
  for (const other of [
    liveIntentScope("indexed-search", "org", "user", "staging"),
    liveIntentScope("local-rerank", "org", "user", "production"),
    liveIntentScope("local-rerank", "other", "user", "staging"),
    liveIntentScope("local-rerank", "org", "other", "staging"),
  ])
    assert.equal(readRecovery(store, other), null);
  await sendLiveIntent(store, scope, body, async (value) => {
    assert.equal(value, key);
    return { id: "reranked", status: "completed" };
  });
  assert.equal(readRecovery(store, scope), null);
});
test("definitive preflight query mismatch permits a corrected explicit intent", async () => {
  const values = new Map<string, string>();
  const store = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
  const scope = liveIntentScope("local-rerank", "org", "user", "staging");
  await assert.rejects(
    sendLiveIntent(
      store,
      scope,
      rerankRequest("saved", "wrong query"),
      async () => {
        throw Object.assign(Error("Query differs"), {
          status: 409,
          code: "RERANK_QUERY_DIFFERENT",
        });
      },
    ),
  );
  assert.equal(readRecovery(store, scope), null);
});
