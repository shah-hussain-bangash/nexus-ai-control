import { validateOperation, type OperationField } from "./operationalModel.ts";
export type FunctionDefinition = {
  working_view?: string;
  implementation_note?: string;
  id: string;
  title: string;
  summary: string;
  priority: string;
  roles: string[];
  fields: OperationField[];
  steps: string[];
  actions: string[];
  planned_path: string;
  entities: string[];
  dependencies: string[];
  acceptance: string[];
  states: string[];
  runtime_activated: false;
};
export type FunctionPlan = {
  feature_id: string;
  owner: string;
  phase: "planned" | "ui_reviewed" | "backend_in_progress" | "staging_review";
  values: Record<string, string>;
  checks: Record<string, boolean>;
  notes: string;
};
export const checkKeys = ["scope", "access", "feedback", "handoff"];
export function defaultFunctionPlan(f: FunctionDefinition): FunctionPlan {
  return {
    feature_id: f.id,
    owner: "Platform review team",
    phase: "planned",
    values: Object.fromEntries(f.fields.map((x) => [x.id, x.default])),
    checks: Object.fromEntries(checkKeys.map((k) => [k, false])),
    notes: "",
  };
}
export function validateFunctionPlan(f: FunctionDefinition, p: FunctionPlan) {
  const errors: Record<string, string> = {};
  if (p.feature_id !== f.id)
    errors.feature_id = "Choose a function from this module.";
  if (!p.owner.trim() || p.owner.length > 120)
    errors.owner = "Enter a responsible owner of 1–120 characters.";
  if (p.notes.length > 2000) errors.notes = "Use at most 2,000 characters.";
  if (
    ![
      "planned",
      "ui_reviewed",
      "backend_in_progress",
      "staging_review",
    ].includes(p.phase)
  )
    errors.phase = "Choose a valid planning phase.";
  if (p.phase !== "planned" && !checkKeys.every((k) => p.checks[k]))
    errors.phase =
      "Review all four UI criteria before advancing the planning phase.";
  if (
    Object.keys(p.values).sort().join("|") !==
    f.fields
      .map((x) => x.id)
      .sort()
      .join("|")
  )
    errors.values = "Use exactly the defined function fields.";
  if (Object.keys(p.checks).some((k) => !checkKeys.includes(k)))
    errors.checks = "Unknown UI review criterion.";
  Object.assign(
    errors,
    validateOperation({ fields: f.fields } as any, {
      id: "function-review",
      title: f.title.slice(0, 120),
      owner: p.owner,
      state: "draft",
      attributes: p.values,
    }),
  );
  return errors;
}
export function functionPreview(
  f: FunctionDefinition,
  scenario: string,
  action: string,
  note: string,
) {
  if (!f.states.includes(scenario))
    throw Error("Unknown screen-state scenario.");
  if (!f.actions.includes(action))
    throw Error("Choose a defined function action.");
  if (!note.trim() || note.length > 500)
    throw Error("Enter a review note of 1–500 characters.");
  return {
    feature_id: f.id,
    action,
    scenario,
    note: note.trim(),
    runtime_activated: false,
    provider_calls: 0,
    business_effects: 0,
    steps: f.steps.map((label, i) => ({
      label,
      state:
        scenario === "ready"
          ? "reviewed"
          : scenario === "empty" || scenario === "loading"
            ? "not_executed"
            : i < 2
              ? "reviewed"
              : i === 2
                ? "simulated_stop"
                : "not_executed",
    })),
    boundary:
      "UI state review only. No live command, access grant, upload, provider request or deployment occurred.",
  };
}
