import type { InterfaceModule } from "./interfaceDesign.ts";
import { uiInputs, type UiRecord } from "./productExperience.ts";
export const HANDOFF_LIMIT = 8 * 1024 * 1024;
export const UI_RECORD_LIMIT = 300;
export const reviewCriteria = [
  {
    id: "journey",
    label: "I reviewed configuration, confirmation, result and evidence.",
  },
  {
    id: "access",
    label: "I reviewed the intended roles and denied-access behavior.",
  },
  {
    id: "recovery",
    label:
      "I reviewed validation, dependency, timeout and stale-revision states.",
  },
  {
    id: "handoff",
    label: "I reviewed the service handoff and implementation boundaries.",
  },
] as const;
export type ReviewChecks = Record<string, string[]>;
export type HandoffScope = { organization: string; user: string };
export type ImportedHandoff = {
  records: UiRecord[];
  reviewed: string[];
  checks: ReviewChecks;
  legacy: boolean;
  sourceRelease: string;
};
const criteria = reviewCriteria.map((x) => x.id) as string[];
function invalid(
  message = "This file is not a valid NEXUS UI handoff.",
): never {
  throw Error(message);
}
function object(value: any) {
  return value && typeof value === "object" && !Array.isArray(value);
}
function text(value: any, min: number, max: number) {
  return (
    typeof value === "string" &&
    value.trim().length >= min &&
    value.length <= max
  );
}
export function reviewComplete(checks: ReviewChecks, id: string) {
  return criteria.every((c) => checks[id]?.includes(c));
}
export function parseHandoff(
  raw: string,
  modules: InterfaceModule[],
  scope: HandoffScope,
): ImportedHandoff {
  if (new TextEncoder().encode(raw).byteLength > HANDOFF_LIMIT)
    invalid(
      "The UI handoff exceeds 8 MiB. Export review-only metadata or fewer examples.",
    );
  let value: any;
  try {
    value = JSON.parse(raw, (key, v) => {
      if (["__proto__", "constructor", "prototype"].includes(key))
        invalid("Unsafe JSON object key.");
      return v;
    });
  } catch {
    invalid("Choose a valid JSON UI handoff without unsafe object keys.");
  }
  if (
    !object(value) ||
    value.backend_activated !== false ||
    value.production_accepted !== false ||
    !["0.14.0", "0.15.0", "0.16.0"].includes(value.release)
  )
    invalid();
  const legacy = value.release === "0.14.0";
  if (
    !legacy &&
    (value.format !== "nexus-ui-review" ||
      value.schema !== 1 ||
      !object(value.workspace_scope) ||
      value.workspace_scope.organization !== scope.organization ||
      value.workspace_scope.user !== scope.user)
  )
    invalid(
      "This handoff belongs to a different account/workspace or uses an unsupported format.",
    );
  if (
    !Array.isArray(value.modules) ||
    value.modules.length !== modules.length ||
    !Array.isArray(value.records) ||
    value.records.length > UI_RECORD_LIMIT
  )
    invalid(
      "Use the current complete catalog and at most 300 synthetic examples.",
    );
  const features = new Map(
      modules.flatMap((m) => m.features.map((f) => [f.id, f] as const)),
    ),
    seenModules = new Set<string>(),
    seenFeatures = new Set<string>(),
    requested: string[] = [];
  for (const m of value.modules) {
    const expected = modules.find((x) => x.id === m?.id);
    if (
      !expected ||
      seenModules.has(m.id) ||
      !Array.isArray(m.features) ||
      m.features.length !== expected.features.length
    )
      invalid("Duplicate, missing or unknown workspace in this handoff.");
    seenModules.add(m.id);
    for (const f of m.features) {
      if (
        !object(f) ||
        !expected.features.some((x) => x.id === f.id) ||
        seenFeatures.has(f.id) ||
        typeof f.ui_reviewed !== "boolean"
      )
        invalid("Duplicate, missing or unknown function in this handoff.");
      seenFeatures.add(f.id);
      if (f.ui_reviewed) requested.push(f.id);
    }
  }
  const checks: ReviewChecks = {};
  if (!legacy) {
    if (
      !object(value.review_checks) ||
      Object.keys(value.review_checks).length > features.size
    )
      invalid("Invalid review checklist.");
    for (const [id, list] of Object.entries(value.review_checks)) {
      if (
        !features.has(id) ||
        !Array.isArray(list) ||
        list.length > criteria.length ||
        new Set(list).size !== list.length ||
        !list.every((x) => criteria.includes(x))
      )
        invalid("Unknown or duplicate review criterion.");
      checks[id] = [...list] as string[];
    }
    if (requested.some((id) => !reviewComplete(checks, id)))
      invalid(
        "Reviewed functions must include all four manual checklist criteria.",
      );
  }
  const ids = new Set<string>();
  const records: UiRecord[] = value.records.map((r: any) => {
    const f = features.get(r?.feature);
    if (
      !f ||
      !text(r.id, 1, 64) ||
      !/^[A-Za-z0-9_-]+$/.test(r.id) ||
      ids.has(r.id) ||
      !text(r.name, 1, 120) ||
      !text(r.owner, 1, 120) ||
      !object(r.values) ||
      !Number.isInteger(r.version) ||
      r.version < 1 ||
      r.version > 10000 ||
      ![
        "draft",
        "in_review",
        "approved",
        "changes_requested",
        "rejected",
        "outcome_unknown",
      ].includes(r.status) ||
      !Array.isArray(r.events) ||
      r.events.length > 50
    )
      invalid(
        "A UI example contains an invalid scope, revision or event history.",
      );
    ids.add(r.id);
    const keys = f.fields.map((x) => x.id).sort();
    if (
      Object.keys(r.values).sort().join("|") !== keys.join("|") ||
      !keys.every((k) => typeof r.values[k] === "string")
    )
      invalid("UI example fields do not match the current function.");
    const row: UiRecord = {
      id: r.id,
      feature: r.feature,
      name: r.name,
      owner: r.owner,
      values: Object.fromEntries(keys.map((k) => [k, r.values[k]])),
      version: r.version,
      status: r.status,
      events: r.events.map((e: any) => {
        if (
          !object(e) ||
          !text(e.at, 1, 50) ||
          !Number.isFinite(Date.parse(e.at)) ||
          !["submit", "approve", "rework", "reject", "reconcile"].includes(
            e.label,
          ) ||
          !text(e.note, 5, 500)
        )
          invalid("A UI event is invalid.");
        return { at: e.at, label: e.label, note: e.note };
      }),
    };
    if (Object.keys(uiInputs(f, row)).length)
      invalid("A UI example fails the current field validation.");
    return row;
  });
  return {
    records,
    checks,
    reviewed: legacy ? [] : requested,
    legacy,
    sourceRelease: value.release,
  };
}
export function makeHandoff(
  modules: InterfaceModule[],
  records: UiRecord[],
  reviewed: string[],
  checks: ReviewChecks,
  scope: HandoffScope,
  includeExamples = true,
) {
  const data = {
    format: "nexus-ui-review",
    schema: 1,
    release: "0.16.0",
    scope: "UI-only review; not deployment acceptance",
    workspace_scope: scope,
    exported_at: new Date().toISOString(),
    modules: modules.map((m) => ({
      id: m.id,
      title: m.title,
      features: m.features.map((f) => ({
        id: f.id,
        title: f.title,
        ui_reviewed: reviewed.includes(f.id),
      })),
    })),
    review_checks: checks,
    records: includeExamples ? records : [],
    backend_activated: false,
    production_accepted: false,
  };
  const raw = JSON.stringify(data, null, 2);
  parseHandoff(raw, modules, scope);
  return data;
}
