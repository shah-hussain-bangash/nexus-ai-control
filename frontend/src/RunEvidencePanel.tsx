import { useState } from "react";
import { api } from "./api";
import { sessionContext, type ContextSnapshot } from "./sessionContext";
import { Modal } from "./RuntimeDialog";
import { verifyRunEvidence, type RunEvidenceReport } from "./runEvidence";

export function RunEvidencePanel({ id }: { id: string }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [report, setReport] = useState<{
    value: RunEvidenceReport;
    snapshot: ContextSnapshot;
  } | null>(null);
  async function preview() {
    const snapshot = sessionContext.capture();
    setBusy(true);
    setError("");
    setReport(null);
    try {
      const value = await verifyRunEvidence(
        await api<RunEvidenceReport>(
          `/v1/agent-runs/${encodeURIComponent(id)}/evidence`,
        ),
        snapshot.context,
        id,
      );
      if (sessionContext.current(snapshot)) setReport({ value, snapshot });
    } catch (e) {
      if (sessionContext.current(snapshot)) setError((e as Error).message);
    } finally {
      if (sessionContext.current(snapshot)) setBusy(false);
    }
  }
  function download() {
    if (
      !report ||
      !sessionContext.current(report.snapshot) ||
      report.value.payload.run.id !== id
    )
      return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report.value, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `nexus-run-evidence-${id.replace(/[^a-zA-Z0-9-]/g, "_")}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setReport(null);
  }
  const visible =
    report &&
    sessionContext.current(report.snapshot) &&
    report.value.payload.run.id === id;
  return (
    <>
      <button className="btn btn-outline" disabled={busy} onClick={preview}>
        {busy ? "Preparing evidence…" : "Review run evidence"}
      </button>
      {error && (
        <p className="ops-alert error" role="alert">
          {error}
        </p>
      )}
      {visible && (
        <Modal title="Run evidence snapshot" onClose={() => setReport(null)}>
          <p>
            Recorded run: {report.value.payload.run.status.replaceAll("_", " ")}{" "}
            · version {report.value.payload.run.version} ·{" "}
            {report.value.payload.connector.mode} connector.
          </p>
          <p>{report.value.payload.boundary}</p>
          {report.value.payload.run.scheduled_start_at_utc && (
            <p>
              Scheduled start: {report.value.payload.run.scheduled_start_at_utc}
            </p>
          )}
          <ol>
            {report.value.payload.steps.map((step) => (
              <li key={step.position}>
                Step {step.position + 1}: {step.kind.replaceAll("_", " ")} ·{" "}
                {step.status.replaceAll("_", " ")}
                {step.action &&
                  ` · action ${step.action.status.replaceAll("_", " ")}`}
              </li>
            ))}
          </ol>
          <p>
            The checksum was checked. This file is unsigned and cannot prove
            authenticity or production readiness.
          </p>
          <button className="btn btn-primary" onClick={download}>
            Download run evidence JSON
          </button>
        </Modal>
      )}
    </>
  );
}
