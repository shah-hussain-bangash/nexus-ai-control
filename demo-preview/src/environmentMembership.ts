import { environmentReason } from "./environmentSetup.ts";
import type { EnvironmentRecord } from "./environmentSetup";

export type EnvironmentMember = {
  id: string;
  name: string;
  role: string;
  active: boolean;
  revision: string;
};
export type AssignmentSnapshot = {
  items: EnvironmentMember[];
  candidates?: EnvironmentMember[];
  environment?: EnvironmentRecord;
  editing_enabled: boolean;
};
export type AssignmentCommand = "grant" | "revoke";
export function canChangeAssignment(
  snapshot: AssignmentSnapshot,
  member: EnvironmentMember,
  command: AssignmentCommand,
) {
  const environment = snapshot.environment;
  const pool = command === "grant" ? snapshot.candidates || [] : snapshot.items;
  return (
    !!environment &&
    snapshot.editing_enabled &&
    ["active", "preparing"].includes(environment.state) &&
    Number.isInteger(environment.version) &&
    environment.version > 0 &&
    !(environment.key === "staging" && member.role === "owner") &&
    (command !== "grant" || member.active) &&
    /^[a-f0-9]{64}$/.test(member.revision) &&
    pool.some((row) => row.id === member.id && row.revision === member.revision)
  );
}
export function assignmentPayload(
  snapshot: AssignmentSnapshot,
  member: EnvironmentMember,
  command: AssignmentCommand,
  note: string,
  reviewed: boolean,
) {
  if (!reviewed)
    throw new Error("Confirm that you reviewed the membership change.");
  if (!canChangeAssignment(snapshot, member, command))
    throw new Error("This membership action is unavailable. Refresh the list.");
  return {
    user_id: member.id,
    command,
    expected_version: snapshot.environment!.version,
    expected_member_revision: member.revision,
    note: environmentReason(note),
    reviewed: true as const,
  };
}
export function assignmentAcknowledged(
  value: unknown,
  request: ReturnType<typeof assignmentPayload>,
  key: string,
) {
  if (!value || typeof value !== "object") return false;
  const result = value as Record<string, unknown>;
  return (
    result.status === (request.command === "grant" ? "assigned" : "removed") &&
    result.member_id === request.user_id &&
    result.environment_key === key &&
    result.version === request.expected_version + 1 &&
    typeof result.sessions_revoked === "number" &&
    Number.isInteger(result.sessions_revoked) &&
    result.sessions_revoked >= 0 &&
    result.switching_enabled === false
  );
}
