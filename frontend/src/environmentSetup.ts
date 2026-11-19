export type EnvironmentRecord = {
  key: string;
  name: string;
  state: string;
  version: number;
  human_runtime_enabled: boolean;
  owner_assigned?: boolean;
};
export type EnvironmentCommand = "archive" | "restore";
const validKey = /^[a-z][a-z0-9-]{1,31}$/;
const controls = /[\u0000-\u001f\u007f]/;
export function environmentReason(value: string) {
  const note = value.trim();
  if (note.length < 5 || note.length > 500 || controls.test(note))
    throw new Error("Enter a reason of 5–500 characters on one line.");
  return note;
}
export function environmentCreatePayload(
  key: string,
  name: string,
  note: string,
) {
  key = key.trim();
  name = name.trim();
  if (!validKey.test(key))
    throw new Error(
      "Use a key of 2–32 lowercase letters, numbers or hyphens, starting with a letter.",
    );
  if (name.length < 2 || name.length > 80 || controls.test(name))
    throw new Error("Enter a name of 2–80 characters on one line.");
  return { key, name, note: environmentReason(note) };
}
export function canControlEnvironment(
  row: EnvironmentRecord,
  current: string,
  command: EnvironmentCommand,
) {
  return (
    validKey.test(row.key) &&
    row.key !== current &&
    row.key !== "staging" &&
    !row.human_runtime_enabled &&
    Number.isInteger(row.version) &&
    row.version > 0 &&
    row.state === (command === "archive" ? "preparing" : "archived")
  );
}
export function environmentControlPayload(
  row: EnvironmentRecord,
  current: string,
  command: EnvironmentCommand,
  note: string,
) {
  if (!canControlEnvironment(row, current, command))
    throw new Error(
      "This action is unavailable. Refresh the environment list.",
    );
  return {
    command,
    expected_version: row.version,
    note: environmentReason(note),
  };
}
export function environmentStateLabel(row: EnvironmentRecord, current: string) {
  if (row.key === current && row.human_runtime_enabled) return "Current";
  if (row.state === "preparing") return "Preparing";
  if (row.state === "archived") return "Archived";
  if (row.state === "active" && row.human_runtime_enabled) return "Active";
  return "Unavailable";
}
