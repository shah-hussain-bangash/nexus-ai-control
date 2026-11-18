import {validateFunctionPlan,type FunctionDefinition,type FunctionPlan} from "./functionPlans.ts";
import {validateOperationalState} from "./operationalModel.ts";
import type {OperationSpec,OperationalState} from "./operationalModel";
export type InterfaceField = {
  id: string;
  label: string;
  type: "text" | "url" | "reference" | "select" | "number" | "toggle" | "list";
  default: any;
  section: string;
  required: boolean;
  options?: string[];
  min?: number;
  max?: number;
};
export type InterfaceModule = {
  runtime_state?: string;
  runtime_note?: string;
  features: FunctionDefinition[];
  operations: OperationSpec;
  record_columns: {
    id: string;
    label: string;
    default: string;
    type: string;
  }[];
  record_states: string[];
  record_boundary: string;
  id: string;
  title: string;
  area: string;
  tagline: string;
  description: string;
  icon: string;
  existing_view: string;
  fields: InterfaceField[];
  stages: { id: string; label: string; description: string }[];
  actions: {
    id: string;
    label: string;
    method: string;
    path: string;
    implementation: string;
    request_fields: string[];
    response_states: string[];
    errors: string[];
    idempotency_required: boolean;
    description: string;
  }[];
  criteria: { id: string; label: string }[];
  failure_states: string[];
  activation_steps: string[];
  sample_name: string;
  permission: string;
};
export type InterfaceDraft = {
  id?: string;
  name: string;
  description: string;
  status?: string;
  version?: number;
  config: {
    function_plans?: FunctionPlan[];
    operational_state?: OperationalState;
    module: string;
    values: Record<string, any>;
    phase: string;
    ui_checks: Record<string, boolean>;
    surface_rows?: {
      id: string;
      state: string;
      values: Record<string, string>;
    }[];
  };
};
export function freshInterface(spec: InterfaceModule): InterfaceDraft {
  return {
    name: spec.title + " · new plan",
    description: spec.description,
    config: {
      module: spec.id,
      values: Object.fromEntries(
        spec.fields.map((f) => [f.id, structuredClone(f.default)]),
      ),
      phase: "planned",
      ui_checks: {},
      surface_rows: [],
    },
  };
}
export function interfaceFingerprint(draft: InterfaceDraft) {
  return JSON.stringify({
    name: draft.name,
    description: draft.description,
    config: draft.config,
  });
}
export function validateInterface(
  spec: InterfaceModule,
  draft: InterfaceDraft,
) {
  const errors: Record<string, string> = {};
  if (draft.name.trim().length < 2 || draft.name.length > 120)
    errors.name = "Use a plan name between 2 and 120 characters.";
  for (const f of spec.fields) {
    const v = draft.config.values[f.id];
    if (f.type === "toggle") {
      if (typeof v !== "boolean") errors[f.id] = "Select a boolean value.";
    } else if (f.type === "number") {
      if (
        typeof v !== "number" ||
        !Number.isFinite(v) ||
        v < (f.min ?? 0) ||
        v > (f.max ?? Infinity)
      )
        errors[f.id] = `Use a value between ${f.min} and ${f.max}.`;
    } else if (f.type === "list") {
      if (
        !Array.isArray(v) ||
        v.length < 1 ||
        v.length > 30 ||
        v.some((x) => typeof x !== "string" || !x.trim() || x.length > 100)
      )
        errors[f.id] = "Use 1–30 nonempty comma-separated values.";
    } else {
      if (typeof v !== "string" || !v.trim() || v.length > 1000) {
        errors[f.id] = "Enter a nonempty value of at most 1,000 characters.";
        continue;
      }
      if (
        f.type === "reference" &&
        !/^(env:[A-Z][A-Z0-9_]{2,70}|secret:\/\/[A-Za-z0-9/_-]{3,180})$/.test(v)
      )
        errors[f.id] =
          "Use env:VARIABLE_NAME or secret://reference; never paste a secret.";
      if (f.type === "select" && !f.options?.includes(v))
        errors[f.id] = "Select a defined option.";
      if (f.type === "url") {
        try {
          const url = new URL(v);
          if (
            url.protocol !== "https:" ||
            url.username ||
            url.password ||
            url.search ||
            url.hash ||
            (url.port && url.port !== "443")
          )
            errors[f.id] =
              "Use a credential-free HTTPS URL without query or fragment.";
        } catch {
          errors[f.id] = "Enter a valid HTTPS endpoint.";
        }
      }
    }
  }
  if (
    draft.config.phase !== "planned" &&
    !spec.criteria.every((c) => draft.config.ui_checks[c.id])
  )
    errors.phase =
      "Review every interface criterion in the Acceptance tab before advancing the plan phase.";
  if(draft.config.operational_state){try{validateOperationalState(spec.operations,draft.config.operational_state)}catch(e){errors.operational_state=(e as Error).message}}
  const ids=new Set<string>();
  for(const plan of draft.config.function_plans||[]){const f=spec.features.find(f=>f.id===plan.feature_id);if(!f||ids.has(plan.feature_id)){errors.function_plans="Use distinct functions from the current module.";break;}ids.add(plan.feature_id);if(Object.keys(validateFunctionPlan(f,plan)).length)errors.function_plans="Correct function screen controls and UI review criteria before saving.";}
  return errors;
}
export function plannedRequest(spec: InterfaceModule, draft: InterfaceDraft) {
  return {
    resource_id: "RESOURCE_ID",
    expected_version: draft.version || 1,
    reason: "Reviewed implementation request",
    configuration_revision: draft.version || 1,
    module: spec.id,
    configuration: draft.config.values,
  };
}
