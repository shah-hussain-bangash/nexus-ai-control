import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { acknowledgeRecovery, readRecovery } from "./inferenceRecovery";
import {
  alertMetrics,
  alertPolicyRequest,
  type AlertRule,
} from "./operationalAlertRequest";
import "./live.css";
import "./enterpriseRuntime.css";
type Row = Record<string, any>;
export function OperationalAlerts({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [history, setHistory] = useState<Row[]>([]),
    [policies, setPolicies] = useState<Row[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]),
    [note, setNote] = useState(""),
    [sampleNote, setSampleNote] = useState("Manual dashboard evaluation.");
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const generation = useRef(0),
    owner = me.permissions?.includes("members"),
    operator = me.permissions?.includes("operate");
  const scope = (kind: "policy" | "sample") =>
    liveIntentScope(
      kind === "policy" ? "ops-alert-policy" : "ops-alert-sample",
      me.user.org_id,
      me.user.id,
      me.environment,
    );
  async function refresh() {
    const sequence = ++generation.current;
    const [current, samples, revisions] = await Promise.all([
      api("/v1/operational-alerts"),
      api("/v1/operational-alerts/history"),
      api("/v1/operational-alerts/history?kind=policy"),
    ]);
    if (sequence !== generation.current) return;
    setData(current);
    setHistory(samples.items);
    setPolicies(revisions.items);
    setRules(current.policy.rules);
  }
  useEffect(() => {
    void refresh().catch((e) => setMessage(e.message));
    return () => {
      generation.current++;
    };
  }, []);
  async function act(task?: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const row = task ? await task() : null;
      await refresh();
      setMessage(
        row
          ? `Receipt ${row.id}: ${row.status}. Reloaded the effective policy. Recovering an earlier receipt does not change the current policy or record a new sample.`
          : "Current readings reloaded. No check was recorded.",
      );
      setNote("");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recover(kind: "policy" | "sample") {
    const pending = readRecovery(sessionStorage, scope(kind));
    if (!pending)
      throw Error(
        "No unacknowledged receipt for this account and environment.",
      );
    const row = await api(`/v1/operational-alerts/${kind}/recover`, "POST", {
      key: pending.key,
    });
    acknowledgeRecovery(sessionStorage, scope(kind), pending, row);
    return row;
  }
  return (
    <details className="panel runtime-card">
      <summary>Local operational alert thresholds</summary>
      <h3>Manual alert checks · {me.environment}</h3>
      <p>
        Refresh reads current database signals. Record check saves a
        point-in-time result. No background alert delivery or automatic action
        is enabled.
      </p>
      {message && <p role="status">{message}</p>}
      <button className="btn" disabled={busy} onClick={() => void act()}>
        Reload readings and policy (discards edits)
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
        onClick={() => void act(() => recover("sample"))}
      >
        Recover check receipt
      </button>
      {data && (
        <>
          <p>
            Policy version {data.policy.version} · current thresholds{" "}
            {data.live.status} · sampled{" "}
            {new Date(data.live.sampled_at * 1000).toLocaleString()}
          </p>
          {data.live.status === "disabled" && (
            <p>No enabled rules. No monitoring assurance is implied.</p>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(() => {
                const body = alertPolicyRequest(
                  data.policy.version,
                  rules,
                  note,
                );
                return sendLiveIntent(
                  sessionStorage,
                  scope("policy"),
                  body,
                  (key) =>
                    api("/v1/operational-alerts/policy", "PUT", body, key),
                );
              });
            }}
          >
            {alertMetrics.map(([metric, label, max]) => {
              const rule = rules.find((r) => r.metric === metric),
                result = data.live.rules.find((r: Row) => r.metric === metric);
              const change = (patch: Partial<AlertRule>) =>
                setRules((before) =>
                  before.map((r) =>
                    r.metric === metric ? { ...r, ...patch } : r,
                  ),
                );
              return (
                <fieldset key={metric} disabled={busy || !owner}>
                  <legend>{label}</legend>
                  <p>
                    Current value {data.live.values[metric]} ·{" "}
                    {result?.status || "unconfigured"}
                    {result ? ` · ${result.severity}` : ""}
                  </p>
                  <label>
                    <input
                      type="checkbox"
                      checked={!!rule}
                      onChange={(e) =>
                        setRules((before) =>
                          e.target.checked
                            ? [
                                ...before,
                                {
                                  metric,
                                  enabled: true,
                                  severity: "warning",
                                  threshold: 1,
                                },
                              ]
                            : before.filter((r) => r.metric !== metric),
                        )
                      }
                    />
                    Include in policy
                  </label>
                  {rule && (
                    <>
                      <label>
                        <input
                          type="checkbox"
                          checked={rule.enabled}
                          onChange={(e) =>
                            change({ enabled: e.target.checked })
                          }
                        />
                        Enabled
                      </label>
                      <label className="field">
                        <span>Fire at or above (1–{max})</span>
                        <input
                          type="number"
                          min={1}
                          max={max}
                          step={1}
                          required
                          value={
                            Number.isNaN(rule.threshold) ? "" : rule.threshold
                          }
                          onChange={(e) =>
                            change({ threshold: e.target.valueAsNumber })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Severity</span>
                        <select
                          value={rule.severity}
                          onChange={(e) =>
                            change({
                              severity: e.target.value as AlertRule["severity"],
                            })
                          }
                        >
                          <option value="warning">Warning</option>
                          <option value="critical">Critical</option>
                        </select>
                      </label>
                    </>
                  )}
                </fieldset>
              );
            })}
            {owner && (
              <>
                <label className="field">
                  <span>Policy change note (no secrets)</span>
                  <textarea
                    required
                    minLength={10}
                    maxLength={1000}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
                <button
                  className="btn btn-primary"
                  disabled={busy || note.trim().length < 10}
                >
                  Save alert policy
                </button>
              </>
            )}
          </form>
          {operator && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void act(() => {
                  const body = {
                    expected_version: data.policy.version,
                    note: sampleNote,
                  };
                  return sendLiveIntent(
                    sessionStorage,
                    scope("sample"),
                    body,
                    (key) =>
                      api("/v1/operational-alerts/sample", "POST", body, key),
                  );
                });
              }}
            >
              <label className="field">
                <span>Check note (no secrets)</span>
                <textarea
                  required
                  minLength={10}
                  maxLength={1000}
                  value={sampleNote}
                  onChange={(e) => setSampleNote(e.target.value)}
                />
              </label>
              <button
                className="btn"
                disabled={busy || sampleNote.trim().length < 10}
              >
                Record manual check
              </button>
            </form>
          )}
          <h4>Recent recorded checks (latest 20)</h4>
          {!history.length && <p>No recorded checks in this environment.</p>}
          {history.map((row) => (
            <details key={row.id}>
              <summary>
                {new Date(row.sampled_at * 1000).toLocaleString()} ·{" "}
                {row.status} · policy {row.policy_version}
                {row.stale_policy ? " (earlier policy)" : ""}
              </summary>
              <p>{row.note}</p>
              {row.rules.map((rule: Row) => (
                <p key={rule.metric}>
                  {alertMetrics.find(([metric]) => metric === rule.metric)?.[1]}
                  : value {rule.value} · fires at ≥ {rule.threshold} ·{" "}
                  {rule.severity} · {rule.status}
                </p>
              ))}
              <small>Receipt {row.id}</small>
            </details>
          ))}
          <h4>Recent policy revisions (latest 20)</h4>
          {policies.map((row) => (
            <p key={row.id}>
              Version {row.version} · {row.status} · {row.rules.length} rules ·{" "}
              {row.note}
            </p>
          ))}
          <p>{data.boundary}</p>
        </>
      )}
    </details>
  );
}
