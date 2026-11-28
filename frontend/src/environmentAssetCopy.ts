import { environmentReason } from "./environmentSetup.ts";
export type CopyAsset = {
  id: string;
  kind: string;
  name: string;
  description: string;
  status: string;
  version: number;
  config: Record<string, unknown>;
};
export type CopyTarget = { key: string; name: string; version: number };
export type ReferenceChoice = {
  id: string;
  kind: string;
  name: string;
  version: number;
};
export type ReferenceMapping = {
  node_id: string;
  target_asset_id: string;
  expected_target_asset_version: number;
};
export function copyResetFields(kind: string): string[] {
  return kind === "model"
    ? ["credential_ref"]
    : kind === "connector"
      ? ["credential_ref", "scopes", "read_only"]
      : [];
}
export function routeDraftPreview(asset: CopyAsset) {
  if (!["model", "connector"].includes(asset.kind))
    throw Error("Choose a model or connector for this preview.");
  return {
    ...asset.config,
    credential_ref: "",
    ...(asset.kind === "connector" ? { scopes: [], read_only: true } : {}),
  };
}
export function workflowReferences(asset: CopyAsset) {
  if (asset.kind !== "workflow") return [];
  if (!Array.isArray(asset.config.nodes))
    throw Error(
      "Refresh the workflow configuration before mapping references.",
    );
  const kinds: Record<string, string> = {
    retrieve: "knowledge",
    prompt: "prompt",
    guardrail: "guardrail",
  };
  const refs = asset.config.nodes
    .filter((n: any) => n.ref_id)
    .map((n: any) => {
      if (
        !/^[a-zA-Z0-9_-]{1,40}$/.test(n.id) ||
        !kinds[n.kind] ||
        !Number.isSafeInteger(n.ref_version) ||
        n.ref_version < 1
      )
        throw Error(
          "Validate and refresh every pinned workflow reference before copying.",
        );
      return {
        node_id: n.id as string,
        kind: kinds[n.kind],
        source_asset_id: n.ref_id as string,
        source_version: n.ref_version as number,
        label: String(n.label || n.id),
      };
    });
  if (new Set(refs.map((ref) => ref.node_id)).size !== refs.length)
    throw Error("Workflow step identifiers must be unique.");
  return refs;
}
export function copyPayload(
  source: string,
  asset: CopyAsset,
  target: CopyTarget,
  name: string,
  note: string,
  reviewed: boolean,
  mappings: ReferenceMapping[] = [],
) {
  if (
    !reviewed ||
    !["prompt", "guardrail", "workflow", "model", "connector"].includes(
      asset.kind,
    ) ||
    asset.status !== "validated" ||
    !asset.id ||
    !Number.isSafeInteger(asset.version) ||
    asset.version < 1 ||
    !/^[a-z][a-z0-9-]{1,31}$/.test(source) ||
    target.key === source ||
    !/^[a-z][a-z0-9-]{1,31}$/.test(target.key) ||
    !Number.isSafeInteger(target.version) ||
    target.version < 1
  )
    throw Error(
      "Refresh and review the validated source and active target before copying.",
    );
  name = name.trim();
  const refs = workflowReferences(asset);
  if (
    new Set(mappings.map((m) => m.node_id)).size !== mappings.length ||
    mappings.length !== refs.length ||
    refs.some((ref) => !mappings.some((m) => m.node_id === ref.node_id)) ||
    mappings.some(
      (m) =>
        !m.target_asset_id ||
        m.target_asset_id.length > 64 ||
        !Number.isSafeInteger(m.expected_target_asset_version) ||
        m.expected_target_asset_version < 1,
    )
  )
    throw Error(
      "Map every workflow reference exactly once to a current target design.",
    );
  if (
    name.length < 2 ||
    name.length > 120 ||
    /[\u0000-\u001f\u007f]/.test(name)
  )
    throw Error("Use a visible draft name of 2–120 characters.");
  return {
    source_asset_id: asset.id,
    expected_source_version: asset.version,
    target_environment: target.key,
    expected_target_version: target.version,
    name,
    note: environmentReason(note),
    reviewed: true,
    ...(mappings.length ? { reference_mappings: mappings } : {}),
  };
}
export function copyOutcome(value: any, source: string) {
  if (
    !value ||
    !/^[a-f0-9]{64}$/.test(value.id) ||
    value.source_environment !== source ||
    !["copied", "cancelled"].includes(value.status) ||
    (value.status === "copied" &&
      (!value.target_asset_id ||
        !value.source_asset_id ||
        !Number.isSafeInteger(value.source_version) ||
        value.source_version < 1 ||
        value.target_environment === source ||
        !/^[a-z][a-z0-9-]{1,31}$/.test(value.target_environment) ||
        value.target_created_version !== 1 ||
        !["prompt", "guardrail", "workflow", "model", "connector"].includes(
          value.kind,
        ) ||
        (copyResetFields(value.kind).length > 0 &&
          (!Array.isArray(value.reset_fields) ||
            value.reset_fields.length !== copyResetFields(value.kind).length ||
            copyResetFields(value.kind).some(
              (field, index) => value.reset_fields[index] !== field,
            )))))
  )
    throw Error(
      "The copy result could not be confirmed. Recover the saved request before continuing.",
    );
  return value as {
    id: string;
    status: string;
    target_environment?: string;
    target_asset_id?: string;
    name?: string;
  };
}
