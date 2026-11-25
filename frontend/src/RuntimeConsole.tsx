import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import {
  readRecovery,
  writeRecovery,
  clearRecovery,
  recoveryScope,
  requestFingerprint,
  prepareRecovery,
  type RecoveryRecord,
} from "./inferenceRecovery";
import { Activity, RefreshCw, Send, ShieldCheck, Wallet } from "lucide-react";
type Row = Record<string, any>;
const usd = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 6,
  }).format((n || 0) / 1e6);
export function RuntimeConsole({ me }: { me: Row }) {
  const [runtime, setRuntime] = useState<Row | null>(null),
    [models, setModels] = useState<Row[]>([]),
    [model, setModel] = useState(""),
    [query, setQuery] = useState(""),
    [output, setOutput] = useState(512),
    [rag, setRag] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [result, setResult] = useState<Row | null>(null);
  const scope = recoveryScope(me.user.org_id, me.user.id, me.environment);
  const [recovery, setRecovery] = useState<RecoveryRecord | null>(null);
  const [history, setHistory] = useState<Row>({
    items: [],
    has_more: false,
    next_cursor: null,
  });
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");
  const [pageStack, setPageStack] = useState<string[]>([]);
  const [pageCursor, setPageCursor] = useState("");
  const [historyBusy, setHistoryBusy] = useState(false);
  const historyRequest = useRef(0);
  const key = useRef("");
  const fingerprint = useRef("");
  const can = ["owner", "engineer", "security"].includes(me.user.role);
  async function loadHistory(
    cursor = "",
    filter = statusFilter,
    q = historyQuery,
  ) {
    const request = ++historyRequest.current;
    setHistoryBusy(true);
    try {
      const params = new URLSearchParams({ limit: "10", status: filter, q });
      if (cursor) params.set("cursor", cursor);
      const page = await api("/v1/inference-calls?" + params);
      if (request === historyRequest.current) {
        setHistory(page);
        setPageCursor(cursor);
        return true;
      }
    } catch (e) {
      if (request === historyRequest.current) setError((e as Error).message);
      return false;
    } finally {
      if (request === historyRequest.current) setHistoryBusy(false);
    }
  }
  async function refresh() {
    try {
      const [r, w] = await Promise.all([
        api("/v1/runtime"),
        api("/v1/workbench"),
      ]);
      setRuntime(r);
      setPageStack([]);
      await loadHistory();
      setModels(
        w.assets.filter(
          (a: Row) => a.kind === "model" && a.status === "validated",
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    refresh();
    const saved = readRecovery(sessionStorage, scope);
    if (saved) {
      setRecovery(saved);
      key.current = saved.key;
      fingerprint.current = saved.fingerprint;
    }
  }, []);
  function acceptResult(response: Row, record: RecoveryRecord) {
    if (
      typeof response?.id !== "string" ||
      !response.id ||
      typeof response.status !== "string" ||
      !response.status
    )
      throw new Error(
        "The response was incomplete. Recover the original request before submitting again.",
      );
    key.current = record.key;
    fingerprint.current = record.fingerprint;
    setResult(response);
    if (["pending", "unknown"].includes(response.status)) {
      writeRecovery(sessionStorage, scope, record);
      setRecovery(record);
    } else {
      clearRecovery(sessionStorage, scope, record);
      setRecovery(readRecovery(sessionStorage, scope));
    }
  }
  async function recoverSaved() {
    if (!recovery) return;
    setBusy(true);
    setError("");
    try {
      const response = await api("/v1/inference/recover", "POST", {
        key: recovery.key,
      });
      acceptResult(response, recovery);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    setBusy(true);
    setError("");
    let hadRecovery = Boolean(recovery);
    try {
      const selected = models.find((x) => x.id === model);
      if (!selected) throw new Error("Choose a checked model configuration.");
      const body = {
        model_id: model,
        expected_version: selected.version,
        query,
        retrieve_evidence: rag,
        max_output_tokens: output,
      };
      const digest = await requestFingerprint(body);
      const pending = readRecovery(sessionStorage, scope, true) || recovery;
      hadRecovery = Boolean(pending);
      if (pending && pending.fingerprint !== digest)
        throw new Error(
          "Recover and resolve the saved request before creating a different intent. No new provider call was sent.",
        );
      if (!key.current || fingerprint.current !== digest) {
        key.current = crypto.randomUUID();
        fingerprint.current = digest;
      }
      const record = prepareRecovery(
        sessionStorage,
        scope,
        digest,
        pending || {
          key: key.current,
          fingerprint: digest,
          created: Date.now(),
        },
      );
      key.current = record.key;
      fingerprint.current = record.fingerprint;
      setRecovery(record);
      const response = await api("/v1/inference", "POST", body, key.current);
      acceptResult(response, record);
      await refresh();
    } catch (e) {
      if (
        !hadRecovery &&
        e instanceof ApiError &&
        (e.status < 500 ||
          ["INFERENCE_DISABLED", "PROVIDER_SECRET_UNAVAILABLE"].includes(
            e.code,
          ))
      ) {
        clearRecovery(sessionStorage, scope, {
          key: key.current,
          fingerprint: fingerprint.current,
        });
        setRecovery(null);
      }
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reconcile(call: Row, event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api("/v1/inference/" + call.id + "/reconcile", "POST", {
        input_tokens: Number(form.get("input")),
        output_tokens: Number(form.get("output")),
        note: String(form.get("note")),
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="nx-panel runtime-console">
      <div className="nx-panel-heading">
        <div>
          <span className="eyebrow">PROVIDER EXECUTION / EXPLICIT OPT-IN</span>
          <h2>
            <Activity size={20} /> Live inference console
          </h2>
          <p>
            Provider calls use server-managed secrets and an atomic monthly
            reservation ledger. Business actions remain separate.
          </p>
        </div>
        <button
          className="btn btn-outline"
          onClick={refresh}
          disabled={busy}
          aria-label="Refresh inference runtime"
        >
          <RefreshCw size={16} />
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {recovery && (
        <div className="runtime-recovery" role="status">
          <strong>A saved inference intent needs review</strong>
          <p>
            Only the request key and a payload fingerprint were retained in this
            browser tab. Recovery reads the existing record without sending
            another provider request.
          </p>
          <button
            className="btn btn-outline"
            disabled={busy || !can}
            onClick={recoverSaved}
          >
            Recover saved request
          </button>
        </div>
      )}
      {!runtime ? (
        <p>Loading runtime status…</p>
      ) : (
        <>
          <div className="runtime-stats">
            <div>
              <ShieldCheck size={18} />
              <span>Execution</span>
              <strong>
                {runtime.enabled
                  ? "Enabled by operator"
                  : "Disabled by operator"}
              </strong>
            </div>
            <div>
              <Wallet size={18} />
              <span>Workspace monthly limit · {runtime.period} UTC</span>
              <strong>{usd(runtime.limit_micro_usd)}</strong>
            </div>
            <div>
              <span>Workspace charge / reserved</span>
              <strong>
                {usd(runtime.spent_micro_usd)} / {usd(runtime.held_micro_usd)}
              </strong>
            </div>
          </div>
          <p className="runtime-boundary">
            Workspace limits: {runtime.requests_per_minute} admitted requests/minute ·{" "}
            {runtime.max_inflight} concurrent pending dispatches (300-second
            window). Shared across environments.{" "}
          </p>
          <p className="runtime-boundary">
            {runtime.boundary} Rates are operator-configured estimates, not an
            invoice reconciliation or a provider account spending cap.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="runtime-form">
              <label>
                Checked model route
                <select
                  value={model}
                  onChange={(e) => {
                    setModel(e.target.value);
                    setResult(null);
                  }}
                  required
                >
                  <option value="">Choose a checked configuration</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} · v{m.version}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Maximum output tokens
                <input
                  type="number"
                  min={1}
                  max={runtime.max_output_tokens}
                  value={output}
                  onChange={(e) => setOutput(Number(e.target.value))}
                  required
                />
              </label>
            </div>
            <label>
              Request text
              <textarea
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setResult(null);
                }}
                maxLength={2000}
                rows={4}
                placeholder="Use synthetic or approved information. Your request will be sent to the selected provider."
                required
              />
            </label>
            <label className="runtime-checkbox">
              <input
                type="checkbox"
                checked={rag}
                onChange={(e) => setRag(e.target.checked)}
              />{" "}
              Include authorized source excerpts (sent to the selected model)
            </label>
            {rag && (
              <p className="muted">
                Searches indexed Document library sources. Saved design sources
                are used when no document matches. Review which model receives
                your evidence before sending.
              </p>
            )}
            <div className="runtime-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!runtime.enabled || !can || busy || !models.length}
              >
                <Send size={16} />
                {busy
                  ? "Processing request…"
                  : result
                    ? "Recheck same request"
                    : "Send to provider"}
              </button>
              {result && (
                <button
                  type="button"
                  className="btn btn-outline"
                  disabled={
                    busy ||
                    !!recovery ||
                    ["pending", "unknown"].includes(result.status)
                  }
                  onClick={() => {
                    clearRecovery(sessionStorage, scope, {
                      key: key.current,
                      fingerprint: fingerprint.current,
                    });
                    setRecovery(null);
                    key.current = "";
                    fingerprint.current = "";
                    setResult(null);
                  }}
                >
                  Start a new request
                </button>
              )}
            </div>
          </form>
          {result && (
            <div className="runtime-answer" aria-live="polite">
              <strong>
                {result.status} · {result.id.slice(0, 8)}
              </strong>
              <p>
                {result.result.answer ||
                  result.result.message ||
                  "Request recorded; refresh the runtime ledger for its outcome."}
              </p>
              {result.result.citations?.map((c: Row, i: number) => (
                <small key={(c.document_id || c.asset_id) + "-" + c.chunk}>
                  [{i + 1}] {c.title} · v{c.document_version ?? c.asset_version} · chunk {c.chunk}
                </small>
              ))}
            </div>
          )}
          <div className="runtime-history-heading">
            <div>
              <h3>Inference history</h3>
              <p>
                Search and page through saved evidence without replaying
                provider requests.
              </p>
            </div>
            <button
              className="btn btn-outline"
              onClick={() => {
                const url = URL.createObjectURL(
                  new Blob([JSON.stringify(history.items, null, 2)], {
                    type: "application/json",
                  }),
                );
                const link = document.createElement("a");
                link.href = url;
                link.download = "NEXUS_Inference_Page.json";
                link.click();
                URL.revokeObjectURL(url);
              }}
            >
              Export this page
            </button>
          </div>
          <form
            className="runtime-history-filters"
            onSubmit={async (e) => {
              e.preventDefault();
              if (await loadHistory("", statusFilter, search)) {
                setPageStack([]);
                setHistoryQuery(search);
              }
            }}
          >
            <label>
              Call or model reference
              <input
                type="search"
                maxLength={120}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Reference or current model-route name"
              />
            </label>
            <label>
              Status
              <select
                value={statusFilter}
                disabled={historyBusy}
                onChange={async (e) => {
                  const filter = e.target.value;
                  if (await loadHistory("", filter, historyQuery)) {
                    setStatusFilter(filter);
                    setPageStack([]);
                  }
                }}
              >
                {["all", "pending", "completed", "unknown", "reconciled"].map(
                  (status) => (
                    <option key={status}>{status}</option>
                  ),
                )}
              </select>
            </label>
            <button
              type="submit"
              className="btn btn-outline"
              disabled={historyBusy}
            >
              Search history
            </button>
          </form>
          <div className="history-pager">
            <span aria-live="polite">
              Page {pageStack.length + 1} · {history.items.length} records{" "}
              {historyBusy ? "· loading…" : ""}
            </span>
            <button
              className="btn btn-outline"
              disabled={historyBusy || !pageStack.length}
              onClick={async () => {
                const next = pageStack.slice(0, -1);
                const previous = pageStack[pageStack.length - 1];
                if (await loadHistory(previous)) setPageStack(next);
              }}
            >
              Previous page
            </button>
            <button
              className="btn btn-outline"
              disabled={historyBusy || !history.has_more}
              onClick={async () => {
                const next = [...pageStack, pageCursor];
                if (await loadHistory(history.next_cursor)) setPageStack(next);
              }}
            >
              Next page
            </button>
          </div>
          <div className="runtime-ledger">
            {history.items.length === 0 ? (
              <p>No provider calls recorded.</p>
            ) : (
              history.items.map((c: Row) => (
                <article key={c.id}>
                  <div>
                    <strong>
                      {c.id.slice(0, 8)} · {c.status}
                    </strong>
                    <span>
                      Route v{c.asset_version} · {c.input_tokens} input /{" "}
                      {c.output_tokens} output tokens ·{" "}
                      {c.duration_ms.toFixed(1)} ms · charge {usd(c.charged)} ·
                      initial reservation {usd(c.reserved)}
                    </span>
                  </div>
                  {c.result.answer && (
                    <details>
                      <summary>Inspect saved response</summary>
                      <p>{c.result.answer}</p>
                    </details>
                  )}
                  {["unknown", "pending"].includes(c.status) &&
                    me.user.role === "owner" && (
                      <details>
                        <summary>Reconcile verified provider usage</summary>
                        <p>
                          First verify the provider's usage records. This
                          settles the held reservation and never replays the
                          provider request. Pending calls require a 300-second
                          grace period.
                        </p>
                        <form onSubmit={(e) => reconcile(c, e)}>
                          <div className="runtime-form">
                            <label>
                              Verified input tokens
                              <input
                                name="input"
                                type="number"
                                min={0}
                                max={100000000}
                                required
                              />
                            </label>
                            <label>
                              Verified output tokens
                              <input
                                name="output"
                                type="number"
                                min={0}
                                max={100000000}
                                required
                              />
                            </label>
                          </div>
                          <label>
                            Evidence note
                            <textarea
                              name="note"
                              minLength={20}
                              maxLength={1000}
                              required
                              placeholder="Record the provider evidence checked, including reference and outcome. Do not paste credentials."
                            />
                          </label>
                          <button className="btn btn-outline" disabled={busy}>
                            Settle recorded usage
                          </button>
                        </form>
                      </details>
                    )}
                </article>
              ))
            )}
          </div>
        </>
      )}
    </section>
  );
}
