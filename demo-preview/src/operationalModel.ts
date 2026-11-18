export type OperationField = {
  id: string;
  label: string;
  default: string;
  type: string;
  options?: string[];
  min?: number;
  max?: number;
};
export type OperationCommand = {
  id: string;
  label: string;
  from_states: string[];
  to_state: string;
};
export type OperationSpec = {
  module: string;
  kind: string;
  title: string;
  visual_title: string;
  steps: string[];
  fields: OperationField[];
  commands: OperationCommand[];
  initial_state: string;
  file_extensions?: string[];
  max_file_bytes?: number;
};
export type OperationRecord = {
  id: string;
  title: string;
  owner: string;
  state: string;
  attributes: Record<string, string>;
};
export type OperationEvent = {
  id: string;
  record_id: string;
  command: string;
  from_state: string;
  to_state: string;
  at: string;
  note: string;
  scenario: string;
};
export type OperationalState = {
  records: OperationRecord[];
  events: OperationEvent[];
};
export const emptyOperations = (): OperationalState => ({
  records: [],
  events: [],
});
export function validateOperation(
  spec: OperationSpec,
  row: OperationRecord,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!row.title.trim() || row.title.length > 120)
    errors.title = "Enter a title of 1–120 characters.";
  if (!row.owner.trim() || row.owner.length > 120)
    errors.owner = "Enter a responsible owner of 1–120 characters.";
  for (const f of spec.fields) {
    const v = row.attributes[f.id];
    if (typeof v !== "string" || !v.trim() || v.length > 2000) {
      errors[f.id] = "Enter 1–2,000 characters.";
      continue;
    }
    if (
      f.type === "number" &&
      (!Number.isFinite(Number(v)) || Number(v) < (f.min ?? 0) || Number(v) > (f.max ?? 1000000000))
    )
      errors[f.id] = `Enter a number between ${f.min ?? 0} and ${f.max ?? 1000000000}.`;
    if (f.type === "select" && !f.options?.includes(v))
      errors[f.id] = "Select an available option.";
    if (
      f.type === "reference" &&
      !/^(env:[A-Z][A-Z0-9_]{2,70}|secret:\/\/[A-Za-z0-9/_-]{3,180})$/.test(v)
    )
      errors[f.id] = "Use an env: or secret:// reference only.";
    if (f.type === "json") {
      try {
        const j = JSON.parse(v);
        if (!j || typeof j !== "object" || Array.isArray(j)) throw Error();
      } catch {
        errors[f.id] = "Enter a valid JSON object.";
      }
    }
    if (f.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v))
      errors[f.id] = "Enter a valid email address.";
    if (
      f.type === "date" &&
      (!/^\d{4}-\d{2}-\d{2}$/.test(v) ||
        !Number.isFinite(Date.parse(v)) ||
        new Date(v).toISOString().slice(0, 10) !== v)
    )
      errors[f.id] = "Enter a valid date.";
    if (f.type === "url") {
      try {
        const u = new URL(v);
        if (
          u.protocol !== "https:" ||
          u.username ||
          u.password ||
          u.search ||
          u.hash ||
          (u.port && u.port !== "443")
        )
          throw Error();
      } catch {
        errors[f.id] =
          "Use HTTPS without credentials, query parameters or fragments.";
      }
    }
  }
  return errors;
}
export function availableCommands(spec: OperationSpec, row: OperationRecord) {
  return spec.commands.filter((c) => c.from_states.includes(row.state));
}
export function validateOperationalState(
  spec: OperationSpec,
  state: OperationalState,
) {
  if (state.records.length > 50 || state.events.length > 100)
    throw Error("Operational review size limit exceeded.");
  const ids = new Set<string>(),
    events = new Set<string>(),
    current = new Map<string, string>();
  for (const row of state.records) {
    if (
      ids.has(row.id) ||
      !/^[A-Za-z0-9_-]{1,64}$/.test(row.id) ||
      Object.keys(validateOperation(spec, row)).length
    )
      throw Error("Invalid operational review record.");
    ids.add(row.id);
    current.set(row.id, spec.initial_state);
  }
  for (const e of state.events) {
    const cmd = spec.commands.find((c) => c.id === e.command);
    const prior = current.get(e.record_id);
    if (
      events.has(e.id) ||
      !cmd ||
      !prior ||
      prior !== e.from_state ||
      !cmd.from_states.includes(prior) ||
      !e.note.trim() ||
      e.note.length > 500 ||
      !Number.isFinite(Date.parse(e.at)) ||
      ![
        "happy_path",
        "permission_denied",
        "dependency_unavailable",
        "timeout_unknown",
        "stale_revision",
      ].includes(e.scenario)
    )
      throw Error("Invalid operational event history.");
    events.add(e.id);
    const next = e.scenario === "happy_path" ? cmd.to_state : prior;
    if (e.to_state !== next)
      throw Error("Failed scenarios must preserve state.");
    current.set(e.record_id, next);
  }
  if (state.records.some((r) => r.state !== current.get(r.id)))
    throw Error("Operational record states do not match review history.");
}
export function transitionOperation(
  spec: OperationSpec,
  state: OperationalState,
  id: string,
  command: string,
  scenario: string,
  note: string,
  eventId: string,
  at: string,
  canEdit = true,
): OperationalState {
  if (!canEdit) throw Error("Your role cannot edit operational UI plans.");
  const row = state.records.find((r) => r.id === id);
  if (!row) throw Error("The selected record no longer exists.");
  if (Object.keys(validateOperation(spec, row)).length)
    throw Error("Correct the record fields before continuing.");
  const c = availableCommands(spec, row).find((c) => c.id === command);
  if (!c) throw Error("This action is unavailable in the current state.");
  if (!note.trim() || note.length > 500)
    throw Error("Enter a review note of 1–500 characters.");
  if (
    ![
      "happy_path",
      "permission_denied",
      "dependency_unavailable",
      "timeout_unknown",
      "stale_revision",
    ].includes(scenario)
  )
    throw Error("Choose an available scenario.");
  if (state.events.length >= 100)
    throw Error(
      "Export this review and start a new plan; the 100-event limit was reached.",
    );
  const next = scenario === "happy_path" ? c.to_state : row.state;
  return {
    records: state.records.map((r) =>
      r.id === id ? { ...r, state: next } : r,
    ),
    events: [
      ...state.events,
      {
        id: eventId,
        record_id: id,
        command,
        from_state: row.state,
        to_state: next,
        at,
        note: note.trim(),
        scenario,
      },
    ],
  };
}
export function capacityEstimate(a: Record<string, string>) {
  const arrival = Number(a.requests) || 0,
    limit = Number(a.rate_limit) || 0,
    concurrency = Number(a.concurrency) || 0,
    duration = Number(a.duration) || 0;
  const throughput = duration > 0 ? (concurrency * 60) / duration : limit;
  const admitted = Math.min(arrival, limit, throughput);
  return {
    arrival,
    admitted: Math.max(0, Math.floor(admitted)),
    rejected: Math.max(0, Math.ceil(arrival - admitted)),
  };
}
export function costEstimate(a: Record<string, string>) {
  const budget = Number(a.budget) || 0,
    estimated = Number(a.estimated) || 0,
    actual = Number(a.actual) || 0;
  return {
    budget,
    estimated,
    actual,
    variance: actual - estimated,
    remaining: budget - actual,
  };
}
export function fileMetadata(
  spec: OperationSpec,
  file: { name: string; size: number },
) {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!extension || !spec.file_extensions?.includes(extension))
    throw Error(
      "Unsupported file type. Use " + spec.file_extensions?.join(", ") + ".",
    );
  if (file.size > Number(spec.max_file_bytes))
    throw Error("File exceeds the 20 MiB UI review limit.");
  if (file.name.length > 250) throw Error("Filename is too long.");
  return { source: file.name, file_bytes: String(file.size) };
}
