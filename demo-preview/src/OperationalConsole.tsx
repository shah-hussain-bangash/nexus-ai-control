import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  GitBranch,
  Plus,
  Search,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import type { InterfaceDraft, InterfaceModule } from "./interfaceDesign";
import {
  availableCommands,
  capacityEstimate,
  costEstimate,
  emptyOperations,
  fileMetadata,
  transitionOperation,
  validateOperation,
  type OperationalState,
  type OperationRecord,
  type OperationSpec,
} from "./operationalModel";
import "./operational.css";
function download(name: string, data: unknown) {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = u;
  a.download = name + ".json";
  a.click();
  URL.revokeObjectURL(u);
}
function Overlay({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      prior?.focus();
    };
  }, []);
  return (
    <dialog
      className="ops-dialog"
      ref={ref}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <header>
        <div>
          <small>OPERATIONAL UI REHEARSAL</small>
          <h2>{title}</h2>
        </div>
        <button
          className="icon-btn"
          aria-label="Close operational dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </header>
      <div className="ops-dialog-body">{children}</div>
    </dialog>
  );
}
export function OperationalConsole({
  module,
  draft,
  disabled,
  onChange,
  onEditorDirtyChange,
}: {
  module: InterfaceModule;
  draft: InterfaceDraft;
  disabled: boolean;
  onChange: (state: OperationalState) => void;
  onEditorDirtyChange: (dirty: boolean) => void;
}) {
  const spec = module.operations as OperationSpec,
    state = draft.config.operational_state || emptyOperations();
  const [selected, setSelected] = useState(""),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [page, setPage] = useState(0),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [editor, setEditor] = useState<OperationRecord | null>(null),
    [fieldErrors, setFieldErrors] = useState<Record<string, string>>({}),
    [command, setCommand] = useState(""),
    [scenario, setScenario] = useState("happy_path"),
    [note, setNote] = useState(""),
    [remove, setRemove] = useState(false),
    [mode, setMode] = useState("available"),
    [searchText, setSearchText] = useState("approval"),
    [searchRun, setSearchRun] = useState(""),
    [principal, setPrincipal] = useState("Assigned role"),
    [accessResult, setAccessResult] = useState(""),
    [digest, setDigest] = useState(""),
    [evidence, setEvidence] = useState(false);
  const [editorBaseline,setEditorBaseline]=useState("");
  const [discardEditor,setDiscardEditor]=useState(false);
  const editorDirty=Boolean(editor && JSON.stringify(editor)!==editorBaseline);
  useEffect(()=>{onEditorDirtyChange(editorDirty);},[editorDirty,onEditorDirtyChange]);
  useEffect(()=>()=>onEditorDirtyChange(false),[onEditorDirtyChange]);
  function closeEditor(){if(editorDirty)setDiscardEditor(true);else setEditor(null);}
  const row = state.records.find((r) => r.id === selected) || state.records[0];
  const filtered = state.records.filter(
    (r) =>
      (filter === "all" || r.state === filter) &&
      (r.title + " " + r.owner + " " + Object.values(r.attributes).join(" "))
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / 8)),
    safePage = Math.min(page, pageCount - 1),
    view = filtered.slice(safePage * 8, safePage * 8 + 8);
  const events = state.events.filter((e) => e.record_id === row?.id),
    states = Array.from(
      new Set([
        spec.initial_state,
        ...spec.commands.flatMap((c) => [...c.from_states, c.to_state]),
      ]),
    );
  const locked = disabled || mode !== "available";
  function blank(index = 1): OperationRecord {
    return {
      id: crypto.randomUUID(),
      title: spec.title + " " + index,
      owner: "Platform review team",
      state: spec.initial_state,
      attributes: Object.fromEntries(spec.fields.map((f) => [f.id, f.default])),
    };
  }
  function edit(record?: OperationRecord) {
    setFieldErrors({});
    const next=structuredClone(record || blank(state.records.length + 1));
    setEditorBaseline(JSON.stringify(next));
    setEditor(next);
  }
  function saveRecord(e: React.FormEvent) {
    e.preventDefault();
    if (!editor || locked) return;
    const errors = validateOperation(spec, editor);
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    const exists = state.records.some((r) => r.id === editor.id);
    if (!exists && state.records.length >= 50) {
      setError("This plan supports 50 records. Export and start a new plan.");
      return;
    }
    onChange({
      ...state,
      records: exists
        ? state.records.map((r) => (r.id === editor.id ? editor : r))
        : [...state.records, editor],
    });
    setSelected(editor.id);
    setEditor(null);
    setNotice(
      "Record added to the interface draft. Save revision to retain it.",
    );
  }
  function seed() {
    if (locked) return;
    const examples = [1, 2, 3].map((i) => blank(i));
    if (spec.kind === "retrieval") {
      examples[1].attributes.source_excerpt =
        "Supplier onboarding requires verified tax and bank details.";
      examples[1].attributes.citation = "SYN-DOC-002 §1";
      examples[2].attributes.source_excerpt =
        "Restricted documents are available only to authorized reviewers.";
      examples[2].attributes.citation = "SYN-DOC-003 §4";
    }
    onChange({
      ...state,
      records: [...state.records, ...examples].slice(0, 50),
    });
    setSelected(examples[0].id);
    setNotice("Synthetic review records added. Save revision to retain them.");
  }
  function runCommand(e: React.FormEvent) {
    e.preventDefault();
    if (!row || locked) return;
    try {
      const next = transitionOperation(
        spec,
        state,
        row.id,
        command,
        scenario,
        note,
        crypto.randomUUID(),
        new Date().toISOString(),
        !disabled,
      );
      onChange(next);
      setCommand("");
      setError("");
      setNotice(
        scenario === "happy_path"
          ? "UI state updated. Save revision to retain this rehearsal."
          : "Failure scenario recorded; record state was preserved. No retry or runtime effect occurred.",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function intake(files: FileList | null) {
    if (!files || locked) return;
    try {
      const incoming = Array.from(files);
      if (state.records.length + incoming.length > 50)
        throw Error("The plan can contain at most 50 intake records.");
      const records = incoming.map((file, i) => {
        const meta = fileMetadata(spec, file);
        const r = blank(state.records.length + i + 1);
        r.title = file.name.slice(0, 120);
        r.attributes = { ...r.attributes, ...meta };
        return r;
      });
      onChange({ ...state, records: [...state.records, ...records] });
      setSelected(records[0]?.id || "");
      setNotice(
        "Local filename and size added. File bytes were not read or uploaded. Save revision to retain metadata.",
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function hashEvidence() {
    try {
      const payload = JSON.stringify({
        module: module.id,
        records: state.records,
        events: state.events,
      });
      const bytes = new TextEncoder().encode(payload);
      const hash = await crypto.subtle.digest("SHA-256", bytes);
      setDigest(
        Array.from(new Uint8Array(hash))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join(""),
      );
    } catch {
      setError(
        "Hashing is unavailable in this browser. Export the review payload instead.",
      );
    }
  }
  const findings = spec.fields.filter((f) => f.id.startsWith("check_"));
  const selectedCommand = spec.commands.find((c) => c.id === command);
  const searched = useMemo(() => {
    const terms = searchRun.toLowerCase().split(/\s+/).filter(Boolean);
    return state.records
      .map((r) => ({
        row: r,
        hits: terms.filter((t) =>
          (r.attributes.source_excerpt || "").toLowerCase().includes(t),
        ).length,
      }))
      .filter((x) => x.hits > 0)
      .sort((a, b) => b.hits - a.hits);
  }, [searchRun, state.records]);
  const pipelineProgress =
    row?.state === "succeeded" ||
    row?.state === "active" ||
    row?.state === "resolved"
      ? spec.steps.length
      : row?.state === "running"
        ? Math.min(3, spec.steps.length)
        : row?.state === "queued" || row?.state === "review_requested"
          ? 1
          : 0;
  return (
    <section className="ops-console" aria-label={spec.title}>
      <div className="ops-heading">
        <div>
          <small>DEDICATED OPERATIONAL EXPERIENCE</small>
          <h3>{spec.title}</h3>
          <p>
            Rehearse the full user journey. Records and transitions are saved as
            interface metadata; services remain inactive.
          </p>
        </div>
        <button
          className="btn btn-outline"
          onClick={() =>
            download(module.id + "-operational-review", {
              boundary: "UI metadata only; no runtime execution",
              module: module.id,
              ...state,
            })
          }
        >
          <Download size={16} /> Export review
        </button>
      </div>
      <div className="ops-metrics">
        <article>
          <span>Review records</span>
          <strong>{state.records.length}</strong>
          <small>In this interface plan</small>
        </article>
        <article>
          <span>Completed UI journeys</span>
          <strong>
            {
              state.records.filter((r) =>
                ["succeeded", "active", "resolved"].includes(r.state),
              ).length
            }
          </strong>
          <small>Synthetic rehearsal outcomes</small>
        </article>
        <article>
          <span>Review events</span>
          <strong>{state.events.length}</strong>
          <small>Zero live service operations</small>
        </article>
      </div>
      <details className="ops-state-review">
        <summary>Review unavailable, loading and permission states</summary>
        <label htmlFor={"mode-" + module.id}>Screen state</label>
        <select
          id={"mode-" + module.id}
          value={mode}
          onChange={(e) => {
            setMode(e.target.value);
            setError("");
          }}
        >
          <option value="available">Available</option>
          <option value="loading">Loading review</option>
          <option value="unavailable">Service unavailable review</option>
          <option value="permission_denied">Permission denied review</option>
          <option value="empty">Empty-results review</option>
        </select>
        <p>
          These controls review UI states. They do not change your actual
          permissions or service health.
        </p>
      </details>
      {error && (
        <div role="alert" className="ops-alert error">
          <strong>Action needs attention</strong>
          <p>{error}</p>
          <button className="btn btn-outline" onClick={() => setError("")}>
            Dismiss error
          </button>
        </div>
      )}
      {notice && (
        <div role="status" className="ops-alert success">
          {notice}
          <button
            className="icon-btn"
            aria-label="Dismiss operational notice"
            onClick={() => setNotice("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {disabled && (
        <p className="ops-permission">
          <ShieldCheck size={17} /> Read-only interface: your role, archive
          state or an active save prevents changes.
        </p>
      )}
      {mode !== "available" ? (
        <div
          className="ops-empty"
          role={mode === "unavailable" ? "alert" : "status"}
        >
          <Activity size={28} />
          <h4>
            {
              (
                {
                  loading: "Loading operational records",
                  unavailable: "The service could not be reached",
                  permission_denied: "Your role cannot access this operation",
                  empty: "No records match this view",
                } as Record<string, string>
              )[mode]
            }
          </h4>
          <p>
            {mode === "unavailable"
              ? "Preserve the current draft and retry. No command was submitted."
              : mode === "permission_denied"
                ? "Ask the workspace administrator to review the required role. Existing records remain unchanged."
                : mode === "empty"
                  ? "Clear filters or add a record when access is available."
                  : "A request is in progress. Existing records remain unchanged."}
          </p>
          <button
            className="btn btn-outline"
            onClick={() => setMode("available")}
          >
            {mode === "unavailable"
              ? "Retry screen"
              : mode === "empty"
                ? "Clear review filter"
                : "Return to available view"}
          </button>
        </div>
      ) : (
        <>
          {spec.kind === "ingestion" && (
            <label
              className={"ops-intake " + (locked ? "locked" : "")}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                intake(e.dataTransfer.files);
              }}
            >
              <Upload size={25} />
              <strong>Add documents for intake UI review</strong>
              <span>PDF, DOCX, TXT, CSV or MD · up to 20 MiB each</span>
              <input
                type="file"
                aria-label="Select documents for intake review"
                multiple
                accept=".pdf,.docx,.txt,.csv,.md"
                disabled={locked}
                onChange={(e) => {
                  intake(e.target.files);
                  e.target.value = "";
                }}
              />
              <small>
                Only local filename and size are used. No content extraction or
                upload occurs.
              </small>
            </label>
          )}
          <div className="ops-toolbar">
            <label className="ops-search">
              <Search size={17} />
              <input
                aria-label="Search operational records"
                placeholder="Search title, owner or details…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
              />
            </label>
            <select
              aria-label="Filter operational records by state"
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setPage(0);
              }}
            >
              <option value="all">All record states</option>
              {states.map((s) => (
                <option key={s} value={s}>
                  {s.replaceAll("_", " ")}
                </option>
              ))}
            </select>
            <button
              className="btn btn-outline"
              disabled={locked || state.records.length > 47}
              onClick={seed}
            >
              Load review examples
            </button>
            <button
              className="btn btn-primary"
              disabled={locked || state.records.length >= 50}
              onClick={() => edit()}
            >
              <Plus size={16} /> New record
            </button>
          </div>
          <div className="ops-workspace">
            <section
              className="ops-records"
              aria-label="Operational record list"
            >
              <div className="ops-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Record / owner</th>
                      <th>UI state</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.map((r) => (
                      <tr
                        key={r.id}
                        className={row?.id === r.id ? "selected" : ""}
                      >
                        <td>
                          <strong>{r.title}</strong>
                          <small>{r.owner}</small>
                        </td>
                        <td>
                          <span className={"ops-badge state-" + r.state}>
                            {r.state.replaceAll("_", " ")}
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn btn-outline"
                            aria-label={"Inspect " + r.title}
                            onClick={() => {
                              setSelected(r.id);
                              setAccessResult("");
                              setDigest("");
                            }}
                          >
                            Inspect <ArrowRight size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!view.length && (
                <div className="ops-empty">
                  <FileText size={26} />
                  <h4>
                    {state.records.length
                      ? "No matching records"
                      : "Your operational review starts here"}
                  </h4>
                  <p>
                    {state.records.length
                      ? "Clear the search or state filter to see your records."
                      : "Add a record or load synthetic examples to review the complete journey."}
                  </p>
                  <button
                    className="btn btn-outline"
                    onClick={() => {
                      setQuery("");
                      setFilter("all");
                      setPage(0);
                    }}
                  >
                    Clear filters
                  </button>
                </div>
              )}
              <footer className="ops-pagination">
                <span>
                  {filtered.length} results · Page {safePage + 1} of {pageCount}
                </span>
                <button
                  className="icon-btn"
                  aria-label="Previous operational page"
                  disabled={safePage === 0}
                  onClick={() => setPage(safePage - 1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-btn"
                  aria-label="Next operational page"
                  disabled={safePage + 1 >= pageCount}
                  onClick={() => setPage(safePage + 1)}
                >
                  <ChevronRight size={18} />
                </button>
              </footer>
            </section>
            {row && (
              <aside
                className="ops-details"
                aria-label="Selected operational record"
              >
                <small>SELECTED RECORD</small>
                <h4>{row.title}</h4>
                <span className={"ops-badge state-" + row.state}>
                  {row.state.replaceAll("_", " ")}
                </span>
                <dl>
                  {spec.fields
                    .filter(
                      (f) => f.type !== "json" && !f.id.startsWith("check_"),
                    )
                    .map((f) => (
                      <div key={f.id}>
                        <dt>{f.label}</dt>
                        <dd>{row.attributes[f.id]}</dd>
                      </div>
                    ))}
                </dl>
                <div className="ops-detail-actions">
                  <button
                    className="btn btn-outline"
                    disabled={locked}
                    onClick={() => edit(row)}
                  >
                    Edit details
                  </button>
                  <button
                    className="btn btn-outline"
                    disabled={locked}
                    onClick={() => {
                      const copy = {
                        ...structuredClone(row),
                        id: crypto.randomUUID(),
                        title: (row.title + " · copy").slice(0, 120),
                        state: spec.initial_state,
                      };
                      if (state.records.length < 50) {
                        onChange({
                          ...state,
                          records: [...state.records, copy],
                        });
                        setSelected(copy.id);
                      } else setError("Record limit reached.");
                    }}
                  >
                    Duplicate
                  </button>
                  <button
                    className="btn btn-outline"
                    disabled={locked}
                    onClick={() => setRemove(true)}
                  >
                    Remove from draft
                  </button>
                </div>
              </aside>
            )}
          </div>
          {row && (
            <section className="ops-specialized">
              <div className="ops-section-title">
                <div>
                  <small>
                    {spec.kind.replaceAll("_", " ").toUpperCase()} WORKSPACE
                  </small>
                  <h4>{spec.visual_title}</h4>
                </div>
                <span className="ops-badge">UI rehearsal</span>
              </div>
              <ol className="ops-pipeline" aria-label="Operational pipeline">
                {spec.steps.map((s, i) => (
                  <li
                    key={s}
                    className={i < pipelineProgress ? "complete" : ""}
                  >
                    <span>
                      {i < pipelineProgress ? <Check size={16} /> : i + 1}
                    </span>
                    <strong>{s}</strong>
                  </li>
                ))}
              </ol>
              {spec.kind === "connector" && (
                <div className="ops-two-col">
                  <article>
                    <h5>Tool input contract</h5>
                    <pre>
                      {(() => {
                        try {
                          return JSON.stringify(
                            JSON.parse(row.attributes.schema),
                            null,
                            2,
                          );
                        } catch {
                          return row.attributes.schema;
                        }
                      })()}
                    </pre>
                    <button
                      className="btn btn-outline"
                      disabled={locked}
                      onClick={() => edit(row)}
                    >
                      Edit schema & scopes
                    </button>
                  </article>
                  <article>
                    <h5>Connection review</h5>
                    <p>
                      {row.attributes.protocol} · {row.attributes.endpoint}
                    </p>
                    <dl>
                      <div>
                        <dt>Requested scope</dt>
                        <dd>{row.attributes.scopes}</dd>
                      </div>
                      <div>
                        <dt>Credential source</dt>
                        <dd>{row.attributes.secret_ref}</dd>
                      </div>
                    </dl>
                    <p>
                      Connection tests and dispatch are rehearsed below.
                      Endpoint contact remains disabled.
                    </p>
                  </article>
                </div>
              )}
              {spec.kind === "orchestration" && (
                <div className="ops-two-col">
                  <article>
                    <h5>
                      <GitBranch size={17} /> Checkpoint graph
                    </h5>
                    <div className="ops-nodegraph">
                      {spec.steps.map((s, i) => (
                        <div key={s}>
                          <span className={i < pipelineProgress ? "done" : ""}>
                            {i + 1}
                          </span>
                          <strong>{s}</strong>
                          <small>
                            {i < pipelineProgress
                              ? "Reviewed"
                              : i === pipelineProgress
                                ? "Next checkpoint"
                                : "Waiting"}
                          </small>
                        </div>
                      ))}
                    </div>
                  </article>
                  <article>
                    <h5>Run controls</h5>
                    <p>
                      Maximum steps: {row.attributes.max_steps}. Timeout:{" "}
                      {row.attributes.timeout}s.
                    </p>
                    <p>
                      Checkpoint: <code>{row.attributes.checkpoint}</code>
                    </p>
                    <p>
                      Pause, resume, cancellation and retry update this UI
                      rehearsal only. Use the event timeline to inspect every
                      transition.
                    </p>
                  </article>
                </div>
              )}
              {spec.kind === "ingestion" && (
                <div className="ops-two-col">
                  <article>
                    <h5>Extraction review</h5>
                    <p>
                      {row.attributes.source} ·{" "}
                      {Number(row.attributes.file_bytes).toLocaleString()} bytes
                    </p>
                    <p>
                      {row.attributes.language} ·{" "}
                      {row.attributes.classification}
                    </p>
                    <button
                      className="btn btn-outline"
                      onClick={() => setEvidence(true)}
                    >
                      Inspect synthetic extraction
                    </button>
                  </article>
                  <article>
                    <h5>Index handoff</h5>
                    <p>Destination: {row.attributes.collection}</p>
                    <p>
                      Parsing, OCR and indexing checkpoints are visible above.
                      UI completion does not mean the file was extracted or
                      indexed.
                    </p>
                  </article>
                </div>
              )}
              {spec.kind === "retrieval" && (
                <div className="ops-retrieval">
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      setSearchRun(searchText);
                    }}
                  >
                    <label htmlFor="ops-retrieval-query">
                      Search synthetic excerpts
                    </label>
                    <div className="ops-toolbar">
                      <input
                        id="ops-retrieval-query"
                        value={searchText}
                        maxLength={500}
                        onChange={(e) => setSearchText(e.target.value)}
                        placeholder="Enter a query…"
                        required
                      />
                      <button className="btn btn-primary">
                        Review results
                      </button>
                    </div>
                  </form>
                  <p>
                    Browser-local keyword matching over review records; this
                    does not run semantic retrieval.
                  </p>
                  {searchRun &&
                    (searched.length ? (
                      searched
                        .slice(
                          0,
                          Math.max(
                            1,
                            Math.min(50, Number(row.attributes.top_k) || 5),
                          ),
                        )
                        .map((x) => (
                          <article className="ops-citation" key={x.row.id}>
                            <strong>{x.row.attributes.citation}</strong>
                            <p>{x.row.attributes.source_excerpt}</p>
                            <small>
                              {x.hits} matching query terms · synthetic source
                            </small>
                            <button
                              className="btn btn-outline"
                              onClick={() => {
                                setSelected(x.row.id);
                                setEvidence(true);
                              }}
                            >
                              Inspect citation
                            </button>
                          </article>
                        ))
                    ) : (
                      <p role="status">
                        No synthetic source matched. Try “approval” or add
                        another source excerpt.
                      </p>
                    ))}
                </div>
              )}
              {spec.kind === "permissions" && (
                <>
                  <div className="ops-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Principal</th>
                          <th>Read</th>
                          <th>Edit</th>
                          <th>Export</th>
                        </tr>
                      </thead>
                      <tbody>
                        {state.records.map((r) => (
                          <tr key={r.id}>
                            <td>{r.attributes.principal}</td>
                            <td>Yes, within planned scope</td>
                            <td>
                              {["Editor", "Custodian"].includes(
                                r.attributes.role,
                              )
                                ? "Yes"
                                : "No"}
                            </td>
                            <td>{r.attributes.allow_export}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      setAccessResult(
                        principal === "Guest"
                          ? "Denied in UI review: guest has no assigned scope."
                          : row.state === "active"
                            ? "Allowed in UI review for assigned role and resource."
                            : "Denied in UI review: policy plan is not active.",
                      );
                    }}
                  >
                    <label htmlFor="ops-test-principal">Test principal</label>
                    <select
                      id="ops-test-principal"
                      value={principal}
                      onChange={(e) => setPrincipal(e.target.value)}
                    >
                      <option>Assigned role</option>
                      <option>Guest</option>
                    </select>
                    <button className="btn btn-outline">
                      Review access decision
                    </button>
                  </form>
                  {accessResult && (
                    <p role="status">
                      {accessResult} Actual authorization remains
                      server-enforced.
                    </p>
                  )}
                </>
              )}
              {["evaluation", "testing", "accessibility"].includes(
                spec.kind,
              ) && (
                <>
                  <div className="ops-check-results">
                    {findings.map((f) => (
                      <article key={f.id}>
                        <span>{f.label}</span>
                        <strong
                          className={
                            "result-" +
                            row.attributes[f.id]
                              .replaceAll(" ", "-")
                              .toLowerCase()
                          }
                        >
                          {row.attributes[f.id]}
                        </strong>
                      </article>
                    ))}
                  </div>
                  <p>
                    Manually recorded review outcomes. No quality benchmark,
                    penetration test, load test or accessibility certification
                    is performed by these controls.
                  </p>
                  <button
                    className="btn btn-outline"
                    disabled={locked}
                    onClick={() => edit(row)}
                  >
                    Record review results
                  </button>
                </>
              )}
              {spec.kind === "routing" && (
                <div className="ops-route-map">
                  <article>
                    <small>PRIMARY ROUTE</small>
                    <strong>{row.attributes.primary}</strong>
                  </article>
                  <ArrowRight />
                  <article>
                    <small>TIMEOUT / CIRCUIT REVIEW</small>
                    <strong>
                      {row.attributes.timeout}s · {row.attributes.retry_limit}{" "}
                      retries
                    </strong>
                  </article>
                  <ArrowRight />
                  <article>
                    <small>FALLBACK ROUTE</small>
                    <strong>{row.attributes.fallback}</strong>
                  </article>
                  <p>
                    Review the failure scenario before wiring actual
                    model-specific fallback. No model request is sent.
                  </p>
                </div>
              )}
              {spec.kind === "capacity" &&
                (() => {
                  const a = capacityEstimate(row.attributes);
                  return (
                    <>
                      <div className="ops-calculation">
                        <article>
                          <span>Planned arrivals / min</span>
                          <strong>{a.arrival}</strong>
                        </article>
                        <article>
                          <span>Estimated admission / min</span>
                          <strong>{a.admitted}</strong>
                        </article>
                        <article>
                          <span>Estimated excess / min</span>
                          <strong>{a.rejected}</strong>
                        </article>
                      </div>
                      <meter
                        min={0}
                        max={Math.max(1, a.arrival)}
                        value={a.admitted}
                        aria-label="Estimated admitted requests"
                      />
                      <p>
                        Planning estimate: min(arrivals, rate limit, concurrency
                        × 60 / average duration). This is not measured
                        throughput.
                      </p>
                    </>
                  );
                })()}
              {spec.kind === "finops" &&
                (() => {
                  const a = costEstimate(row.attributes);
                  return (
                    <>
                      <div className="ops-calculation">
                        {Object.entries(a).map(([key, value]) => (
                          <article key={key}>
                            <span>{key}</span>
                            <strong>
                              {value.toLocaleString("en-US", {
                                style: "currency",
                                currency: "USD",
                              })}
                            </strong>
                          </article>
                        ))}
                      </div>
                      <p>
                        Variance = entered actual − estimate. Remaining =
                        entered budget − actual. Values are manually entered
                        synthetic amounts; no invoice or provider billing was
                        fetched.
                      </p>
                    </>
                  );
                })()}
              {spec.kind === "identity" && (
                <div className="ops-two-col">
                  <article>
                    <h5>Member lifecycle</h5>
                    <p>{row.attributes.email}</p>
                    <p>Requested role: {row.attributes.role}</p>
                    <p>Review date: {row.attributes.expiry}</p>
                  </article>
                  <article>
                    <h5>Authentication policy review</h5>
                    <p>{row.attributes.identity_provider}</p>
                    <p>MFA: {row.attributes.mfa}</p>
                    <p>
                      No account, invitation, role grant or IdP setting is
                      created by this interface.
                    </p>
                  </article>
                </div>
              )}
              {spec.kind === "environments" && (
                <div className="ops-environments">
                  {state.records.map((r) => (
                    <button
                      key={r.id}
                      className={row.id === r.id ? "selected" : ""}
                      onClick={() => setSelected(r.id)}
                    >
                      <small>{r.attributes.environment}</small>
                      <strong>{r.attributes.workspace}</strong>
                      <span>
                        {r.attributes.region} · {r.state}
                      </span>
                    </button>
                  ))}
                  <p>
                    Selection changes this review context only. It does not
                    switch the authenticated tenant or deployment.
                  </p>
                </div>
              )}
              {spec.kind === "secrets" && (
                <div className="ops-two-col">
                  <article>
                    <h5>Reference inventory</h5>
                    <code>{row.attributes.secret_ref}</code>
                    <p>Workload: {row.attributes.scope}</p>
                    <p>Rotation plan: {row.attributes.rotation_days} days</p>
                  </article>
                  <article>
                    <h5>Egress boundary review</h5>
                    <strong>{row.attributes.host}</strong>
                    <p>{row.attributes.egress}</p>
                    <p>
                      Secret values are never requested. Rotation and network
                      enforcement require reviewed backend integration.
                    </p>
                  </article>
                </div>
              )}
              {spec.kind === "telemetry" && (
                <>
                  <div
                    className="ops-signal-chart"
                    role="img"
                    aria-label="Illustrative signal samples relative to configured threshold"
                  >
                    {[0.35, 0.5, 0.7, 1.15, 1.4, 0.9].map((n, i) => (
                      <div key={i}>
                        <span
                          style={{ height: n * 60 + "px" }}
                          className={n > 1 ? "breach" : ""}
                        />
                        <small>T{i + 1}</small>
                      </div>
                    ))}
                  </div>
                  <p>
                    Illustrative samples only; threshold{" "}
                    {row.attributes.threshold}s. No production metrics are
                    connected.
                  </p>
                  <p>
                    {row.attributes.severity} · {row.attributes.service} ·
                    Runbook {row.attributes.runbook}
                  </p>
                </>
              )}
              {spec.kind === "audit" && (
                <>
                  <p>
                    Archive: {row.attributes.archive} · Retention:{" "}
                    {row.attributes.retention_days} days · Legal hold:{" "}
                    {row.attributes.legal_hold}
                  </p>
                  <button className="btn btn-outline" onClick={hashEvidence}>
                    Compute review payload SHA-256
                  </button>
                  {digest && <output className="ops-hash">{digest}</output>}
                  <p>
                    This digest describes the current UI metadata export. It
                    does not provide immutable off-host storage or production
                    chain verification.
                  </p>
                </>
              )}
              {spec.kind === "recovery" && (
                <div className="ops-two-col">
                  <article>
                    <h5>Recovery point plan</h5>
                    <strong>{row.attributes.backup}</strong>
                    <p>Target RPO: {row.attributes.rpo} minutes</p>
                    <p>Target RTO: {row.attributes.rto} minutes</p>
                  </article>
                  <article>
                    <h5>Isolated restore destination</h5>
                    <strong>{row.attributes.target}</strong>
                    <p>Key reference: {row.attributes.encryption_ref}</p>
                    <p>
                      These are targets. No backup, decryption or restore is
                      executed; measured RPO/RTO requires a real drill.
                    </p>
                  </article>
                </div>
              )}
              {spec.kind === "delivery" && (
                <div className="ops-two-col">
                  <article>
                    <h5>Release candidate</h5>
                    <strong>{row.attributes.release}</strong>
                    <p>{row.attributes.artifact}</p>
                    <p>
                      Canary plan: {row.attributes.canary}% ·{" "}
                      {row.attributes.environment}
                    </p>
                  </article>
                  <article>
                    <h5>Rollback destination</h5>
                    <strong>{row.attributes.rollback}</strong>
                    <p>
                      Complete or fail the rehearsal to expose the rollback
                      review command. No deployment or traffic shift occurs.
                    </p>
                  </article>
                </div>
              )}
              <div className="ops-commandbar">
                <h5>
                  Available actions for “{row.state.replaceAll("_", " ")}”
                </h5>
                <div>
                  {availableCommands(spec, row).map((c) => (
                    <button
                      className="btn btn-outline"
                      key={c.id}
                      disabled={locked || state.events.length >= 100}
                      onClick={() => {
                        setCommand(c.id);
                        setScenario("happy_path");
                        setNote("");
                        setError("");
                      }}
                    >
                      {c.label} <ArrowRight size={14} />
                    </button>
                  ))}
                </div>
                <p>
                  Each action opens a review dialog. Only valid transitions are
                  offered. Failed scenarios preserve the current state.
                </p>
              </div>
              <section
                className="ops-timeline"
                aria-label="Operational event timeline"
              >
                <h5>Record event timeline</h5>
                {!events.length ? (
                  <p>
                    No events yet. Start an available action to review its state
                    transition.
                  </p>
                ) : (
                  <ol>
                    {[...events].reverse().map((e) => (
                      <li key={e.id}>
                        <strong>
                          {spec.commands.find((c) => c.id === e.command)
                            ?.label || e.command}
                        </strong>
                        <span>
                          {e.from_state} → {e.to_state} ·{" "}
                          {e.scenario.replaceAll("_", " ")}
                        </span>
                        <p>{e.note}</p>
                        <time dateTime={e.at}>
                          {new Date(e.at).toLocaleString()}
                        </time>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </section>
          )}
        </>
      )}
      {editor && (
        <Overlay
          title={
            state.records.some((r) => r.id === editor.id)
              ? "Edit operational record"
              : "New operational record"
          }
          onClose={closeEditor}
        >
          <form onSubmit={saveRecord}>
            <p>
              Use synthetic review data and secret references. Changes stay in
              the parent interface draft until Save revision.
            </p>
            <div className="ops-form-grid">
              <label>
                Record title
                <input
                  value={editor.title}
                  maxLength={120}
                  required
                  onChange={(e) =>
                    setEditor({ ...editor, title: e.target.value })
                  }
                />
                {fieldErrors.title && (
                  <small role="alert">{fieldErrors.title}</small>
                )}
              </label>
              <label>
                Responsible owner
                <input
                  value={editor.owner}
                  maxLength={120}
                  required
                  onChange={(e) =>
                    setEditor({ ...editor, owner: e.target.value })
                  }
                />
                {fieldErrors.owner && (
                  <small role="alert">{fieldErrors.owner}</small>
                )}
              </label>
              {spec.fields.map((f) => (
                <label key={f.id} className={f.type === "json" ? "wide" : ""}>
                  {f.label}
                  {f.type === "select" ? (
                    <select
                      value={editor.attributes[f.id]}
                      onChange={(e) =>
                        setEditor({
                          ...editor,
                          attributes: {
                            ...editor.attributes,
                            [f.id]: e.target.value,
                          },
                        })
                      }
                    >
                      {f.options?.map((o) => (
                        <option key={o}>{o}</option>
                      ))}
                    </select>
                  ) : f.type === "json" ? (
                    <textarea
                      rows={7}
                      value={editor.attributes[f.id]}
                      maxLength={2000}
                      onChange={(e) =>
                        setEditor({
                          ...editor,
                          attributes: {
                            ...editor.attributes,
                            [f.id]: e.target.value,
                          },
                        })
                      }
                    />
                  ) : (
                    <input
                      type={
                        ["number", "email", "date", "url"].includes(f.type)
                          ? f.type
                          : "text"
                      }
                      min={f.type === "number" ? (f.min ?? 0) : undefined}
                      max={f.type === "number" ? (f.max ?? 1000000000) : undefined}
                      step={f.type === "number" ? "any" : undefined}
                      required
                      maxLength={2000}
                      value={editor.attributes[f.id]}
                      onChange={(e) =>
                        setEditor({
                          ...editor,
                          attributes: {
                            ...editor.attributes,
                            [f.id]: e.target.value,
                          },
                        })
                      }
                    />
                  )}{" "}
                  {fieldErrors[f.id] && (
                    <small role="alert">{fieldErrors[f.id]}</small>
                  )}
                </label>
              ))}
            </div>
            <footer>
              <button
                className="btn btn-outline"
                type="button"
                onClick={closeEditor}
              >
                Cancel
              </button>
              <button className="btn btn-primary" disabled={locked}>
                Apply to interface draft
              </button>
            </footer>
          </form>
        </Overlay>
      )}
      {discardEditor && <Overlay title="Discard unapplied record edits?" onClose={()=>setDiscardEditor(false)}><p>These changes have not been applied to the parent interface draft.</p><footer><button className="btn btn-outline" onClick={()=>setDiscardEditor(false)}>Keep editing record</button><button className="btn btn-primary" onClick={()=>{setDiscardEditor(false);setEditor(null)}}>Discard record edits</button></footer></Overlay>}
      {command && row && selectedCommand && (
        <Overlay title={selectedCommand.label} onClose={() => setCommand("")}>
          <form onSubmit={runCommand}>
            <p>
              <strong>{row.title}</strong>
            </p>
            <div className="ops-transition">
              <span>{row.state}</span>
              <ArrowRight size={18} />
              <strong>{selectedCommand.to_state}</strong>
            </div>
            <p>
              This review updates UI metadata only. It cannot grant access,
              submit a business action or contact a service.
            </p>
            <label>
              Action review scenario
              <select
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
              >
                <option value="happy_path">Successful UI transition</option>
                <option value="permission_denied">Permission denied</option>
                <option value="dependency_unavailable">
                  Dependency unavailable
                </option>
                <option value="timeout_unknown">
                  Timeout / uncertain outcome
                </option>
                <option value="stale_revision">Stale revision</option>
              </select>
            </label>
            <label>
              Decision / review note
              <textarea
                rows={3}
                required
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Record what you reviewed and the expected outcome…"
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <footer>
              <button
                className="btn btn-outline"
                type="button"
                onClick={() => setCommand("")}
              >
                Keep current state
              </button>
              <button className="btn btn-primary" disabled={locked}>
                Confirm UI rehearsal
              </button>
            </footer>
          </form>
        </Overlay>
      )}
      {remove && row && (
        <Overlay
          title="Remove record from interface draft?"
          onClose={() => setRemove(false)}
        >
          <p>
            The record and its review events will be removed from the draft.
            Previous saved revisions remain available in History.
          </p>
          <footer>
            <button
              className="btn btn-outline"
              onClick={() => setRemove(false)}
            >
              Keep record
            </button>
            <button
              className="btn btn-primary"
              disabled={locked}
              onClick={() => {
                onChange({
                  records: state.records.filter((r) => r.id !== row.id),
                  events: state.events.filter((e) => e.record_id !== row.id),
                });
                setRemove(false);
                setSelected("");
              }}
            >
              Remove from draft
            </button>
          </footer>
        </Overlay>
      )}
      {evidence && row && (
        <Overlay
          title={
            spec.kind === "retrieval"
              ? "Synthetic citation detail"
              : "Synthetic extraction detail"
          }
          onClose={() => setEvidence(false)}
        >
          <p>
            <strong>{row.attributes.citation || row.attributes.source}</strong>
          </p>
          <blockquote>
            {row.attributes.source_excerpt ||
              "SYNTHETIC EXAMPLE: Purchases above USD 5,000 require independent review. This text is a UI sample, not extracted file content."}
          </blockquote>
          <p>
            Collection: {row.attributes.collection}. This review cannot
            establish source authenticity or extraction quality.
          </p>
          <button
            className="btn btn-outline"
            onClick={() => setEvidence(false)}
          >
            Close source review
          </button>
        </Overlay>
      )}
    </section>
  );
}
