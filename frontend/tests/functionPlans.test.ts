import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  defaultFunctionPlan,
  validateFunctionPlan,
  functionPreview,
  checkKeys,
  type FunctionDefinition,
} from "../src/functionPlans.ts";
const modules = JSON.parse(
  readFileSync(
    new URL("../../backend/nexus/interface_catalog.json", import.meta.url),
    "utf8",
  ),
).modules;
const features = modules.flatMap(
  (m: any) => m.features,
) as FunctionDefinition[];
test("all 216 function screens have valid domain controls, role guidance, states and handoff", () => {
  assert.equal(features.length, 216);
  assert.equal(new Set(features.map((f) => f.id)).size, 216);
  for (const f of features) {
    assert.deepEqual(validateFunctionPlan(f, defaultFunctionPlan(f)), {});
    assert.equal(f.fields.length, 3);
    assert.equal(f.states.length, 8);
    assert.equal(f.steps.length, 6);
    assert.equal(f.actions.length, 3);
    assert.equal(f.acceptance.length, 4);
    assert.ok(f.planned_path.startsWith("/v1/planned/"));
    assert.equal(f.runtime_activated, false);
  }
});
test("UI review phase requires manual acceptance and remains a planning phase", () => {
  const f = features[0],
    plan = defaultFunctionPlan(f);
  plan.phase = "ui_reviewed";
  assert.ok(validateFunctionPlan(f, plan).phase);
  plan.checks = Object.fromEntries(checkKeys.map((k) => [k, true]));
  assert.deepEqual(validateFunctionPlan(f, plan), {});
});
test("every function action and screen state has an effect-free preview", () => {
  for (const f of features)
    for (const state of f.states)
      for (const action of f.actions) {
        const p = functionPreview(
          f,
          state,
          action,
          "Reviewed synthetic UI flow",
        );
        assert.equal(p.runtime_activated, false);
        assert.equal(p.provider_calls, 0);
        assert.equal(p.business_effects, 0);
        if (state === "loading" || state === "empty")
          assert.ok(p.steps.every((s) => s.state === "not_executed"));
        else if (state !== "ready")
          assert.equal(p.steps[2].state, "simulated_stop");
      }
});
test("unknown actions, blank review notes and unknown scenarios are rejected", () => {
  const f = features[0];
  assert.throws(() => functionPreview(f, "unknown", f.actions[0], "Reviewed"));
  assert.throws(() => functionPreview(f, "ready", "unknown", "Reviewed"));
  assert.throws(() => functionPreview(f, "ready", f.actions[0], ""));
});
test("secret references and percentage boundaries validate before saving", () => {
  const secret = features.find((f) =>
      f.fields.some((x) => x.type === "reference"),
    )!,
    sp = defaultFunctionPlan(secret);
  sp.values[secret.fields.find((x) => x.type === "reference")!.id] =
    "raw-token";
  assert.ok(Object.keys(validateFunctionPlan(secret, sp)).length);
  const percent = features.find((f) =>
      f.fields.some((x) => x.type === "number" && x.max === 100),
    )!,
    np = defaultFunctionPlan(percent);
  np.values[percent.fields.find((x) => x.type === "number")!.id] = "101";
  assert.ok(Object.keys(validateFunctionPlan(percent, np)).length);
});
