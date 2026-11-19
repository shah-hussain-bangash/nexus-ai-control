import type { EnvironmentRecord } from "./environmentSetup.ts";
import { environmentReason } from "./environmentSetup.ts";
export type RuntimeCommand = "pause" | "resume";
export function canControlRuntime(
  row: EnvironmentRecord,
  current: string,
  enabled: boolean,
  command: RuntimeCommand,
) {
  return (
    enabled &&
    current === "staging" &&
    row.owner_assigned === true &&
    /^[a-z][a-z0-9-]{1,31}$/.test(row.key) &&
    row.key !== "staging" &&
    Number.isSafeInteger(row.version) &&
    row.version > 0 &&
    row.state === (command === "pause" ? "active" : "suspended") &&
    Number.isSafeInteger(row.selected_sessions) &&
    row.selected_sessions! >= 0 &&
    !!row.unfinished_work &&
    ["actions", "durable_runs", "ingestion_jobs", "inference_calls"].every(
      (key) => row.unfinished_work![key] === 0,
    ) &&
    Object.values(row.unfinished_work).every((count) => count === 0)
  );
}
export function runtimeControlPayload(
  row: EnvironmentRecord,
  current: string,
  enabled: boolean,
  command: RuntimeCommand,
  note: string,
  reviewed: boolean,
) {
  if (!reviewed || !canControlRuntime(row, current, enabled, command))
    throw Error(
      "Refresh and review the idle environment and session sign-out effect before continuing.",
    );
  return {
    command,
    expected_version: row.version,
    expected_selected_sessions: row.selected_sessions!,
    note: environmentReason(note),
    reviewed: true,
  };
}
