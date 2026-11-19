import type { SessionContext } from "./sessionContext.ts";
import type { EnvironmentRecord } from "./environmentSetup.ts";
import { environmentReason } from "./environmentSetup.ts";
import { recoveryContextParts } from "./recoveryContext.ts";
export type EnvironmentChoice = { key: string; name: string; version: number };
export function canActivateEnvironment(
  row: EnvironmentRecord,
  current: string,
  enabled: boolean,
) {
  return (
    enabled &&
    row.key !== current &&
    row.key !== "staging" &&
    /^[a-z][a-z0-9-]{1,31}$/.test(row.key) &&
    row.state === "preparing" &&
    !row.human_runtime_enabled &&
    row.owner_assigned === true &&
    Number.isSafeInteger(row.version) &&
    row.version > 0
  );
}
export function activationPayload(
  row: EnvironmentRecord,
  current: string,
  enabled: boolean,
  note: string,
  reviewed: boolean,
) {
  if (!canActivateEnvironment(row, current, enabled) || reviewed !== true)
    throw Error(
      "Assign yourself as owner and review this activation before continuing.",
    );
  return {
    expected_version: row.version,
    note: environmentReason(note),
    reviewed: true,
  };
}
export function selectionPayload(
  context: SessionContext,
  choice: EnvironmentChoice,
  reviewed: boolean,
) {
  recoveryContextParts(
    context.workspace_id,
    context.user_id,
    context.environment,
  );
  if (
    reviewed !== true ||
    choice.key === context.environment ||
    !/^[a-z][a-z0-9-]{1,31}$/.test(choice.key) ||
    !Number.isSafeInteger(choice.version) ||
    choice.version < 1 ||
    !Number.isSafeInteger(context.revision) ||
    context.revision < 1 ||
    !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(context.binding_id)
  )
    throw Error("Refresh and review the target environment before switching.");
  return {
    workspace_id: context.workspace_id,
    environment: choice.key,
    expected_revision: context.revision,
    expected_binding_id: context.binding_id,
    expected_environment_version: choice.version,
    reviewed: true,
  };
}
