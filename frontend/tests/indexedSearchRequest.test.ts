import test from "node:test";
import assert from "node:assert/strict";
import { indexedSearchRequest } from "../src/indexedSearchRequest.ts";
test("single snapshot keeps the legacy query payload", () => {
  assert.deepEqual(indexedSearchRequest("primary", [], "query"), {
    index_id: "primary",
    query: "query",
    top_k: 5,
    min_score: 0.15,
    one_per_document: true,
  });
});
test("combined selection is copied, deduplicated and canonical regardless of click order", () => {
  const ids = ["second", "first", "primary"];
  const body = indexedSearchRequest("primary", ids, "query");
  ids.push("later");
  assert.deepEqual(body, {
    index_ids: ["first", "primary", "second"],
    query: "query",
    top_k: 5,
    min_score: 0.15,
    one_per_document: true,
  });
  assert.deepEqual(
    body,
    indexedSearchRequest("second", ["primary", "first"], "query"),
  );
});
test("missing primary or more than eight snapshots cannot submit a partial selection", () => {
  assert.throws(() => indexedSearchRequest("", ["another"], "query"));
  assert.throws(() =>
    indexedSearchRequest(
      "primary",
      Array.from({ length: 8 }, (_, i) => String(i)),
      "query",
    ),
  );
  assert.equal(
    indexedSearchRequest(
      "primary",
      Array.from({ length: 7 }, (_, i) => String(i)),
      "query",
    ).index_ids?.length,
    8,
  );
});
