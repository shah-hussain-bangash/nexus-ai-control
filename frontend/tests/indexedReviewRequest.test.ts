import test from "node:test";
import assert from "node:assert/strict";
import { indexedReviewRequest } from "../src/indexedReviewRequest.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";

test("review intent contains labels and saved search ID without query or model inputs", () => {
  const expected = ["second", "first"];
  const body = indexedReviewRequest({
    searchId: "saved-search",
    expectation: "retrieve",
    expected,
    language: "Arabic",
    precision: 100,
    note: " Reviewed fixture. ",
  });
  assert.deepEqual(body, {
    search_id: "saved-search",
    expectation: "retrieve",
    expected_document_ids: ["first", "second"],
    query_language: "Arabic",
    minimum_precision_percent: 100,
    note: "Reviewed fixture.",
  });
  expected.push("later");
  assert.deepEqual(body.expected_document_ids, ["first", "second"]);
});

test("negative expectations cannot carry hidden positive labels or precision targets", () => {
  assert.deepEqual(
    indexedReviewRequest({
      searchId: "saved",
      expectation: "no_results",
      expected: ["hidden previous selection"],
      language: "",
      precision: 90,
      note: "Expected empty.",
    }),
    {
      search_id: "saved",
      expectation: "no_results",
      expected_document_ids: [],
      note: "Expected empty.",
    },
  );
});

test("lost review replies preserve their own scoped intent without storing labels", async () => {
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
  const scope = liveIntentScope("indexed-review", "org", "reviewer", "staging");
  const body = indexedReviewRequest({
    searchId: "saved",
    expectation: "retrieve",
    expected: ["source"],
    language: "English",
    precision: 80,
    note: "Private review note.",
  });
  let key = "";
  await assert.rejects(
    sendLiveIntent(store, scope, body, async (intent) => {
      key = intent;
      throw Error("Lost reply");
    }),
  );
  assert.ok(readRecovery(store, scope));
  assert.ok(![...data.values()].join("").includes("Private review note"));
  for (const other of [
    liveIntentScope("indexed-search", "org", "reviewer", "staging"),
    liveIntentScope("indexed-review", "other", "reviewer", "staging"),
    liveIntentScope("indexed-review", "org", "other", "staging"),
    liveIntentScope("indexed-review", "org", "reviewer", "production"),
  ])
    assert.equal(readRecovery(store, other), null);
  await sendLiveIntent(store, scope, body, async (intent) => {
    assert.equal(intent, key);
    return { id: "review", status: "passed" };
  });
  assert.equal(readRecovery(store, scope), null);
});

test("preflight stale evidence permits a new reviewed intent", async () => {
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
  const scope = liveIntentScope("indexed-review", "org", "reviewer", "staging");
  for (const code of [
    "INDEX_REVIEW_SEARCH_UNSUPPORTED",
    "INDEX_REVIEW_SEARCH_STALE",
  ]) {
    await assert.rejects(
      sendLiveIntent(store, scope, { search_id: "stale" }, async () => {
        throw Object.assign(Error(code), { status: 409, code });
      }),
    );
    assert.equal(readRecovery(store, scope), null);
  }
});
