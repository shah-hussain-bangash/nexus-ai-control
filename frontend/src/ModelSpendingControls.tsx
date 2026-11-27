import { useEffect, useState, useRef } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import {
  modelSpendingRequest,
  formatMicroUsd,
  microUsdInput,
} from "./modelSpendingRequest";
import "./live.css";
import "./enterpriseRuntime.css";
type Row = Record<string, any>;
export function ModelSpendingControls({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [limits, setLimits] = useState<Record<string, string>>({});
  const [required, setRequired] = useState(false),
    [note, setNote] = useState("");
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [history, setHistory] = useState<Row[]>([]);
  const inspection = useRef(0),
    canRead = me.permissions?.includes("export"),
    owner = me.permissions?.includes("members");
  const scope = liveIntentScope(
    "model-spend-policy",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  async function refresh() {
    const sequence = ++inspection.current;
    const [current, previous] = await Promise.all([
      api("/v1/inference-spend-controls"),
      api("/v1/inference-spend-controls/history?limit=20"),
    ]);
    if (sequence !== inspection.current) return;
    setData(current);
    setHistory(previous.items);
    setRequired(current.require_model_caps);
    setLimits(
      Object.fromEntries(
        current.caps.map((cap: Row) => [
          cap.model_id,
          microUsdInput(cap.monthly_limit_micro_usd),
        ]),
      ),
    );
  }
  useEffect(() => {
    if (canRead) void refresh().catch((e: Error) => setMessage(e.message));
    return () => {
      inspection.current++;
    };
  }, [canRead]);
  async function act(task: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const row = await task();
      setMessage(
        `Recorded policy version ${row.version}: ${row.status}. Refresh loaded the current effective policy; recovery does not reactivate an older revision.`,
      );
      await refresh();
      setNote("");
    } catch (e) {
      setMessage(
        e instanceof Error ? e.message : "Spending policy request failed.",
      );
    } finally {
      setBusy(false);
    }
  }
  if (!canRead) return null;
  return (
    <details className="panel runtime-card">
      <summary>Model-route monthly spending limits</summary>
      <h3>Owner-managed model-route ceilings</h3>
      <p>
        Limits apply to new inference admissions in this environment and include
        recorded spend plus unresolved reservations. The operator's
        workspace-wide budget and execution flags still apply. This does not
        change provider invoices, existing charges, hardware costs, or calls
        already admitted.
      </p>
      {message && <p role="status">{message}</p>}
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void refresh().catch((e: Error) => setMessage(e.message))
        }
      >
        Reload current policy and usage (discards edits)
      </button>
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void act(async () => {
            const pending = readRecovery(sessionStorage, scope);
            if (!pending)
              throw Error(
                "No unacknowledged policy change for this account and environment.",
              );
            const row = await api(
              "/v1/inference-spend-controls/recover",
              "POST",
              { key: pending.key },
            );
            acknowledgeRecovery(sessionStorage, scope, pending, row);
            return row;
          })
        }
      >
        Recover policy-change receipt
      </button>
      {data && (
        <>
          <p>
            Current version {data.version} · accounting month {data.period}{" "}
            (UTC) · environment {data.scope.environment}
          </p>
          <p>
            {data.require_model_caps
              ? "Unassigned model routes are blocked for new inference."
              : "Unassigned routes retain only existing server/workspace controls."}
          </p>
          <p>
            Caps attach to model asset IDs across versions. Required-cap mode
            prevents a newly created route from running without an
            owner-assigned cap. A zero-dollar cap permits zero-reservation local
            calls; it is not a model off switch.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              try {
                const body = modelSpendingRequest(
                  data.version,
                  required,
                  data.models,
                  limits,
                  note,
                );
                void act(() =>
                  sendLiveIntent(sessionStorage, scope, body, (key) =>
                    api("/v1/inference-spend-controls", "PUT", body, key),
                  ),
                );
              } catch (e) {
                setMessage(
                  e instanceof Error ? e.message : "Check the USD limits.",
                );
              }
            }}
          >
            <label>
              <input
                type="checkbox"
                checked={required}
                disabled={busy || !owner}
                onChange={(e) => setRequired(e.target.checked)}
              />
              Require an assigned cap for every new model request in this
              environment
            </label>
            <p>
              Blank removes a route's cap. Removing a cap while required-cap
              mode is enabled blocks that route. Up to 100 capped routes;
              amounts support six decimal places, at most 1,000,000 USD each.
            </p>
            {data.models.map((model: Row) => (
              <fieldset key={model.id}>
                <legend>
                  {model.name} · {model.status} · version {model.version}
                </legend>
                <p>
                  Recorded spend {formatMicroUsd(model.spent_micro_usd)} ·
                  unresolved reservations {formatMicroUsd(model.held_micro_usd)}{" "}
                  · remaining{" "}
                  {model.remaining_micro_usd === null
                    ? "no route cap"
                    : formatMicroUsd(model.remaining_micro_usd)}
                </p>
                {model.over_limit && (
                  <p role="status">
                    Current recorded spend/reservations exceed this cap. New
                    reservations are blocked; historical accounting remains
                    unchanged.
                  </p>
                )}
                <label className="field">
                  <span>Monthly route cap in USD (blank = unassigned)</span>
                  <input
                    inputMode="decimal"
                    disabled={busy || !owner || model.status === "archived"}
                    value={limits[model.id] ?? ""}
                    onChange={(e) =>
                      setLimits((before) => ({
                        ...before,
                        [model.id]: e.target.value,
                      }))
                    }
                  />
                </label>
                {model.status === "archived" && limits[model.id] && (
                  <button
                    className="btn"
                    type="button"
                    disabled={busy || !owner}
                    onClick={() =>
                      setLimits((before) => ({ ...before, [model.id]: "" }))
                    }
                  >
                    Remove archived-route cap from next revision
                  </button>
                )}
              </fieldset>
            ))}
            {owner && (
              <>
                <label className="field">
                  <span>Reason for policy change (avoid credentials)</span>
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
                  Save reviewed spending policy
                </button>
              </>
            )}
          </form>
          <h4>Recent policy revisions</h4>
          {history.map((row) => (
            <p key={row.id}>
              Version {row.version} · {row.status} · {row.caps.length} capped
              routes · required caps {row.require_model_caps ? "yes" : "no"} ·{" "}
              {row.note}
            </p>
          ))}
          <p>{data.boundary}</p>
        </>
      )}
    </details>
  );
}
