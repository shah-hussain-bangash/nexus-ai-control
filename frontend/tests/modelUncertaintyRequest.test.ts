import test from "node:test";
import assert from "node:assert/strict";
import { modelUncertaintyRequest } from "../src/modelUncertaintyRequest.ts";
import { liveIntentScope } from "../src/liveIntent.ts";
const models = [{ id: "model-route", version: 3, status: "validated" }],
  note = "Reviewed route failure admission limits.";
test("route failure request pins current model versions and blank removes the guard", () => {
  assert.deepEqual(
    modelUncertaintyRequest(2, models, { "model-route": "1" }, note),
    {
      expected_version: 2,
      rules: [
        {
          model_id: "model-route",
          expected_model_version: 3,
          unknown_limit: 1,
        },
      ],
      note,
    },
  );
  assert.deepEqual(
    modelUncertaintyRequest(2, models, { "model-route": "" }, note).rules,
    [],
  );
  assert.equal(
    modelUncertaintyRequest(2, models, { "model-route": "100" }, note).rules[0]
      .unknown_limit,
    100,
  );
});
test("invalid limits and unavailable routes cannot enter a reviewed request", () => {
  for (const value of ["0", "101", "1.5", "1e1", "true", "01", " 1 "])
    assert.throws(() =>
      modelUncertaintyRequest(0, models, { "model-route": value }, note),
    );
  assert.throws(() =>
    modelUncertaintyRequest(0, models, { "foreign-route": "1" }, note),
  );
  assert.throws(() =>
    modelUncertaintyRequest(
      0,
      [{ ...models[0], status: "archived" }],
      { "model-route": "1" },
      note,
    ),
  );
  assert.throws(() => modelUncertaintyRequest(0, models, {}, "   "));
});
test("route failure recovery is separate from spend policy, actor and environment", () => {
  const scope = liveIntentScope(
    "model-uncertainty-policy",
    "org",
    "owner",
    "staging",
  );
  assert.notEqual(
    scope,
    liveIntentScope("model-spend-policy", "org", "owner", "staging"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("model-uncertainty-policy", "org", "other", "staging"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("model-uncertainty-policy", "org", "owner", "development"),
  );
});
