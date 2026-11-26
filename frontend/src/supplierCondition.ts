import type { procurementRun } from "./liveRequests";

export function withSupplierCondition(
  body: ReturnType<typeof procurementRun>,
  values: string,
) {
  const ids = values.split(",").map((value) => value.trim());
  if (
    ids.length < 1 ||
    ids.length > 10 ||
    new Set(ids).size !== ids.length ||
    ids.some((id) => !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(id))
  )
    throw Error(
      "Enter one to ten unique supplier references, separated by commas.",
    );
  if (
    body.steps[1]?.request?.action !== "supplier:read" ||
    !body.steps.some((step) => step.request?.action === "purchase:create") ||
    body.steps.at(-1)?.kind !== "output"
  )
    throw Error("This condition requires the supervised procurement workflow.");
  return {
    ...body,
    steps: [
      ...body.steps.slice(0, 2),
      {
        kind: "condition",
        label: "Check supplier allowlist",
        condition: {
          kind: "supplier_allowlist",
          source_step: 1,
          supplier_ids: ids,
        },
      },
      ...body.steps.slice(2),
    ],
  };
}
