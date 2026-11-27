import test from "node:test";
import assert from "node:assert/strict";
import {
  modelSpendingRequest,
  formatMicroUsd,
  microUsdInput,
} from "../src/modelSpendingRequest.ts";
import { liveIntentScope } from "../src/liveIntent.ts";
test("reviewed policy pins model versions and omits deliberately unassigned caps", () => {
  assert.deepEqual(
    modelSpendingRequest(
      2,
      true,
      [
        { id: "one", version: 3 },
        { id: "two", version: 4 },
      ],
      { one: "0.000024", two: "" },
      " Reviewed cap. ",
    ),
    {
      expected_version: 2,
      require_model_caps: true,
      caps: [
        {
          model_id: "one",
          expected_model_version: 3,
          monthly_limit_micro_usd: 24,
        },
      ],
      note: "Reviewed cap.",
    },
  );
});
test("zero is an explicit cap and large aggregate displays retain every micro-unit", () => {
  assert.equal(
    modelSpendingRequest(
      0,
      false,
      [{ id: "one", version: 1 }],
      { one: "0" },
      "note",
    ).caps[0].monthly_limit_micro_usd,
    0,
  );
  assert.equal(formatMicroUsd("9007199254740993"), "$9,007,199,254.740993");
  assert.equal(microUsdInput(24), "0.000024");
});
test("spending policy recovery namespace never overlaps another actor/environment or billing review", () => {
  const scope = liveIntentScope(
    "model-spend-policy",
    "org",
    "owner",
    "staging",
  );
  for (const other of [
    liveIntentScope("billing-review", "org", "owner", "staging"),
    liveIntentScope("model-spend-policy", "org", "other", "staging"),
    liveIntentScope("model-spend-policy", "other", "owner", "staging"),
    liveIntentScope("model-spend-policy", "org", "owner", "production"),
  ])
    assert.notEqual(scope, other);
});
