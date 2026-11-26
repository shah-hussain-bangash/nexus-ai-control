import test from "node:test";
import assert from "node:assert/strict";
import { procurementRun } from "../src/liveRequests.ts";
import { withSupplierCondition } from "../src/supplierCondition.ts";

function workflow() {
  return procurementRun(
    "agent",
    "lookup",
    "purchase",
    "procurement",
    "SUP-104",
    "12500.00",
    "Reviewed purpose",
  );
}
test("condition pins source and allowlist while preserving review and purchase steps", () => {
  const original = workflow(),
    result = withSupplierCondition(original, "SUP-104, SUP-205");
  assert.equal(original.steps.length, 5);
  assert.equal(result.steps.length, 6);
  assert.deepEqual(result.steps[2].condition, {
    kind: "supplier_allowlist",
    source_step: 1,
    supplier_ids: ["SUP-104", "SUP-205"],
  });
  assert.equal(result.steps[3].kind, "approval");
  assert.equal(result.steps[4].request.action, "purchase:create");
});
test("invalid, duplicate, empty and oversized allowlists are rejected", () => {
  for (const value of [
    "",
    "SUP-104,SUP-104",
    "../x",
    "SUP-104,",
    Array.from({ length: 11 }, (_, i) => "SUP-" + i).join(","),
  ])
    assert.throws(() => withSupplierCondition(workflow(), value));
  assert.throws(() =>
    withSupplierCondition(
      procurementRun("agent", "lookup", "", "lookup", "SUP-104", "", ""),
      "SUP-104",
    ),
  );
});
