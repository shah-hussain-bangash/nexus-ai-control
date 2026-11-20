import test from "node:test";
import assert from "node:assert/strict";
import { assertPrecisionTargets } from "../src/precisionTargets.ts";

test("legacy and disabled targets preserve the original request shape", () => {
  const cases = [{ expectation: "retrieve" }, { expectation: "no_results" }];
  const original = JSON.stringify(cases);
  assertPrecisionTargets(cases);
  assert.equal(JSON.stringify(cases), original);
  const disabled = {
    expectation: "retrieve",
    minimum_precision_percent: undefined,
  };
  assertPrecisionTargets([disabled]);
  assert.equal(JSON.stringify(disabled), '{"expectation":"retrieve"}');
});
test("whole percentage targets including zero and one hundred remain explicit", () => {
  for (const minimum of [0, 33, 50, 100]) {
    const item = {
      expectation: "retrieve",
      minimum_precision_percent: minimum,
    };
    assertPrecisionTargets([item]);
    assert.equal(item.minimum_precision_percent, minimum);
  }
});
test("invalid or unfinished enabled inputs cannot become a saved request", () => {
  for (const minimum of [
    NaN,
    Infinity,
    -Infinity,
    -1,
    101,
    50.5,
    "50",
    null,
    true,
  ])
    assert.throws(
      () =>
        assertPrecisionTargets([
          { expectation: "retrieve", minimum_precision_percent: minimum },
        ]),
      /whole-number/,
    );
  assert.throws(
    () =>
      assertPrecisionTargets([
        { expectation: "no_results", minimum_precision_percent: 0 },
      ]),
    /expected-source/,
  );
});
