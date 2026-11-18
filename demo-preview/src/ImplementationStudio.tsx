import {FunctionDesigner} from "./FunctionDesigner";
import {registerNavigationGuard} from "./navigationGuard";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import {
  freshInterface,
  interfaceFingerprint,
  validateInterface,
  plannedRequest,
  type InterfaceModule,
  type InterfaceDraft,
  type InterfaceField,
} from "./interfaceDesign";
import {
  ArrowRight,
  ArrowUpRight,
  Archive,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Cloud,
  Code2,
  Copy,
  Download,
  FileText,
  FlaskConical,
  GitBranch,
  History,
  Layers3,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {OperationalConsole} from "./OperationalConsole";
import {OperationsSurface} from "./OperationsSurface";
type Row = Record<string, any>;
const tabs = [
  ["overview", "Overview"],
  ["setup", "Configuration"],
  ["features", "Function catalog"],
  ["operations", "Operational console"],
  ["surface", "Record blueprint"],
  ["preview", "Workflow preview"],
  ["contract", "API handoff"],
  ["acceptance", "Acceptance"],
  ["history", "History"],
];
const scenarios = [
  ["happy_path", "Happy-path review"],
  ["invalid_configuration", "Invalid configuration"],
  ["permission_denied", "Permission denied"],
  ["dependency_unavailable", "Dependency unavailable"],
  ["timeout_unknown", "Timeout / uncertain outcome"],
  ["stale_revision", "Stale revision"],
];
function saveJson(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name + ".json";
  a.click();
  URL.revokeObjectURL(url);
}
function Chips({ items }: { items: string[] }) {
  return (
    <div className="studio-chips">
      {items.map((x) => (
        <span key={x}>{x.replaceAll("_", " ")}</span>
      ))}
    </div>
  );
}
function Dialog({
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
    const prior = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      prior?.focus();
    };
  }, []);
  return (
    <dialog
      className="studio-dialog"
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-label={title}
    >
      <header>
        <div>
          <span className="studio-overline">NEXUS / INTERFACE REVIEW</span>
          <h2>{title}</h2>
        </div>
        <button
          className="icon-btn"
          aria-label="Close interface dialog"
          onClick={onClose}
        >
          <X size={21} />
        </button>
      </header>
      <div className="studio-dialog-body">{children}</div>
    </dialog>
  );
}
function Field({
  field,
  value,
  error,
  onChange,
  disabled,
}: {
  field: InterfaceField;
  value: any;
  error?: string;
  onChange: (value: any) => void;
  disabled: boolean;
}) {
  const id = "interface-field-" + field.id;
  return (
    <div
      className={
        "studio-field " + (field.type === "toggle" ? "studio-toggle" : "")
      }
    >
      <label htmlFor={id}>
        {field.label}
        {field.type === "reference" && <span>Reference only</span>}
      </label>
      {field.type === "select" ? (
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!error}
        >
          {field.options?.map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      ) : field.type === "toggle" ? (
        <div>
          <input
            id={id}
            type="checkbox"
            checked={Boolean(value)}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span>{value ? "Included in design" : "Excluded from design"}</span>
        </div>
      ) : field.type === "list" ? (
        <>
          <input
            id={id}
            value={Array.isArray(value) ? value.join(", ") : ""}
            disabled={disabled}
            onChange={(e) =>
              onChange(e.target.value.split(",").map((x) => x.trim()))
            }
            aria-invalid={!!error}
          />
          <small>Comma-separated values; planning metadata only.</small>
        </>
      ) : field.type === "number" ? (
        <input
          id={id}
          type="number"
          min={field.min}
          max={field.max}
          value={value}
          disabled={disabled}
          onChange={(e) =>
            onChange(e.target.value === "" ? "" : Number(e.target.value))
          }
          aria-invalid={!!error}
        />
      ) : (
        <input
          id={id}
          type={field.type === "url" ? "url" : "text"}
          value={value || ""}
          maxLength={1000}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="off"
          aria-invalid={!!error}
        />
      )}{" "}
      {error && (
        <p className="studio-field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
export function ImplementationStudio({
  me,
  onNavigate,
}: {
  me: Row;
  onNavigate: (view: string) => void;
}) {
  const [modules, setModules] = useState<InterfaceModule[]>([]),
    [assets, setAssets] = useState<Row[]>([]),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [selected, setSelected] = useState(
      new URLSearchParams(location.search).get("design") ||
        "customer_connectors",
    ),
    [area, setArea] = useState("All"),
    [query, setQuery] = useState(""),
    [tab, setTab] = useState(new URL(location.href).searchParams.has("feature")?"features":"overview"),
    [step, setStep] = useState(0);
  const [draft, setDraft] = useState<InterfaceDraft | null>(null),
    [baseline, setBaseline] = useState(""),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [history, setHistory] = useState<Row[]>([]),
    [run, setRun] = useState<Row | null>(null),
    [scenario, setScenario] = useState("happy_path"),
    [action, setAction] = useState("");
  const [discard, setDiscard] = useState(false);
  const [nestedDirty,setNestedDirty]=useState(false);
  const pendingNavigation = useRef<() => void>(() => {});
  const draftRef = useRef<InterfaceDraft | null>(null);
  draftRef.current = draft;
  const canEdit = me.permissions?.includes("operate");
  const module = modules.find((m) => m.id === selected);
  const saved = assets.filter((a) => a.config.module === selected);
  const dirty = nestedDirty || Boolean(draft && interfaceFingerprint(draft) !== baseline);
  const archived = draft?.status === "archived";
  const disabled = busy || !canEdit || archived;
  const areas = useMemo(
    () => ["All", ...new Set(modules.map((m) => m.area))],
    [modules],
  );
  const filtered = modules.filter(
    (m) =>
      (area === "All" || m.area === area) &&
      (m.title + " " + m.description)
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  function openDraft(row: InterfaceDraft | Row) {
    const clean = structuredClone(row) as InterfaceDraft;
    setNestedDirty(false);
    setDraft(clean);
    setBaseline(interfaceFingerprint(clean));
    setErrors({});
    setRun(null);
    setHistory([]);
  }
  async function load() {
    setLoading(true);
    try {
      const [catalog, w] = await Promise.all([
        api("/v1/interface-catalog"),
        api("/v1/workbench"),
      ]);
      setModules(catalog.modules);
      const blueprints = w.assets.filter((a: Row) => a.kind === "blueprint");
      setAssets(blueprints);
      setError("");
      const chosen =
        catalog.modules.find((m: InterfaceModule) => m.id === selected) ||
        catalog.modules[0];
      setSelected(chosen.id);
      if (!draftRef.current)
        openDraft(
          blueprints.find(
            (a: Row) =>
              a.config.module === chosen.id && a.status !== "archived",
          ) || freshInterface(chosen),
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  useEffect(() => {
    function leave(e: BeforeUnloadEvent) {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, [dirty]);
  useEffect(() => {
    if (!dirty) return;
    return registerNavigationGuard(fn => {pendingNavigation.current=fn;setDiscard(true);});
  }, [dirty]);
  function navigate(fn: () => void) {
    if (dirty) {
      pendingNavigation.current = fn;
      setDiscard(true);
    } else fn();
  }
  function chooseModule(id: string) {
    navigate(() => {
      const next = modules.find((m) => m.id === id);
      if (!next) return;
      setSelected(id);
      setTab("overview");
      setStep(0);
      setAction("");
      const url = new URL(location.href);
      url.searchParams.set("design", id);
      url.searchParams.delete("feature");
      window.history.replaceState(null, "", url);
      openDraft(
        assets.find((a) => a.config.module === id && a.status !== "archived") ||
          freshInterface(next),
      );
      setNotice("");
    });
  }
  function update(field: string, value: any) {
    if (!draft) return;
    setDraft({
      ...draft,
      config: {
        ...draft.config,
        values: { ...draft.config.values, [field]: value },
      },
    });
    setErrors((e) => ({ ...e, [field]: "" }));
  }
  async function refreshAssets() {
    const w = await api("/v1/workbench");
    setAssets(w.assets.filter((a: Row) => a.kind === "blueprint"));
  }
  async function save() {
    if (!draft || !module) return;
    const found = validateInterface(module, draft);
    setErrors(found);
    if (Object.keys(found).length) {
      setError("Review the highlighted interface fields before saving.");
      setTab(found.function_plans?"features":"setup");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body = {
        kind: "blueprint",
        name: draft.name.trim(),
        description: draft.description,
        config: draft.config,
      };
      const row = await api(
        "/v1/workbench" + (draft.id ? "/" + draft.id : ""),
        draft.id ? "PUT" : "POST",
        draft.id ? { ...body, expected_version: draft.version } : body,
      );
      await refreshAssets();
      openDraft(row);
      setNotice("Interface revision saved. No runtime service was activated.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadExamples() {
    setBusy(true);
    setError("");
    try {
      const response = await api("/v1/interface-starter", "POST", {});
      const w = await api("/v1/workbench");
      const list = w.assets.filter((a: Row) => a.kind === "blueprint");
      setAssets(list);
      if (module && !dirty)
        openDraft(
          list.find(
            (a: Row) =>
              a.config.module === module.id && a.status !== "archived",
          ) || freshInterface(module),
        );
      setNotice(
        `${response.created} synthetic interface examples added. Runtime integrations remain inactive.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function preview(actionId = "") {
    if (!draft?.id || dirty) {
      setError("Save this interface revision before generating its preview.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api("/v1/workbench/" + draft.id + "/run", "POST", {
        variables: { design_action: actionId, design_scenario: scenario },
      });
      setRun(result);
      if (!actionId) setTab("preview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function check() {
    if (!draft?.id || dirty) return;
    setBusy(true);
    try {
      const row = await api("/v1/workbench/" + draft.id + "/validate", "POST", {
        expected_version: draft.version,
      });
      await refreshAssets();
      openDraft(row);
      setNotice(
        "Interface schema checked. Runtime connectivity was not tested.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function duplicate() {
    if (!draft) return;
    setBusy(true);
    try {
      const row = await api("/v1/workbench", "POST", {
        kind: "blueprint",
        name: (draft.name + " · copy").slice(0, 120),
        description: draft.description,
        config: draft.config,
      });
      await refreshAssets();
      openDraft(row);
      setNotice("A separate interface draft was created.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function archive() {
    if (!draft?.id) return;
    setBusy(true);
    try {
      const row = await api("/v1/workbench/" + draft.id + "/archive", "POST", {
        expected_version: draft.version,
      });
      await refreshAssets();
      openDraft(row);
      setNotice("Interface archived; revision history is preserved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function historyTab() {
    setTab("history");
    if (!draft?.id) {
      setHistory([]);
      return;
    }
    setBusy(true);
    try {
      setHistory(await api("/v1/workbench/" + draft.id + "/history"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (loading && !modules.length)
    return (
      <section className="studio-loading" role="status">
        <LoaderCircle size={26} /> Loading enterprise interface catalog…
      </section>
    );
  if (!module || !draft)
    return (
      <section className="error" role="alert">
        {error || "The interface catalog is unavailable."}
        <button className="btn btn-outline" onClick={load}>
          Retry catalog
        </button>
      </section>
    );
  const reviewed = module.criteria.filter(
    (c) => draft.config.ui_checks[c.id],
  ).length;
  const currentAction = module.actions.find((a) => a.id === action);
  const fields = module.fields.filter(
    (f) => f.section === ["Setup", "Controls", "Review"][step],
  );
  const previewResult = run?.result;
  const resultView = previewResult && (
    <div className="studio-result">
      <div className="studio-result-top">
        <strong>
          <FlaskConical size={17} /> Interface preview
        </strong>
        <span>Saved revision {run.asset_version}</span>
        <button
          className="text-btn"
          onClick={() => saveJson("NEXUS_Interface_Preview", run)}
        >
          <Download size={15} /> Export
        </button>
      </div>
      <p>{previewResult.boundary}</p>
      <div className="studio-preview-stats">
        <span>
          Provider calls <b>{previewResult.provider_calls}</b>
        </span>
        <span>
          Business effects <b>{previewResult.business_effects}</b>
        </span>
        <span>
          Scenario <b>{previewResult.scenario?.replaceAll("_", " ")}</b>
        </span>
      </div>
      <ol className="studio-timeline">
        {previewResult.steps?.map((s: Row) => (
          <li key={s.id}>
            <span
              className={
                s.status === "design_checked"
                  ? "studio-dot good"
                  : "studio-dot caution"
              }
            />
            <div>
              <strong>{s.label}</strong>
              <span className="studio-state">
                {s.status.replaceAll("_", " ")}
              </span>
              <p>{s.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
  return (
    <div className="implementation-studio">
      <section className="studio-intro">
        <div>
          <span className="studio-overline">
            ENTERPRISE INTERFACE BLUEPRINT
          </span>
          <h2>
            Design the platform.
            <br />
            <em>Activate it in controlled stages.</em>
          </h2>
          <p>
            A complete interface workspace for the 18 production roadmap areas.
            Save and review the UI contracts before implementing each backend
            integration.
          </p>
          <div className="studio-intro-chips">
            <span>
              <Layers3 size={15} /> {modules.length} module interfaces
            </span>
            <span>
              <FileText size={15} />{" "}
              {modules.reduce((n, m) => n + m.fields.length, 0)} configuration
              fields
            </span>
            <span>
              <Code2 size={15} />{" "}
              {modules.reduce((n, m) => n + m.actions.length, 0)} planned action
              contracts
            </span>
          </div>
        </div>
        <div className="studio-intro-aside">
          <div className="studio-status">
            <span /> UI-FIRST DELIVERY
          </div>
          <strong>{assets.length}</strong>
          <span>saved interface plans in this workspace</span>
          <small>Drafts and design previews do not activate services.</small>
          {me.mode === "local" && me.permissions?.includes("policy") && (
            <button
              className="btn btn-outline"
              disabled={busy}
              onClick={loadExamples}
            >
              <Sparkles size={16} /> Load interface examples
            </button>
          )}
        </div>
      </section>
      {error && (
        <div className="error" role="alert">
          {error}
          <button
            className="icon-btn"
            aria-label="Dismiss studio error"
            onClick={() => setError("")}
          >
            <X size={17} />
          </button>
        </div>
      )}
      {notice && (
        <div className="studio-notice" role="status">
          <CheckCircle2 size={18} />
          <span>{notice}</span>
          <button
            className="icon-btn"
            aria-label="Dismiss studio confirmation"
            onClick={() => setNotice("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <div className="studio-layout">
        <aside
          className="studio-explorer"
          aria-label="Enterprise interface modules"
        >
          <header>
            <strong>Module explorer</strong>
            <span>{modules.length} interfaces</span>
          </header>
          <label className="studio-search">
            <Search size={16} />
            <input
              aria-label="Search interface modules"
              placeholder="Find an interface…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Interface area"
            value={area}
            onChange={(e) => setArea(e.target.value)}
          >
            {areas.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
          <nav>
            {filtered.length === 0 ? (
              <p>No matching interfaces.</p>
            ) : (
              filtered.map((m, i) => (
                <button
                  key={m.id}
                  aria-current={selected === m.id ? "page" : undefined}
                  className={selected === m.id ? "active" : ""}
                  disabled={busy}
                  onClick={() => chooseModule(m.id)}
                >
                  <span>{String(modules.indexOf(m) + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{m.title}</strong>
                    <small>{m.area}</small>
                  </div>
                  <ChevronRight size={15} />
                </button>
              ))
            )}
          </nav>
          <footer>
            <ShieldCheck size={16} />
            <span>Interface plans are separate from runtime acceptance.</span>
          </footer>
        </aside>
        <section className="studio-workspace">
          <header className="studio-workspace-heading">
            <div>
              <span className="studio-overline">
                {module.area} / INTERFACE DESIGN
              </span>
              <h2>{module.title}</h2>
              <p>{module.tagline}</p>
            </div>
            <button
              className="icon-btn"
              disabled={busy}
              onClick={refreshAssets}
              aria-label="Refresh interface plans"
            >
              <RefreshCw size={19} />
            </button>
          </header>
          <div className="studio-draftbar">
            <label>
              Saved interface plan
              <select
                aria-label="Saved interface plan"
                value={draft.id || ""}
                disabled={busy}
                onChange={(e) => {
                  const selected = e.target.value;
                  navigate(() =>
                    openDraft(
                      saved.find((a) => a.id === selected) ||
                        freshInterface(module),
                    ),
                  );
                }}
              >
                <option value="">New unsaved plan</option>
                {saved.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · v{a.version}
                    {a.status === "archived" ? " · archived" : ""}
                  </option>
                ))}
              </select>
            </label>
            <div>
              <span className={"studio-save-state " + (dirty ? "dirty" : "")}>
                {dirty
                  ? "Unsaved changes"
                  : draft.id
                    ? "Saved revision " + draft.version
                    : "New interface draft"}
              </span>
              <button
                className="btn btn-primary"
                disabled={disabled}
                onClick={save}
              >
                <Check size={16} />{" "}
                {draft.id ? "Save revision" : "Save interface plan"}
              </button>
            </div>
          </div>
          <div
            className="studio-tabs"
            role="tablist"
            aria-label="Interface workspace sections"
            onKeyDown={(e) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key))
                return;
              e.preventDefault();
              const buttons = Array.from(
                e.currentTarget.querySelectorAll<HTMLButtonElement>(
                  '[role="tab"]',
                ),
              );
              const i = buttons.indexOf(
                document.activeElement as HTMLButtonElement,
              );
              const next =
                e.key === "Home"
                  ? 0
                  : e.key === "End"
                    ? buttons.length - 1
                    : (i + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) %
                      buttons.length;
              buttons[next].click();
              buttons[next].focus();
            }}
          >
            {tabs.map(([id, label]) => (
              <button
                key={id}
                role="tab"
                id={"studio-tab-" + id}
                aria-controls={"studio-panel-" + id}
                aria-selected={tab === id}
                tabIndex={tab === id ? 0 : -1}
                onClick={() => (id === "history" ? historyTab() : setTab(id))}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            className="studio-panel"
            role="tabpanel"
            id={"studio-panel-" + tab}
            aria-labelledby={"studio-tab-" + tab}
          >
            {tab === "features" && <FunctionDesigner key={module.id+":"+(draft.id||"new")} module={module} draft={draft} disabled={disabled} onNavigate={onNavigate} onChange={function_plans=>setDraft({...draft,config:{...draft.config,function_plans}})}/>}
            {tab === "operations" && <OperationalConsole key={module.id+":"+(draft.id||"new")} module={module} draft={draft} disabled={disabled} onEditorDirtyChange={setNestedDirty} onChange={operational_state=>setDraft({...draft,config:{...draft.config,operational_state}})}/>}
            {tab === "overview" && (
              <>
                <div className="studio-module-description">
                  <div>
                    <h3>End-to-end interface scope</h3>
                    <p>{module.description}</p>
                  </div>
                  <span className="studio-boundary-badge">
                    {module.runtime_state==="partial_runtime"?"Partial runtime available":"Runtime activation pending"}
                  </span>
                </div>
                <div className="studio-section-title"><div><h3>Detailed long-term functions</h3><p>{module.features.length} feature screens cover the remaining capabilities, permissions, error states and backend handoff.</p></div><button className="btn btn-outline" onClick={()=>setTab("features")}>Open function catalog <ArrowRight size={16}/></button></div>
                <div className="studio-section-title"><div><h3>{module.operations.visual_title}</h3><p>Open the dedicated operational experience for this module, including forms, state transitions and review history.</p></div><button className="btn btn-primary" onClick={()=>setTab("operations")}>Open operational console <ArrowRight size={16}/></button></div>
                <div
                  className="studio-journey"
                  aria-label="Planned user journey"
                >
                  {module.stages.map((s, i) => (
                    <button
                      key={s.id}
                      onClick={() => {
                        setStep(Math.min(2, Math.floor(i / 2)));
                        setTab("setup");
                      }}
                    >
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      <strong>{s.label}</strong>
                      <small>Review interface</small>
                      {i < module.stages.length - 1 && (
                        <ChevronRight size={14} />
                      )}
                    </button>
                  ))}
                </div>
                <div className="studio-section-title">
                  <div>
                    <h3>Actions & control surfaces</h3>
                    <p>
                      Every action has a UI review flow and a planned
                      integration contract.
                    </p>
                  </div>
                </div>
                <div className="studio-action-grid">
                  {module.actions.map((a, i) => (
                    <article key={a.id}>
                      <div className={"studio-action-symbol tone-" + i}>
                        {i === 0 ? (
                          <Play size={20} />
                        ) : i === 1 ? (
                          <GitBranch size={20} />
                        ) : (
                          <ShieldCheck size={20} />
                        )}
                      </div>
                      <h4>{a.label}</h4>
                      <p>{a.description}</p>
                      <span>Planned runtime action</span>
                      <button
                        className="text-btn"
                        onClick={() => {
                          setAction(a.id);
                          setRun(null);
                        }}
                      >
                        Review action UI <ArrowRight size={15} />
                      </button>
                    </article>
                  ))}
                </div>
                <div className="studio-overview-bottom">
                  <section>
                    <h3>Designed failure states</h3>
                    <Chips items={module.failure_states} />
                    <p>
                      Review an error scenario in Workflow preview before wiring
                      real services.
                    </p>
                    <button
                      className="text-btn"
                      onClick={() => setTab("preview")}
                    >
                      Open workflow preview <ArrowUpRight size={14} />
                    </button>
                  </section>
                  <section>
                    <h3>Working control-plane workspace</h3>
                    {module.runtime_note&&<p>{module.runtime_note}</p>}
                    <p>
                      Existing implemented functions remain available in their
                      original workspace.
                    </p>
                    <button
                      className="btn btn-outline"
                      onClick={() =>
                        onNavigate(module.existing_view)
                      }
                    >
                      Open working workspace <ArrowUpRight size={15} />
                    </button>
                  </section>
                </div>
              </>
            )}
            {tab === "surface" && <OperationsSurface module={module} draft={draft} disabled={Boolean(disabled)} onChange={rows=>setDraft({...draft,config:{...draft.config,surface_rows:rows}})}/>}
          {tab === "setup" && (
              <>
                <div className="studio-section-title">
                  <div>
                    <h3>Configuration designer</h3>
                    <p>
                      These settings describe the planned interface. They do not
                      change server runtime configuration.
                    </p>
                  </div>
                  <span className="studio-boundary-badge">
                    Planning metadata
                  </span>
                </div>
                <div className="studio-wizard" aria-label="Configuration steps">
                  {["Setup", "Controls", "Review"].map((s, i) => (
                    <button
                      className={step === i ? "active" : ""}
                      key={s}
                      onClick={() => setStep(i)}
                    >
                      <span>{i + 1}</span>
                      {s}
                    </button>
                  ))}
                </div>
                <div className="studio-form-grid">
                  {step === 0 && (
                    <>
                      <div className="studio-field">
                        <label htmlFor="interface-name">
                          Interface plan name
                        </label>
                        <input
                          id="interface-name"
                          value={draft.name}
                          maxLength={120}
                          disabled={disabled}
                          onChange={(e) =>
                            setDraft({ ...draft, name: e.target.value })
                          }
                        />
                        {errors.name && (
                          <p className="studio-field-error">{errors.name}</p>
                        )}
                      </div>
                      <div className="studio-field">
                        <label htmlFor="interface-description">
                          Description
                        </label>
                        <input
                          id="interface-description"
                          value={draft.description}
                          maxLength={500}
                          disabled={disabled}
                          onChange={(e) =>
                            setDraft({ ...draft, description: e.target.value })
                          }
                        />
                      </div>
                    </>
                  )}
                  {fields.map((f) => (
                    <Field
                      key={f.id}
                      field={f}
                      value={draft.config.values[f.id]}
                      error={errors[f.id]}
                      disabled={disabled}
                      onChange={(value) => update(f.id, value)}
                    />
                  ))}
                  {step === 2 && (
                    <div className="studio-field studio-full">
                      <label htmlFor="interface-phase">
                        Implementation planning phase
                      </label>
                      <select
                        id="interface-phase"
                        disabled={disabled}
                        value={draft.config.phase}
                        onChange={(e) =>
                          setDraft({
                            ...draft,
                            config: { ...draft.config, phase: e.target.value },
                          })
                        }
                      >
                        <option value="planned">Planned interface</option>
                        <option value="ui_reviewed">UI reviewed</option>
                        <option value="backend_in_progress">
                          Backend implementation in progress
                        </option>
                        <option value="staging_review">
                          Staging review planned
                        </option>
                      </select>
                      {errors.phase && (
                        <p className="studio-field-error">{errors.phase}</p>
                      )}
                      <small>
                        Review all interface criteria in Acceptance before
                        advancing. This phase never activates a service.
                      </small>
                    </div>
                  )}
                </div>
                <div className="studio-wizard-footer">
                  <button
                    className="btn btn-outline"
                    disabled={step === 0}
                    onClick={() => setStep((s) => s - 1)}
                  >
                    Previous step
                  </button>
                  <span>
                    {step + 1} of 3 · {module.fields.length} configured controls
                  </span>
                  {step < 2 ? (
                    <button
                      className="btn btn-primary"
                      onClick={() => setStep((s) => s + 1)}
                    >
                      Continue <ArrowRight size={15} />
                    </button>
                  ) : (
                    <button
                      className="btn btn-primary"
                      disabled={disabled}
                      onClick={save}
                    >
                      Save interface revision
                    </button>
                  )}
                </div>
                <div className="studio-safety-note">
                  <ShieldCheck size={17} />
                  <p>
                    Store references and design metadata only. Actual secret
                    material, deployment access and runtime enforcement belong
                    to the reviewed backend implementation.
                  </p>
                </div>
              </>
            )}
            {tab === "preview" && (
              <>
                <div className="studio-section-title">
                  <div>
                    <h3>Workflow review & failure simulation</h3>
                    <p>
                      Previews use the saved interface revision. No real runtime
                      command is dispatched.
                    </p>
                  </div>
                </div>
                <div className="studio-preview-controls">
                  <label>
                    Review scenario
                    <select
                      aria-label="Workflow review scenario"
                      value={scenario}
                      onChange={(e) => setScenario(e.target.value)}
                    >
                      {scenarios.map(([v, label]) => (
                        <option key={v} value={v}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="btn btn-primary"
                    disabled={disabled || !draft.id || dirty}
                    onClick={() => preview()}
                  >
                    <Play size={16} /> Generate design preview
                  </button>
                </div>
                {(!draft.id || dirty) && (
                  <p className="studio-inline-note">
                    Save the current revision to enable the interface preview.
                  </p>
                )}
                {resultView || (
                  <div className="studio-preview-empty">
                    <FlaskConical size={30} />
                    <h3>Inspect the journey before implementation</h3>
                    <p>
                      Choose a scenario and generate a saved preview. The trace
                      will show design checkpoints and the selected failure
                      state.
                    </p>
                    <Chips items={module.stages.map((s) => s.label)} />
                  </div>
                )}
              </>
            )}
            {tab === "contract" && (
              <>
                <div className="studio-section-title">
                  <div>
                    <h3>Backend implementation handoff</h3>
                    <p>
                      The routes below are planned contracts, not active API
                      endpoints.
                    </p>
                  </div>
                  <button
                    className="btn btn-outline"
                    onClick={() =>
                      saveJson("NEXUS_" + module.id + "_API_Handoff", {
                        module: module.id,
                        contracts: module.actions,
                        request: plannedRequest(module, draft),
                        values_schema: module.fields,
                        runtime_activated: false,
                      })
                    }
                  >
                    <Download size={15} /> Export handoff
                  </button>
                </div>
                <div className="studio-contracts">
                  {module.actions.map((a) => (
                    <details key={a.id}>
                      <summary>
                        <span>{a.method}</span>
                        <strong>{a.label}</strong>
                        <code>{a.path}</code>
                      </summary>
                      <div>
                        <p>{a.description}</p>
                        <dl>
                          <div>
                            <dt>Request identity</dt>
                            <dd>
                              Scoped session, authorized role, CSRF and
                              idempotency key
                            </dd>
                          </div>
                          <div>
                            <dt>Resource control</dt>
                            <dd>
                              Bind resource identifier and expected
                              configuration revision
                            </dd>
                          </div>
                        </dl>
                        <h4>Planned response states</h4>
                        <Chips items={a.response_states} />
                        <h4>Required error states</h4>
                        <Chips items={a.errors} />
                        <h4>Example implementation request</h4>
                        <pre>
                          {JSON.stringify(
                            plannedRequest(module, draft),
                            null,
                            2,
                          )}
                        </pre>
                      </div>
                    </details>
                  ))}
                </div>
                <div className="studio-activation">
                  <h3>Step-by-step activation sequence</h3>
                  {module.activation_steps.map((s, i) => (
                    <div key={s}>
                      <span>{i + 1}</span>
                      <strong>{s}</strong>
                      <span>Required</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            {tab === "acceptance" && (
              <>
                <div className="studio-section-title">
                  <div>
                    <h3>Interface review & acceptance handoff</h3>
                    <p>
                      Record a UI review for this plan. Production acceptance is
                      tracked separately.
                    </p>
                  </div>
                  <span className="studio-boundary-badge">
                    {reviewed}/{module.criteria.length} interface checks
                    reviewed
                  </span>
                </div>
                <div className="studio-criteria">
                  {module.criteria.map((c) => (
                    <label key={c.id}>
                      <input
                        type="checkbox"
                        checked={Boolean(draft.config.ui_checks[c.id])}
                        disabled={disabled}
                        onChange={(e) =>
                          setDraft({
                            ...draft,
                            config: {
                              ...draft.config,
                              ui_checks: {
                                ...draft.config.ui_checks,
                                [c.id]: e.target.checked,
                              },
                            },
                          })
                        }
                      />
                      <div>
                        <strong>{c.label}</strong>
                        <span>
                          Manual interface review · saved with the plan revision
                        </span>
                      </div>
                    </label>
                  ))}
                </div>
                <div className="studio-acceptance-grid">
                  <section>
                    <ClipboardCheck size={23} />
                    <h3>UI review</h3>
                    <p>
                      Check configuration, actions, errors, permissions and
                      evidence presentation before implementing runtime
                      behavior.
                    </p>
                    <button
                      className="btn btn-outline"
                      disabled={disabled}
                      onClick={save}
                    >
                      Save review notes
                    </button>
                  </section>
                  <section>
                    <ShieldCheck size={23} />
                    <h3>Production acceptance</h3>
                    <p>
                      A UI checklist does not certify the service.
                      Implementation and staging evidence remain required.
                    </p>
                    <button
                      className="btn btn-outline"
                      onClick={() => onNavigate("operations")}
                    >
                      Open readiness board <ArrowUpRight size={15} />
                    </button>
                  </section>
                </div>
              </>
            )}
            {tab === "history" && (
              <>
                <div className="studio-section-title">
                  <div>
                    <h3>Interface revision history</h3>
                    <p>
                      Saved configuration, planning phase and UI review
                      decisions remain versioned.
                    </p>
                  </div>
                  <button
                    className="btn btn-outline"
                    disabled={busy || !draft.id}
                    onClick={historyTab}
                  >
                    <RefreshCw size={15} /> Refresh history
                  </button>
                </div>
                {history.length === 0 ? (
                  <div className="studio-preview-empty">
                    <History size={28} />
                    <p>
                      {draft.id
                        ? "No revision history is available."
                        : "Save an interface plan to create its first revision."}
                    </p>
                  </div>
                ) : (
                  history.map((h) => (
                    <details className="studio-history-row" key={h.id}>
                      <summary>
                        <strong>Revision {h.version}</strong>
                        <span>
                          {h.snapshot.status === "validated"
                            ? "Schema checked"
                            : h.snapshot.status}
                        </span>
                        <time>
                          {new Date(h.created * 1000).toLocaleString()}
                        </time>
                      </summary>
                      <div>
                        <p>{h.snapshot.name}</p>
                        <pre>{JSON.stringify(h.snapshot.config, null, 2)}</pre>
                        <button
                          className="text-btn"
                          onClick={() =>
                            saveJson(
                              "NEXUS_Interface_Revision_" + h.version,
                              h.snapshot,
                            )
                          }
                        >
                          <Download size={15} /> Export revision
                        </button>
                      </div>
                    </details>
                  ))
                )}
              </>
            )}
          </div>
          <footer className="studio-editor-footer">
            <span>
              <FileText size={15} />{" "}
              {draft.id
                ? "Versioned interface specification"
                : "Unsaved interface specification"}
            </span>
            <div>
              <button
                className="text-btn"
                disabled={!draft.id || dirty || disabled}
                onClick={check}
              >
                <ShieldCheck size={15} /> Check saved schema
              </button>
              <button
                className="text-btn"
                disabled={!canEdit || busy}
                onClick={duplicate}
              >
                <Copy size={15} />{" "}
                {archived ? "Restore as new draft" : "Duplicate plan"}
              </button>
              <button
                className="text-btn"
                onClick={() =>
                  saveJson("NEXUS_" + module.id + "_Interface", draft)
                }
              >
                <Download size={15} /> Export plan
              </button>
              {draft.id && !archived && (
                <button
                  className="text-btn studio-archive"
                  disabled={disabled || dirty}
                  onClick={archive}
                >
                  <Archive size={15} /> Archive
                </button>
              )}
            </div>
          </footer>
        </section>
      </div>
      {currentAction && (
        <Dialog title={currentAction.label} onClose={() => setAction("")}>
          <p className="studio-dialog-description">
            {currentAction.description}
          </p>
          <div className="studio-safety-note">
            <ShieldCheck size={18} />
            <p>
              This is an interface review. The runtime action remains
              unimplemented until its backend contract is completed.
            </p>
          </div>
          <label className="studio-field">
            Review scenario
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
            >
              {scenarios.map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="studio-contract-summary">
            <span>{currentAction.method} · planned endpoint</span>
            <code>{currentAction.path}</code>
            <p>
              Preview uses saved revision {draft.version || "—"}. Save modified
              or new plans first.
            </p>
          </div>
          <div className="studio-dialog-actions">
            <button
              className="btn btn-outline"
              onClick={() => {
                setAction("");
                setTab("contract");
              }}
            >
              Inspect API handoff
            </button>
            <button
              className="btn btn-primary"
              disabled={disabled || !draft.id || dirty}
              onClick={() => preview(currentAction.id)}
            >
              <Play size={15} /> Generate action preview
            </button>
          </div>
          {resultView}
        </Dialog>
      )}
      {discard && (
        <Dialog
          title="Keep your unsaved interface changes?"
          onClose={() => setDiscard(false)}
        >
          <p>
            You have an edited interface draft. Save it before switching, or
            explicitly discard the unsaved changes.
          </p>
          <div className="studio-dialog-actions">
            <button
              className="btn btn-primary"
              onClick={() => setDiscard(false)}
            >
              Keep editing
            </button>
            <button
              className="btn btn-outline"
              onClick={() => {
                setDiscard(false);
                pendingNavigation.current();
              }}
            >
              Discard and switch
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
