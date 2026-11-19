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
export function copyPayload(
  source: string,
  asset: CopyAsset,
  target: CopyTarget,
  name: string,
  note: string,
  reviewed: boolean,
) {
  if (
    !reviewed ||
    !["prompt", "guardrail"].includes(asset.kind) ||
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
        !["prompt", "guardrail"].includes(value.kind)))
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
