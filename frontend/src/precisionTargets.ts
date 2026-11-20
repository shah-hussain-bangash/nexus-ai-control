export function assertPrecisionTargets(
  cases: readonly {
    expectation: string;
    minimum_precision_percent?: unknown;
  }[],
) {
  for (const item of cases) {
    const minimum = item.minimum_precision_percent;
    if (minimum === undefined) continue;
    if (item.expectation !== "retrieve")
      throw new Error(
        "Precision targets apply only to expected-source retrieval cases.",
      );
    if (
      typeof minimum !== "number" ||
      !Number.isInteger(minimum) ||
      minimum < 0 ||
      minimum > 100
    )
      throw new Error("Use a whole-number precision target from 0 to 100.");
  }
}
