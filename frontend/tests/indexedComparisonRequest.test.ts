import test from "node:test";
import assert from "node:assert/strict";
import { indexedComparisonRequest } from "../src/indexedComparisonRequest.ts";
test("comparison preserves baseline/candidate order and submits only saved IDs", () => {
  assert.deepEqual(indexedComparisonRequest("baseline", "candidate"), {
    baseline_id: "baseline",
    candidate_id: "candidate",
  });
  assert.deepEqual(indexedComparisonRequest("candidate", "baseline"), {
    baseline_id: "candidate",
    candidate_id: "baseline",
  });
});
test("missing or identical review selections cannot request a misleading comparison", () => {
  for (const [left, right] of [
    ["", "candidate"],
    ["baseline", ""],
    ["same", "same"],
  ])
    assert.throws(() => indexedComparisonRequest(left, right));
});
