import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { modelUncertaintyRequest } from "./modelUncertaintyRequest";
type Row = Record<string, any>;
export function ModelUncertaintyControls({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [history, setHistory] = useState<Row[]>([]),
    [limits, setLimits] = useState<Record<string, string>>({});
  const [note, setNote] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const generation = useRef(0),
    canRead = me.permissions?.includes("export"),
    owner = me.permissions?.includes("members");
  const scope = liveIntentScope(
    "model-uncertainty-policy",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  async function refresh() {
    const sequence = ++generation.current;
    const [current, previous] = await Promise.all([
      api("/v1/model-uncertainty-controls"),
      api("/v1/model-uncertainty-controls/history"),
    ]);
    if (sequence !== generation.current) return;
    setData(current);
    setHistory(previous.items);
    setLimits(
      Object.fromEntries(
        current.rules.map((rule: Row) => [
          rule.model_id,
          String(rule.unknown_limit),
        ]),
      ),
    );
  }
  useEffect(() => {
    if (canRead) void refresh().catch((e) => setMessage(e.message));
    return () => {
      generation.current++;
    };
  }, [canRead]);
  async function act(task?: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const row = task ? await task() : null;
      await refresh();
      setNote("");
      setMessage(
        row
          ? `Policy receipt ${row.id}: version ${row.version}, ${row.status}. The effective policy is reloaded; recovery never reactivates an older revision.`
          : "Current policy and unknown counts reloaded; no inference was sent.",
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!canRead) return null;
  return (
    <details className="panel runtime-card">
      <summary>Pause routes on recorded unknown outcomes</summary>
      <p>
        Owners can pause new admissions when a route has at least the chosen
        number of recorded unknown outcomes. Counts span all months and versions
        of the route in this environment. Blank means no added limit. No retries
        or provider probes are performed.
      </p>
      {message && <p role="status">{message}</p>}
      <button className="btn" disabled={busy} onClick={() => void act()}>
        Reload policy and counts (discards edits)
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
              "/v1/model-uncertainty-controls/recover",
              "POST",
              { key: pending.key },
            );
            acknowledgeRecovery(sessionStorage, scope, pending, row);
            return row;
          })
        }
      >
        Recover policy receipt
      </button>
      {data && (
        <>
          <p>
            Policy version {data.version} · {data.scope.environment} ·{" "}
            {data.rules.length} guarded routes
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(() => {
                const body = modelUncertaintyRequest(
                  data.version,
                  data.models,
                  limits,
                  note,
                );
                return sendLiveIntent(sessionStorage, scope, body, (key) =>
                  api("/v1/model-uncertainty-controls", "PUT", body, key),
                );
              });
            }}
          >
            {data.models.map((model: Row) => (
              <fieldset key={model.id} disabled={busy || !owner}>
                <legend>
                  {model.name} · v{model.version} · {model.status}
                </legend>
                <p>
                  {model.unknown_calls} recorded unknown outcomes ·{" "}
                  {model.blocked
                    ? "new admissions paused"
                    : model.unknown_limit
                      ? "below configured limit"
                      : "no added limit"}
                </p>
                <label className="field">
                  <span>
                    Pause at or above this count (1–100; blank removes limit)
                  </span>
                  <input
                    inputMode="numeric"
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
                  <p>
                    Clear an archived route's limit before saving a new policy.
                  </p>
                )}
              </fieldset>
            ))}
            {owner && (
              <>
                <label className="field">
                  <span>Policy change reason (no secrets)</span>
                  <input
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
                  Save reviewed route-failure limits
                </button>
              </>
            )}
          </form>
          <p>
            To reduce unknown counts, review the original outcomes and use the
            existing owner reconciliation workflow. Updating this policy does
            not settle charges or change those records. Calls already admitted
            may still finish or fail.
          </p>
          <p>
            Pending calls are not counted here; existing concurrency,
            reservation and reconciliation controls still apply. Newly created
            route IDs are unguarded until explicitly configured.
          </p>
          <h4>Recent policy revisions (latest 20)</h4>
          {history.map((row) => (
            <p key={row.id}>
              Version {row.version} · {row.status} · {row.rules.length} route
              limits · {row.note}
            </p>
          ))}
          <p>{data.boundary}</p>
        </>
      )}
    </details>
  );
}
