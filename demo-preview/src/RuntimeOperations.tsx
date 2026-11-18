import { useEffect, useState } from "react";
import {
  Activity,
  RefreshCw,
  ShieldCheck,
  Plug,
  Database,
  LockKeyhole,
} from "lucide-react";
import { api } from "./api";
type Row = Record<string, any>;
export function RuntimeOperations() {
  const [data, setData] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true);
    try {
      setData(await api("/v1/runtime-operations"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    refresh();
  }, []);
  return (
    <section className="runtime-ops" aria-label="Live runtime operations">
      <header>
        <div>
          <span className="eyebrow">CURRENT WORKSPACE SIGNALS</span>
          <h2>Operations you can inspect.</h2>
          <p>
            Queue state, review demand and the configured business destination
            in one clear view.
          </p>
        </div>
        <button className="btn btn-outline" disabled={busy} onClick={refresh}>
          <RefreshCw size={17} />
          {busy ? "Refreshing…" : "Refresh signals"}
        </button>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data ? (
        <p role="status">Loading operating signals…</p>
      ) : (
        <>
          <div className="runtime-ops-metrics">
            {[
              [
                "Queued actions",
                data.actions.queued || 0,
                "Waiting for an authorized worker",
              ],
              [
                "Unknown outcomes",
                data.actions.outcome_unknown || 0,
                "Reconcile; do not submit again",
              ],
              [
                "Pending reviews",
                data.pending_unexpired_approvals,
                "Unexpired independent approvals",
              ],
              [
                "Indexed sources",
                data.documents.indexed || 0,
                "Current active document records",
              ],
            ].map(([label, value, note]) => (
              <article className="panel" key={String(label)}>
                <small>{label}</small>
                <strong>{value}</strong>
                <p>{note}</p>
              </article>
            ))}
          </div>
          <div className="runtime-ops-grid">
            <article className="panel">
              <header>
                <Plug size={22} />
                <h3>Business adapter</h3>
              </header>
              <span
                className={
                  "live-state " +
                  (data.connector.external_effects_enabled
                    ? "waiting_review"
                    : "succeeded")
                }
              >
                {data.connector.external_effects_enabled
                  ? "HTTP business mode"
                  : "Synthetic local mode"}
              </span>
              <p>{data.connector.boundary}</p>
              <dl>
                <div>
                  <dt>Contract</dt>
                  <dd>{data.connector.contract}</dd>
                </div>
                <div>
                  <dt>Host</dt>
                  <dd>
                    {data.connector.configured_host ||
                      "Local synthetic database"}
                  </dd>
                </div>
                <div>
                  <dt>Automatic retries</dt>
                  <dd>Disabled</dd>
                </div>
                <div>
                  <dt>Transport</dt>
                  <dd>
                    {data.connector.external_effects_enabled
                      ? "HTTPS · certificate verification required"
                      : "Local isolated test store"}
                  </dd>
                </div>
              </dl>
              <code className="live-hash">
                Reviewed destination: {data.connector.destination}
              </code>
              <p>
                Destination changes invalidate queued action dispatch and future
                workflow steps. Approvals remain tied to the reviewed payload.
              </p>
            </article>
            <article className="panel">
              <header>
                <Activity size={22} />
                <h3>Monitoring and recovery</h3>
              </header>
              <dl>
                <div>
                  <dt>Metrics export</dt>
                  <dd>
                    {data.metrics_enabled
                      ? "Enabled · protected operator header"
                      : "Disabled by default"}
                  </dd>
                </div>
                <div>
                  <dt>Oldest queued action</dt>
                  <dd>
                    {Math.round(data.oldest_queued_action_age_seconds)} seconds
                  </dd>
                </div>
                <div>
                  <dt>Database schema</dt>
                  <dd>{data.schema_version}</dd>
                </div>
                <div>
                  <dt>Sampling time</dt>
                  <dd>{new Date(data.sampled_at * 1000).toLocaleString()}</dd>
                </div>
              </dl>
              <p>
                The optional /metrics endpoint supplies fixed-label database
                gauges. The operator token stays on the server and monitoring
                service; it is never displayed here.
              </p>
              <p>
                Encrypted backup creation and isolated inspection are available
                through the operator CLI. They require stopped writers and a
                separately protected encryption key.
              </p>
            </article>
          </div>
          <div className="ops-alert">
            <ShieldCheck size={20} />
            <p>
              {data.boundary} A green configuration signal does not replace a
              customer sandbox test, alert drill or restore acceptance.
            </p>
          </div>
        </>
      )}
    </section>
  );
}
