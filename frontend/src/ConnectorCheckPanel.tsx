import { useEffect, useState } from "react";
import { api } from "./api";
import { sessionContext, type ContextSnapshot } from "./sessionContext";
import { Modal } from "./RuntimeDialog";
import { verifyEvidence, type EvidenceReport } from "./supplierEvidence";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import {
  readRecovery,
  acknowledgeRecovery,
  type RecoveryRecord,
} from "./inferenceRecovery";
import {
  supplierCheckPayload,
  supplierCheckOutcome,
  supplierCheckLabel,
  type ConnectorProfile,
  type SupplierRoute,
  type SupplierCheck,
} from "./connectorCheck";
type Config = {
  connector: ConnectorProfile;
  environment: string;
  choices: SupplierRoute[];
  boundary: string;
};
type History = { items: SupplierCheck[]; open_check: SupplierCheck | null };
export function ConnectorCheckPanel({
  user,
  environment,
}: {
  user: { id: string; org_id: string };
  environment: string;
}) {
  const scope = liveIntentScope(
    "connector-check",
    user.org_id,
    user.id,
    environment,
  );
  const [config, setConfig] = useState<Config | null>(null),
    [history, setHistory] = useState<History>({ items: [], open_check: null });
  const [routeId, setRouteId] = useState(""),
    [supplier, setSupplier] = useState(""),
    [note, setNote] = useState("");
  const [reviewed, setReviewed] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<RecoveryRecord | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const route = config?.choices.find((row) => row.grant_id === routeId);
  const [report, setReport] = useState<{
    value: EvidenceReport;
    snapshot: ContextSnapshot;
  } | null>(null);
  const [exporting, setExporting] = useState(false);
  async function previewEvidence(id: string) {
    if (exporting) return;
    const snapshot = sessionContext.capture();
    setExporting(true);
    setError("");
    try {
      const value = await verifyEvidence(
        await api<EvidenceReport>(
          `/v1/connector-checks/${encodeURIComponent(id)}/evidence`,
        ),
        snapshot.context,
        id,
      );
      if (sessionContext.current(snapshot)) setReport({ value, snapshot });
    } catch (e) {
      if (sessionContext.current(snapshot)) setError((e as Error).message);
    } finally {
      if (sessionContext.current(snapshot)) setExporting(false);
    }
  }
  function downloadEvidence() {
    if (!report || !sessionContext.current(report.snapshot)) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report.value, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `nexus-supplier-evidence-${report.value.payload.check.id.replace(/[^a-zA-Z0-9-]/g, "_")}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(
      "Evidence JSON downloaded. Its checksum was verified; the report is unsigned.",
    );
    setReport(null);
  }
  useEffect(() => {
    let active = true;
    load().catch((e) => {
      if (active) setError((e as Error).message);
    });
    return () => {
      active = false;
    };
  }, [scope]);
  async function results() {
    setHistory(await api<History>("/v1/connector-checks"));
  }
  async function load() {
    setLoading(true);
    setError("");
    setReviewed(false);
    setRouteId("");
    try {
      setPending(readRecovery(sessionStorage, scope, true));
      const [next, latest] = await Promise.all([
        api<Config>("/v1/connector-checks/config"),
        api<History>("/v1/connector-checks"),
      ]);
      setConfig(next);
      setHistory(latest);
    } finally {
      setLoading(false);
    }
  }
  const polling = ["queued", "executing"].includes(
    history.open_check?.status || "",
  );
  useEffect(() => {
    if (!polling) return;
    let active = true;
    const timer = setInterval(() => {
      api<History>("/v1/connector-checks")
        .then((data) => {
          if (active) setHistory(data);
        })
        .catch((e) => {
          if (active) setError((e as Error).message);
        });
    }, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [polling, scope]);
  function saved(value: ReturnType<typeof supplierCheckOutcome>) {
    setPending(null);
    setReviewed(false);
    setNotice(
      value.status === "cancelled"
        ? "The pending request was cancelled. A delayed request with that key cannot admit a check."
        : `Request recorded as check ${value.check!.id}. Follow its current result below. Recovery or intake cancellation preserves an already-recorded check.`,
    );
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!config || !route || busy || pending || history.open_check) return;
    let body;
    try {
      body = supplierCheckPayload(
        config.connector,
        route,
        supplier,
        note,
        reviewed,
      );
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      saved(
        await sendLiveIntent(sessionStorage, scope, body, async (key) =>
          supplierCheckOutcome(
            await api("/v1/connector-checks", "POST", body, key),
          ),
        ),
      );
      await results();
    } catch (e) {
      setError((e as Error).message);
      try {
        setPending(readRecovery(sessionStorage, scope, true));
      } catch (stored) {
        setError((stored as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }
  async function resolve(command: "recover" | "cancel-pending") {
    if (!pending || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const value = supplierCheckOutcome(
        await api(`/v1/connector-checks/${command}`, "POST", {
          key: pending.key,
        }),
      );
      acknowledgeRecovery(sessionStorage, scope, pending, value);
      saved(value);
      await results();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const locked = busy || loading || !!pending || !!history.open_check;
  return (
    <section
      className="panel runtime-card"
      aria-label="Governed supplier check"
    >
      <h2>Governed supplier check</h2>
      <p>
        The configured business connector is shared across this deployment.
        Selecting a local environment does not provision a separate customer
        sandbox.
      </p>
      <p>
        Review the configured business connector and request one supplier lookup
        in <strong>{environment}</strong>. Policy, grants and the existing
        worker control dispatch. This screen cannot create a purchase request or
        change connector settings.
      </p>
      <div className="live-actions">
        <button
          className="btn"
          disabled={busy || loading}
          onClick={() =>
            void load().catch((e) => setError((e as Error).message))
          }
        >
          Refresh supplier routes
        </button>
        <button
          className="btn"
          disabled={busy}
          onClick={() =>
            void results().catch((e) => setError((e as Error).message))
          }
        >
          Refresh check results
        </button>
      </div>
      {config && (
        <p>
          {config.connector.mode === "synthetic"
            ? "Synthetic local connector: no customer system will be contacted."
            : `HTTP adapter: this lookup will contact ${config.connector.configured_host} using the server's configured credential.`}{" "}
          Contract: {config.connector.contract}. Destination:{" "}
          <code>{config.connector.destination}</code>.
        </p>
      )}
      <p>
        A verified lookup is evidence for that supplier read only. Synthetic
        results do not establish customer acceptance. Purchase handling,
        isolation, recovery and deployment acceptance need separate evidence.
      </p>
      {pending && (
        <div className="ops-alert">
          <p>
            A submission is awaiting confirmation. Recovery or cancellation
            resolves the saved intent without deleting an already-admitted
            check.
          </p>
          <button
            className="btn"
            disabled={busy}
            onClick={() => void resolve("recover")}
          >
            Recover supplier check
          </button>
          <button
            className="btn"
            disabled={busy}
            onClick={() => void resolve("cancel-pending")}
          >
            Cancel pending check request
          </button>
        </div>
      )}
      {history.open_check && (
        <p role="status">
          An existing check needs attention:{" "}
          {supplierCheckLabel(history.open_check)}. Finish or reconcile it
          before starting another.
        </p>
      )}
      {error && (
        <p className="ops-alert" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <form className="runtime-form" onSubmit={submit}>
        <label className="field">
          <span>Granted supplier route</span>
          <select
            value={routeId}
            disabled={locked}
            onChange={(e) => {
              setRouteId(e.target.value);
              setReviewed(false);
            }}
          >
            <option value="">Choose an active agent and supplier tool</option>
            {config?.choices.map((row) => (
              <option key={row.grant_id} value={row.grant_id}>
                {row.agent_name} → {row.tool_name} · {row.grant_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        {config && !config.choices.length && (
          <p>
            Activate an agent and grant a validated supplier-read tool in this
            environment before requesting a check.
          </p>
        )}
        <label className="field">
          <span>Supplier reference to check</span>
          <input
            required
            maxLength={64}
            value={supplier}
            disabled={locked}
            onChange={(e) => {
              setSupplier(e.target.value);
              setReviewed(false);
            }}
          />
        </label>
        <label className="field">
          <span>Reason for supplier check</span>
          <input
            required
            minLength={5}
            maxLength={500}
            value={note}
            disabled={locked}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <label className="product-check">
          <input
            type="checkbox"
            checked={reviewed}
            disabled={locked}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          I reviewed the connector destination, granted route and supplier
          reference. This requests a governed supplier read.
        </label>
        <button
          className="btn btn-primary"
          disabled={locked || !route || !reviewed}
        >
          {busy ? "Submitting…" : "Submit governed supplier check"}
        </button>
      </form>
      <h3>Recent checks for your account</h3>
      {!history.items.length && (
        <p>No supplier checks are recorded in this environment.</p>
      )}
      {history.items.length > 0 && (
        <div className="runtime-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Supplier / connector</th>
                <th>Result</th>
                <th>Reference</th>
              </tr>
            </thead>
            <tbody>
              {history.items.map((row) => (
                <tr key={row.id}>
                  <td>
                    {row.supplier_id}
                    <br />
                    {row.connector_mode === "synthetic"
                      ? "Synthetic local system"
                      : "HTTP business adapter"}
                  </td>
                  <td>
                    {supplierCheckLabel(row)}
                    <br />
                    {row.reason}
                  </td>
                  <td>
                    <code>{row.id}</code>
                    {row.external_ref && <p>{row.external_ref}</p>}
                    <small>Trace: {row.trace_id}</small>
                    <p>
                      <button
                        className="btn"
                        disabled={exporting}
                        onClick={() => void previewEvidence(row.id)}
                      >
                        Evidence report
                      </button>
                    </p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {report && (
        <Modal title="Supplier evidence report" onClose={() => setReport(null)}>
          <p>
            {report.value.payload.connector.mode === "synthetic"
              ? "Synthetic local lookup"
              : "HTTP supplier lookup"}{" "}
            · {report.value.payload.check.status}
          </p>
          <p>
            Supplier: {report.value.payload.check.supplier_id}. Environment:{" "}
            {report.value.payload.scope.environment}.
          </p>
          <p>
            Captured: {report.value.payload.exported_at_utc}. Audit events:{" "}
            {report.value.payload.audit_events.length}.
          </p>
          <p>{report.value.payload.boundary}</p>
          <p>SHA-256 checksum verified:</p>
          <code style={{ overflowWrap: "anywhere" }}>
            {report.value.integrity.digest}
          </code>
          <p>
            <button className="btn btn-primary" onClick={downloadEvidence}>
              Download JSON
            </button>
          </p>
        </Modal>
      )}
      <div className="live-actions">
        <a className="btn" href="#executions">
          Open execution ledger
        </a>
        <a className="btn" href="#approvals">
          Open independent approvals
        </a>
      </div>
    </section>
  );
}
