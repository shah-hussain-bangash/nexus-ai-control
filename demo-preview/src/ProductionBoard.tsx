import { useEffect, useState } from "react";
import { api } from "./api";
import {
  ArrowUpRight,
  ClipboardCheck,
  Download,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
type Row = Record<string, any>;
export function ProductionBoard({
  me,
  onNavigate,
  onDesign,
}: {
  me: Row;
  onNavigate: (view: string) => void;
  onDesign?: (module:string) => void;
}) {
  const [report, setReport] = useState<Row | null>(null),
    [group, setGroup] = useState("All"),
    [search, setSearch] = useState(""),
    [selected, setSelected] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState("not_tested"),
    [summary, setSummary] = useState(""),
    [reference, setReference] = useState("");
  const can = me.permissions?.includes("policy");
  async function refresh() {
    try {
      setReport(await api("/v1/production-readiness"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    refresh();
  }, []);
  function edit(gate: Row) {
    setSelected(gate.id);
    setOutcome(gate.evidence?.outcome || "not_tested");
    setSummary(gate.evidence?.summary || "");
    setReference(gate.evidence?.reference || "");
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    const gate = report?.gates.find((g: Row) => g.id === selected);
    if (!gate) return;
    setBusy(true);
    setError("");
    try {
      await api("/v1/production-readiness/" + selected, "PUT", {
        outcome,
        summary,
        reference,
        expected_version: gate.evidence?.version || 0,
      });
      setSelected("");
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function download() {
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "NEXUS_Production_Readiness.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }
  if (!report)
    return (
      <section className="nx-panel production-board">
        <p>{error || "Loading production workstreams…"}</p>
      </section>
    );
  const groups = [
    "All",
    ...new Set(report.gates.map((g: Row) => g.group)),
  ] as string[];
  const rows = report.gates.filter(
    (g: Row) =>
      (group === "All" || g.group === group) &&
      `${g.title} ${g.required_evidence}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <section className="nx-panel production-board">
      <div className="nx-panel-heading">
        <div>
          <span className="eyebrow">DELIVERY & ACCEPTANCE</span>
          <h2>
            <ClipboardCheck size={22} /> Production readiness board
          </h2>
          <p>
            Track implementation separately from operator-recorded acceptance
            evidence.
          </p>
        </div>
        <div className="board-actions">
          <button className="btn btn-outline" onClick={download}>
            <Download size={16} /> Export report
          </button>
          <button
            className="icon-btn"
            onClick={refresh}
            aria-label="Refresh readiness evidence"
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </div>
      <div className="readiness-summary">
        <div>
          <span>Tracked workstreams</span>
          <strong>{report.total_workstreams}</strong>
        </div>
        <div>
          <span>Implemented roadmap items</span>
          <strong>{report.implemented}</strong>
        </div>
        <div>
          <span>Partially implemented items</span>
          <strong>{report.partial}</strong>
        </div>
        <div>
          <span>Awaiting implementation</span>
          <strong>{report.not_implemented}</strong>
        </div>
        <div>
          <span>Accepted roadmap gates</span>
          <strong>{report.accepted}</strong>
        </div>
      </div>
      <div className="readiness-decision">
        <ShieldCheck size={20} />
        <div>
          <strong>
            {report.production_ready
              ? "All tracked gates recorded as accepted"
              : "Production acceptance remains open"}
          </strong>
          <p>{report.boundary}</p>
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="board-filters">
        <label>
          Find a workstream
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search capability or required evidence"
          />
        </label>
        <label>
          Area
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {groups.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="readiness-grid">
        {rows.length === 0 ? (
          <p>No workstreams match this search.</p>
        ) : (
          rows.map((gate: Row) => (
            <article className="readiness-workstream" key={gate.id}>
              <div className="readiness-workstream-top">
                <span>{gate.group}</span>
                <span className={"readiness-delivery " + gate.delivery}>
                  {gate.delivery.replaceAll("_", " ")}
                </span>
              </div>
              <h3>{gate.title}</h3>
              <p>{gate.required_evidence}</p>
              <div className="readiness-evidence-status">
                <span>Acceptance evidence</span>
                <strong>
                  {gate.evidence
                    ? gate.evidence.outcome.replaceAll("_", " ") +
                      " · revision " +
                      gate.evidence.version
                    : "Not recorded"}
                </strong>
              </div>
              {gate.evidence && (
                <details>
                  <summary>Read recorded evidence</summary>
                  <p>{gate.evidence.summary}</p>
                  {gate.evidence.reference && (
                    <a
                      href={gate.evidence.reference}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open evidence reference <ArrowUpRight size={14} />
                    </a>
                  )}
                  <small>
                    Updated{" "}
                    {new Date(gate.evidence.updated * 1000).toLocaleString()}
                  </small>
                </details>
              )}
              <div className="board-actions">
                <button
                  className="text-btn"
                  onClick={() => onNavigate(gate.view)}
                >
                  Open workspace <ArrowUpRight size={15} />
                </button>
                {onDesign && <button className="text-btn" onClick={()=>onDesign(gate.id)}>Design interface <ArrowUpRight size={15}/></button>}
                {can && (
                  <button
                    className="btn btn-outline"
                    onClick={() => edit(gate)}
                  >
                    Record evidence
                  </button>
                )}
              </div>
              {selected === gate.id && (
                <form onSubmit={save} className="readiness-evidence-form">
                  <label>
                    Recorded outcome
                    <select
                      value={outcome}
                      onChange={(e) => setOutcome(e.target.value)}
                    >
                      <option value="not_tested">Not tested</option>
                      <option value="failed">Failed</option>
                      <option
                        value="passed"
                        disabled={gate.delivery === "not_implemented"}
                      >
                        Passed for tested scope
                      </option>
                    </select>
                  </label>
                  <label>
                    Scope, environment and result
                    <textarea
                      rows={4}
                      minLength={20}
                      maxLength={1000}
                      value={summary}
                      onChange={(e) => setSummary(e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    Evidence reference (optional HTTPS URL)
                    <input
                      type="url"
                      value={reference}
                      maxLength={500}
                      onChange={(e) => setReference(e.target.value)}
                      placeholder="No credentials, query strings or fragments"
                    />
                  </label>
                  <p className="muted">
                    Recording evidence does not change this release's
                    implementation status.
                  </p>
                  <div className="board-actions">
                    <button className="btn btn-primary" disabled={busy}>
                      Save evidence revision
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => setSelected("")}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </article>
          ))
        )}
      </div>
    </section>
  );
}
