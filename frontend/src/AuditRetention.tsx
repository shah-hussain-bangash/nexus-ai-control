import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { acknowledgeRecovery, readRecovery } from "./inferenceRecovery";
import {
  retentionApplyRequest,
  retentionConfirmation,
} from "./auditRetentionRequest";
type Row = Record<string, any>;
export function AuditRetention({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [enabled, setEnabled] = useState(false),
    [days, setDays] = useState(30),
    [policyNote, setPolicyNote] = useState("");
  const [note, setNote] = useState(""),
    [selected, setSelected] = useState(""),
    [confirmation, setConfirmation] = useState("");
  const owner = me.permissions?.includes("members");
  const scope = (kind: "policy" | "plan") =>
    liveIntentScope(
      kind === "policy" ? "audit-retention-policy" : "audit-retention-plan",
      me.user.org_id,
      me.user.id,
      me.environment,
    );
  async function refresh() {
    const value = await api("/v1/audit-retention");
    setData(value);
    setEnabled(value.policy.enabled);
    setDays(value.policy.minimum_age_days);
  }
  useEffect(() => {
    if (owner) void refresh().catch((e) => setMessage(e.message));
  }, [owner]);
  async function act(task?: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const result = task ? await task() : null;
      await refresh();
      setConfirmation("");
      setMessage(
        result
          ? `Receipt ${result.id}: ${result.status}${result.purged_count !== undefined ? ` · removed ${result.purged_count} signed payloads` : ""}. Original audit events are preserved.`
          : "Retention inventory reloaded. No payloads removed.",
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recover(kind: "policy" | "plan") {
    const pending = readRecovery(sessionStorage, scope(kind));
    if (!pending)
      throw Error(
        "No unacknowledged operation for this account and environment.",
      );
    const row = await api(`/v1/audit-retention/${kind}/recover`, "POST", {
      key: pending.key,
    });
    acknowledgeRecovery(sessionStorage, scope(kind), pending, row);
    if (kind === "plan") setSelected(row.id);
    return row;
  }
  if (!owner) return null;
  const plan = data?.plans.find((row: Row) => row.id === selected);
  return (
    <details className="panel runtime-card">
      <summary>Expired signed-evidence payload retention</summary>
      <h3>Owner controls · {me.environment}</h3>
      <p>
        Off by default. Only expired signed audit snapshot payloads can be
        removed, after the minimum age and an explicit saved preview. Original
        audit logs and operation receipts remain. Downloaded copies are outside
        this tool.
      </p>
      {message && <p role="status">{message}</p>}
      <button className="btn" disabled={busy} onClick={() => void act()}>
        Reload inventory (discards policy edits)
      </button>
      <button
        className="btn"
        disabled={busy}
        onClick={() => void act(() => recover("policy"))}
      >
        Recover policy receipt
      </button>
      <button
        className="btn"
        disabled={busy}
        onClick={() => void act(() => recover("plan"))}
      >
        Recover preview receipt
      </button>
      {data && (
        <>
          <p>
            Effective policy version {data.policy.version} ·{" "}
            {data.policy.enabled
              ? `enabled · minimum ${data.policy.minimum_age_days} days`
              : "disabled"}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(() => {
                const body = {
                  expected_version: data.policy.version,
                  enabled,
                  minimum_age_days: days,
                  note: policyNote,
                };
                return sendLiveIntent(
                  sessionStorage,
                  scope("policy"),
                  body,
                  (key) => api("/v1/audit-retention/policy", "PUT", body, key),
                );
              });
            }}
          >
            <fieldset disabled={busy}>
              <legend>Retention policy</legend>
              <label>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                />
                Allow explicit payload retention operations
              </label>
              <label className="field">
                <span>Minimum snapshot age in days (7–3650)</span>
                <input
                  required
                  type="number"
                  min={7}
                  max={3650}
                  step={1}
                  value={Number.isNaN(days) ? "" : days}
                  onChange={(e) => setDays(e.target.valueAsNumber)}
                />
              </label>
              <label className="field">
                <span>Policy change reason (no secrets)</span>
                <input
                  required
                  minLength={10}
                  maxLength={500}
                  value={policyNote}
                  onChange={(e) => setPolicyNote(e.target.value)}
                />
              </label>
              <button className="btn" disabled={policyNote.trim().length < 10}>
                Save reviewed retention policy
              </button>
            </fieldset>
          </form>
          <label className="field">
            <span>
              Reason for hold, preview or removal (10–500 characters, no
              secrets)
            </span>
            <input
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <h4>Retained signed snapshot payloads</h4>
          {!data.items.length && (
            <p>No retained signed payloads in this environment.</p>
          )}
          {data.items.map((row: Row) => (
            <article key={row.id}>
              <p>
                {row.id} · created{" "}
                {new Date(row.created * 1000).toLocaleString()} · expires{" "}
                {row.expires
                  ? new Date(row.expires * 1000).toLocaleString()
                  : "unknown"}
              </p>
              <p>
                {row.hold.held
                  ? "Held: protected from this retention tool"
                  : row.eligible
                    ? "Eligible under the effective policy"
                    : "Not eligible under the effective policy"}{" "}
                · hold version {row.hold.version}
              </p>
              {row.hold.note && <p>Hold reason: {row.hold.note}</p>}
              <button
                className="btn"
                disabled={busy || note.trim().length < 10}
                onClick={() =>
                  void act(() =>
                    api(
                      `/v1/audit-retention/holds/${encodeURIComponent(row.id)}`,
                      "PUT",
                      {
                        expected_version: row.hold.version,
                        held: !row.hold.held,
                        note,
                      },
                    ),
                  )
                }
              >
                {row.hold.held ? "Release hold" : "Protect snapshot with hold"}
              </button>
            </article>
          ))}
          <button
            className="btn"
            disabled={busy || !data.policy.enabled || note.trim().length < 10}
            onClick={() =>
              void act(async () => {
                const body = { expected_version: data.policy.version, note };
                const result = await sendLiveIntent(
                  sessionStorage,
                  scope("plan"),
                  body,
                  (key) => api("/v1/audit-retention/plans", "POST", body, key),
                );
                setSelected(result.id);
                return result;
              })
            }
          >
            Save exact removal preview (does not remove payloads)
          </button>
          <label className="field">
            <span>Saved previews and removal receipts (latest 20)</span>
            <select
              value={selected}
              disabled={busy}
              onChange={(e) => {
                setSelected(e.target.value);
                setConfirmation("");
              }}
            >
              <option value="">Choose a saved preview</option>
              {data.plans.map((row: Row) => (
                <option key={row.id} value={row.id}>
                  {row.id} · {row.status} · {row.targets.length} targets ·
                  policy {row.policy_version}
                </option>
              ))}
            </select>
          </label>
          {plan && (
            <>
              <p>
                Preview {plan.id} · {plan.status} · policy {plan.policy_version}{" "}
                · expires {new Date(plan.expires * 1000).toLocaleString()}
              </p>
              <p>{plan.note}</p>
              <ul>
                {plan.targets.map((target: Row) => (
                  <li key={target.id}>
                    {target.id} · hold version {target.hold_version} · payload
                    fingerprint <code>{target.payload_sha256}</code>
                  </li>
                ))}
              </ul>
              {plan.status === "applied" ? (
                <p>
                  Removed {plan.purged_count} payloads at{" "}
                  {new Date(plan.applied_at * 1000).toLocaleString()}. This
                  operation will not run again.
                </p>
              ) : (
                <>
                  <p>
                    This permanently removes the listed saved payloads from the
                    application database. Audit events, intent tombstones and
                    downloaded files remain. Changes to a hold, payload or
                    policy invalidate the preview.
                  </p>
                  <label className="field">
                    <span>Type {retentionConfirmation} to confirm</span>
                    <input
                      value={confirmation}
                      onChange={(e) => setConfirmation(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <button
                    className="btn"
                    disabled={
                      busy ||
                      !data.policy.enabled ||
                      plan.policy_version !== data.policy.version ||
                      plan.expires * 1000 <= Date.now() ||
                      !plan.targets.length ||
                      confirmation !== retentionConfirmation ||
                      note.trim().length < 10
                    }
                    onClick={() =>
                      void act(() =>
                        api(
                          `/v1/audit-retention/plans/${encodeURIComponent(plan.id)}/apply`,
                          "POST",
                          retentionApplyRequest(
                            plan,
                            data.policy.version,
                            confirmation,
                            note,
                          ),
                        ),
                      )
                    }
                  >
                    Remove only the previewed expired payloads
                  </button>
                </>
              )}
            </>
          )}
          <h4>Recent retention policy revisions (latest 20)</h4>
          {data.policies.map((row: Row) => (
            <p key={row.id}>
              Version {row.version} · {row.status} ·{" "}
              {row.enabled ? "enabled" : "disabled"} · minimum{" "}
              {row.minimum_age_days} days · {row.note}
            </p>
          ))}
          <p>{data.boundary}</p>
        </>
      )}
    </details>
  );
}
