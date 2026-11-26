import test from "node:test";
import assert from "node:assert/strict";
import { hybridSearchRequest } from "../src/hybridSearchRequest.ts";
const options = {
  neural: false,
  query: "Synthetic query",
  sources: [{ id: "source", version: 2 }],
  dimensions: 8,
  weight: 0.6,
  threshold: 0.15,
  top: 5,
  onePerDocument: false,
};
test("default search preserves the existing request fingerprint fields", () => {
  assert.deepEqual(hybridSearchRequest(options), {
    query: "Synthetic query",
    sources: [{ id: "source", version: 2 }],
    dimensions: 8,
    semantic_weight: 0.6,
    min_score: 0.15,
    top_k: 5,
  });
});
test("neural mode omits LSA controls and cannot supply server model configuration", () => {
  const body = hybridSearchRequest({
    ...options,
    neural: true,
    dimensions: 2,
    weight: 0.9,
    onePerDocument: true,
  });
  assert.deepEqual(body, {
    query: "Synthetic query",
    sources: [{ id: "source", version: 2 }],
    retrieval_mode: "local_neural",
    min_score: 0.15,
    top_k: 5,
    one_per_document: true,
  });
  assert.ok(!("embedding_model" in body) && !("embedding_digest" in body));
});
test("reviewed source versions are copied into the body used for intent and API", () => {
  const sources = [{ id: "source", version: 2 }];
  const body = hybridSearchRequest({ ...options, sources });
  sources[0].version = 3;
  assert.equal(body.sources[0].version, 2);
});
