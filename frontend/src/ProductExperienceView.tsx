import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Search,
  Layers3,
  ShieldCheck,
  CheckCircle2,
  Bell,
  Download,
  Plus,
  RefreshCw,
  HelpCircle,
  Compass,
  ListChecks,
  Activity,
  LockKeyhole,
  Upload,
} from "lucide-react";
import { api } from "./api";
import type { InterfaceModule } from "./interfaceDesign";
import type { FunctionDefinition } from "./functionPlans";
import { Modal } from "./RuntimeDialog";
import { registerNavigationGuard } from "./navigationGuard";
import {
  detailTabs,
  journeys,
  newUiRecord,
  phases,
  phaseFor,
  previewTransition,
  screenStates,
  stateGuidance,
  uiInputs,
  type ReviewRole,
  type ScreenState,
  type UiRecord,
} from "./productExperience";
import {
  HANDOFF_LIMIT,
  UI_RECORD_LIMIT,
  makeHandoff,
  parseHandoff,
  reviewComplete,
  reviewCriteria,
  type ReviewChecks,
  type ImportedHandoff,
} from "./uiHandoff";
import "./product.css";
type Props = {
  me: Record<string, any>;
  onNavigate: (page: string) => void;
  onDesign: (module: string, feature: string) => void;
};
const pretty = (s: string) => s.replaceAll("_", " ");
function download(data: unknown) {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = u;
  a.download = "NEXUS_UI_Phase_Handoff.json";
  a.click();
  URL.revokeObjectURL(u);
}
export function ProductExperience({ me, onNavigate, onDesign }: Props) {
  const [modules, setModules] = useState<InterfaceModule[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [view, setView] = useState("overview"),
    [moduleId, setModule] = useState("customer_connectors"),
    [featureId, setFeature] = useState(""),
    [q, setQ] = useState(""),
    [tab, setTab] = useState<(typeof detailTabs)[number]>("Overview"),
    [role, setRole] = useState<ReviewRole>("Operator"),
    [environment, setEnvironment] = useState("Staging design"),
    [screen, setScreen] = useState<ScreenState>("ready"),
    [rows, setRows] = useState<UiRecord[]>([]),
    [selected, setSelected] = useState(""),
    [draft, setDraft] = useState<UiRecord | null>(null),
    [command, setCommand] = useState(""),
    [pinned, setPinned] = useState<UiRecord | null>(null),
    [note, setNote] = useState(""),
    [scopeCheck, setScopeCheck] = useState(false),
    [effectCheck, setEffectCheck] = useState(false),
    [notice, setNotice] = useState(""),
    [reviewed, setReviewed] = useState<string[]>([]),
    [journeyId, setJourney] = useState(""),
    [journeyIndex, setJourneyIndex] = useState(0),
    [discard, setDiscard] = useState(false),
    [help, setHelp] = useState(false),
    [checks, setChecks] = useState<ReviewChecks>({}),
    [unsavedSession, setUnsavedSession] = useState(false),
    [leaveSession, setLeaveSession] = useState(false),
    [candidate, setCandidate] = useState<ImportedHandoff | null>(null),
    [importAck, setImportAck] = useState(false),
    [includeExamples, setIncludeExamples] = useState(true);
  const pending = useRef<() => void>(() => {}),
    leavingWorkspace = useRef(false),
    importInput = useRef<HTMLInputElement>(null),
    module = modules.find((m) => m.id === moduleId) || modules[0],
    feature =
      module?.features.find((f) => f.id === featureId) || module?.features[0],
    all = modules.flatMap((m) =>
      m.features.map((f) => ({ module: m, feature: f })),
    ),
    record = rows.find((r) => r.id === selected && r.feature === feature?.id),
    featureRows = rows.filter((r) => r.feature === feature?.id),
    activeJourney = journeys.find((j) => j.id === journeyId),
    editable = role === "Operator" && screen === "ready";
  async function load() {
    setLoading(true);
    try {
      const c = await api("/v1/interface-catalog");
      setModules(c.modules);
      const initial = new URL(location.href).searchParams.get("ui_feature");
      const initialModule = c.modules.find((m: InterfaceModule) =>
        m.features.some((f) => f.id === initial),
      );
      if (initialModule) {
        setModule(initialModule.id);
        setFeature(initial!);
        setView("module");
      }
      setError("");
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
    if (!draft && !unsavedSession) return;
    const stop = registerNavigationGuard((next) => {
      pending.current = next;
      leavingWorkspace.current = true;
      if (draft) setDiscard(true);
      else setLeaveSession(true);
    });
    const before = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", before);
    return () => {
      stop();
      window.removeEventListener("beforeunload", before);
    };
  }, [Boolean(draft), unsavedSession]);
  function guarded(next: () => void) {
    if (draft) {
      leavingWorkspace.current = false;
      pending.current = next;
      setDiscard(true);
    } else next();
  }
  function openFeature(id: string) {
    const entry = all.find((x) => x.feature.id === id);
    if (!entry) return;
    guarded(() => {
      setModule(entry.module.id);
      setFeature(id);
      const url = new URL(location.href);
      url.searchParams.set("ui_feature", id);
      window.history.replaceState(null, "", url);
      setQ("");
      setView("module");
      setSelected("");
      setTab("Overview");
      setScreen("ready");
      setError("");
      setNotice("");
    });
  }
  function openModule(id: string) {
    setJourney("");
    const m = modules.find((x) => x.id === id);
    if (m) openFeature(m.features[0].id);
  }
  function openGlobal(id: string) {
    setJourney("");
    const f = all.find((x) => x.feature.id.endsWith("__" + id));
    if (f) openFeature(f.feature.id);
  }
  function create() {
    if (!feature) return;
    if (rows.length >= UI_RECORD_LIMIT) {
      setError(
        "This UI review session is limited to 300 example records. Export your handoff before starting another session.",
      );
      return;
    }
    setDraft(newUiRecord(feature, "UI-" + crypto.randomUUID()));
    setError("");
  }
  function save(e: React.FormEvent) {
    e.preventDefault();
    if (!draft || !feature || !editable) return;
    const issues = uiInputs(feature, draft);
    if (Object.keys(issues).length) {
      setError(Object.values(issues).join(" "));
      return;
    }
    setRows((prior) => [
      ...prior.filter((r) => r.id !== draft.id),
      { ...draft, version: draft.version + 1 },
    ]);
    setUnsavedSession(true);
    setSelected(draft.id);
    setDraft(null);
    setNotice(
      "Example saved in this UI session only. Export the handoff to retain it.",
    );
    setTab("Configuration");
  }
  function review(cmd: string) {
    if (!record) return;
    setPinned(structuredClone(record));
    setCommand(cmd);
    setNote("");
    setScopeCheck(false);
    setEffectCheck(false);
    setError("");
  }
  function confirm(e: React.FormEvent) {
    e.preventDefault();
    if (!pinned || !scopeCheck || !effectCheck) return;
    try {
      const current = rows.find((r) => r.id === pinned.id);
      if (!current) throw Error("Preview record is no longer available.");
      const next = previewTransition(
        current,
        command,
        role,
        pinned.version,
        note,
        screen,
      );
      setRows((prior) => prior.map((r) => (r.id === next.id ? next : r)));
      setPinned(null);
      setUnsavedSession(true);
      setCommand("");
      setNotice(
        "UI transition recorded. No backend command, external notification or business operation was executed.",
      );
      setTab("Activity");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const workspaceScope = {
    organization: String(me.user.org_id),
    user: String(me.user.id),
  };
  function exportHandoff() {
    try {
      const data = makeHandoff(
        modules,
        rows,
        reviewed,
        checks,
        workspaceScope,
        includeExamples,
      );
      download(data);
      if (includeExamples || !rows.length) setUnsavedSession(false);
      setNotice(
        includeExamples
          ? "UI handoff download started. It can be imported in this account/workspace to resume your review."
          : "Review metadata download started. Examples were excluded; export a full handoff to retain changed examples.",
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function chooseImport(file?: File) {
    if (!file) return;
    try {
      if (
        !file.name.toLowerCase().endsWith(".json") ||
        file.size < 1 ||
        file.size > HANDOFF_LIMIT
      )
        throw Error("Choose a JSON UI handoff of 1 byte to 8 MiB.");
      const imported = parseHandoff(await file.text(), modules, workspaceScope);
      setCandidate(imported);
      setImportAck(false);
      setError("");
    } catch (e) {
      setCandidate(null);
      setError((e as Error).message);
    }
  }
  function applyImport() {
    if (!candidate || !importAck) return;
    setRows(candidate.records);
    setReviewed(candidate.reviewed);
    setChecks(candidate.checks);
    setDraft(null);
    setSelected("");
    setPinned(null);
    setUnsavedSession(false);
    setNotice(
      candidate.legacy
        ? "Legacy UI examples restored. Review markers require the new four-part checklist before acceptance."
        : "UI review restored from your handoff. No backend records or permissions were changed.",
    );
    setCandidate(null);
    setView("coverage");
  }
  function toggleCriterion(id: string, checked: boolean) {
    if (!feature) return;
    setChecks((prior) => ({
      ...prior,
      [feature.id]: checked
        ? [...(prior[feature.id] || []).filter((x) => x !== id), id]
        : (prior[feature.id] || []).filter((x) => x !== id),
    }));
    if (!checked) setReviewed((prior) => prior.filter((x) => x !== feature.id));
    setUnsavedSession(true);
  }
  const issues = draft && feature ? uiInputs(feature, draft) : {};
  return (
    <section className="product-ui" aria-label="Product UI walkthrough">
      <div className="product-banner">
        <ShieldCheck size={20} />
        <div>
          <strong>UI FIRST · IMPLEMENTATION FOLLOWS IN PHASES</strong>
          <p>
            All examples, personas, environments and review decisions in this
            workspace are UI rehearsals. Existing implemented workspaces remain
            available separately.
          </p>
        </div>
        <button className="btn btn-outline" onClick={() => setHelp(true)}>
          <HelpCircle size={17} />
          How to use
        </button>
      </div>
      <header className="product-hero">
        <div>
          <small>THE COMPLETE PRODUCT JOURNEY</small>
          <h2>
            One control plane.
            <br />
            <span>Every step connected.</span>
          </h2>
          <p>
            Explore the agreed enterprise UI scope from onboarding to governed
            execution, knowledge, operations and release evidence.
          </p>
          <div className="product-inline">
            <button
              className="btn btn-primary"
              onClick={() => {
                setJourney("onboarding");
                setJourneyIndex(0);
                openFeature(journeys[0].steps[0]);
              }}
            >
              Start onboarding journey <ArrowRight size={17} />
            </button>
            <button className="btn btn-outline" onClick={exportHandoff}>
              <Download size={17} />
              Export UI handoff
            </button>
            <button
              className="btn btn-outline"
              disabled={!modules.length || Boolean(draft)}
              onClick={() => importInput.current?.click()}
            >
              <Upload size={17} />
              Import UI handoff
            </button>
            <input
              ref={importInput}
              className="product-file-input"
              type="file"
              accept=".json,application/json"
              aria-label="Import a UI handoff file"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                void chooseImport(file);
              }}
            />
            <label className="product-export-option">
              <input
                type="checkbox"
                checked={includeExamples}
                onChange={(e) => setIncludeExamples(e.target.checked)}
              />
              Include synthetic examples in export
            </label>
          </div>
        </div>
        <div className="product-summary">
          <span>
            <strong>{all.length}</strong>function screens
          </span>
          <span>
            <strong>{modules.length}</strong>enterprise areas
          </span>
          <span>
            <strong>{reviewed.length}</strong>reviewed in this session
          </span>
          <span>
            <strong>5</strong>implementation phases
          </span>
        </div>
      </header>
      <nav className="product-tabs" aria-label="Product walkthrough navigation">
        {[
          ["overview", "Workspace", Compass],
          ["journeys", "End-to-end journeys", ArrowRight],
          ["coverage", "UI coverage", ListChecks],
          ["phases", "Phase plan", Layers3],
          ["inbox", "Review inbox", Bell],
        ].map(([id, title, Icon]: any) => (
          <button
            key={id}
            className={view === id ? "selected" : ""}
            aria-current={view === id ? "page" : undefined}
            onClick={() =>
              guarded(() => {
                setView(id);
                setJourney("");
                setError("");
              })
            }
          >
            <Icon size={17} />
            {title}
            {id === "inbox" && rows.some((r) => r.status === "in_review") ? (
              <b>{rows.filter((r) => r.status === "in_review").length}</b>
            ) : null}
          </button>
        ))}
      </nav>
      <p className="product-session-status" role="status">
        {unsavedSession
          ? "This UI review has changes to export before leaving."
          : "No unexported UI review changes."}
      </p>
      {loading ? (
        <div className="product-empty" role="status">
          <RefreshCw />
          Loading the enterprise screen catalog…
        </div>
      ) : error && !modules.length ? (
        <div className="product-empty" role="alert">
          <h3>The screen catalog is unavailable</h3>
          <p>{error}</p>
          <button className="btn btn-outline" onClick={load}>
            Retry loading catalog
          </button>
        </div>
      ) : (
        <>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="product-notice" role="status">
              {notice}
            </p>
          )}
          {view === "overview" && (
            <>
              <div className="product-section">
                <div>
                  <small>YOUR NEXT STEP</small>
                  <h3>Start with a journey or open a workspace.</h3>
                </div>
                <button
                  className="btn btn-outline"
                  onClick={() => setView("journeys")}
                >
                  View all journeys <ArrowRight size={16} />
                </button>
              </div>
              <div className="product-shortcuts">
                {[
                  ["Organization setup", "organization_onboarding"],
                  ["Access & sessions", "session_and_device_management"],
                  ["Environment switching", "environment_creation_and_switch"],
                  ["Notifications", "notification_preferences"],
                  ["Help & ownership", "help_support_and_ownership"],
                  ["Branding & language", "branding_and_localization"],
                ].map(([title, id]) => (
                  <button key={id} onClick={() => openGlobal(id)}>
                    <span>{title}</span>
                    <ArrowRight size={17} />
                  </button>
                ))}
              </div>
              <div className="product-module-grid">
                {modules.map((m) => (
                  <button
                    className="product-module-card"
                    key={m.id}
                    onClick={() => openModule(m.id)}
                  >
                    <small>
                      {m.area} · Phase{" "}
                      {phases.indexOf(phaseFor(m.id) as any) + 1}
                    </small>
                    <h3>{m.title}</h3>
                    <p>{m.description}</p>
                    <footer>
                      <span>{m.features.length} function screens</span>
                      <ArrowRight size={18} />
                    </footer>
                  </button>
                ))}
              </div>
            </>
          )}
          {view === "journeys" && (
            <>
              <div className="product-section">
                <div>
                  <small>ACROSS THE PLATFORM</small>
                  <h3>Six connected journeys</h3>
                  <p>
                    Each step opens its function screen. Review the handoffs
                    before implementing the services.
                  </p>
                </div>
              </div>
              <div className="product-journeys">
                {journeys.map((j) => (
                  <article key={j.id}>
                    <small>{j.steps.length} connected screens</small>
                    <h3>{j.title}</h3>
                    <p>{j.description}</p>
                    <ol>
                      {j.steps.map((id, i) => {
                        const f = all.find((x) => x.feature.id === id);
                        return (
                          <li key={id}>
                            <button
                              onClick={() => {
                                setJourney(j.id);
                                setJourneyIndex(i);
                                openFeature(id);
                              }}
                            >
                              {f?.feature.title || id}
                              <ArrowRight size={15} />
                            </button>
                          </li>
                        );
                      })}
                    </ol>
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        setJourney(j.id);
                        setJourneyIndex(0);
                        openFeature(j.steps[0]);
                      }}
                    >
                      Start this journey <ArrowRight size={16} />
                    </button>
                  </article>
                ))}
              </div>
            </>
          )}
          {view === "coverage" && (
            <>
              <div className="product-section">
                <div>
                  <small>BOUNDED UI BASELINE</small>
                  <h3>
                    {all.length} screens. Nothing hidden from the agreed
                    inventory.
                  </h3>
                  <p>
                    A rendered screen is separate from human UI review,
                    implemented service behavior and production acceptance.
                  </p>
                </div>
              </div>
              <label className="product-search">
                <Search size={18} />
                <input
                  aria-label="Search all product screens"
                  placeholder="Search a function, workspace or capability…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </label>
              <div className="product-coverage">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Function screen</th>
                      <th scope="col">Workspace / phase</th>
                      <th scope="col">UI state coverage</th>
                      <th scope="col">Session review</th>
                      <th scope="col">Open</th>
                    </tr>
                  </thead>
                  <tbody>
                    {all
                      .filter((x) =>
                        (x.feature.title + " " + x.module.title)
                          .toLowerCase()
                          .includes(q.toLowerCase()),
                      )
                      .map(({ module: m, feature: f }) => (
                        <tr key={f.id}>
                          <td>
                            <strong>{f.title}</strong>
                            <small>
                              {f.priority} · {f.fields.length} configuration
                              controls
                            </small>
                          </td>
                          <td>
                            {m.title}
                            <small>{phaseFor(m.id).title}</small>
                          </td>
                          <td>
                            {screenStates.length} designed states
                            <br />
                            <small>
                              6 detail views · confirmation · evidence
                            </small>
                          </td>
                          <td>
                            <span
                              className={
                                "product-status " +
                                (reviewed.includes(f.id) ? "approved" : "draft")
                              }
                            >
                              {reviewed.includes(f.id)
                                ? "UI reviewed"
                                : "Needs UI review"}
                            </span>
                          </td>
                          <td>
                            <button
                              className="btn btn-outline"
                              aria-label={"Open " + f.title + " screen"}
                              onClick={() => openFeature(f.id)}
                            >
                              Open <ArrowRight size={15} />
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                {!all.some((x) =>
                  (x.feature.title + " " + x.module.title)
                    .toLowerCase()
                    .includes(q.toLowerCase()),
                ) && (
                  <p className="product-empty">
                    No matching function screens. Clear the search to restore
                    the full inventory.
                  </p>
                )}
              </div>
            </>
          )}
          {view === "phases" && (
            <>
              <div className="product-section">
                <div>
                  <small>AFTER THE UI REVIEW</small>
                  <h3>Implement in five controlled phases.</h3>
                  <p>
                    Each phase needs code, integrations and test evidence.
                    Checking a UI screen does not pass a release gate.
                  </p>
                </div>
              </div>
              <div className="product-phase-list">
                {phases.map((p) => {
                  const list = modules.filter((m) =>
                      (p.modules as readonly string[]).includes(m.id),
                    ),
                    total = list.reduce((a, m) => a + m.features.length, 0),
                    done = list.reduce(
                      (a, m) =>
                        a +
                        m.features.filter((f) => reviewed.includes(f.id))
                          .length,
                      0,
                    );
                  return (
                    <article key={p.id}>
                      <header>
                        <span className="product-phase-number">
                          {phases.indexOf(p) + 1}
                        </span>
                        <div>
                          <h3>{p.title.slice(4)}</h3>
                          <p>{p.deliverable}</p>
                        </div>
                        <span>
                          {done}/{total} UI reviews
                        </span>
                      </header>
                      <progress
                        value={done}
                        max={total || 1}
                        aria-label={p.title + " UI review progress"}
                      />
                      <div className="product-inline">
                        {list.map((m) => (
                          <button
                            className="btn btn-outline"
                            key={m.id}
                            onClick={() => openModule(m.id)}
                          >
                            {m.title} <ArrowRight size={15} />
                          </button>
                        ))}
                      </div>
                      <p>
                        <strong>Exit evidence:</strong> reviewed UI flows →
                        implemented APIs/workers → role and tenant tests →
                        staging checks → operator acceptance.
                      </p>
                    </article>
                  );
                })}
              </div>
            </>
          )}
          {view === "inbox" && (
            <>
              <div className="product-section">
                <div>
                  <small>IN THIS UI SESSION</small>
                  <h3>Review inbox and activity</h3>
                  <p>
                    These notifications are generated from your example
                    transitions. No email, push notification or approval request
                    is sent.
                  </p>
                </div>
                <button
                  className="btn btn-outline"
                  onClick={() => openGlobal("notification_preferences")}
                >
                  Notification preferences
                </button>
              </div>
              <div className="product-inbox">
                {rows.filter((r) =>
                  [
                    "in_review",
                    "outcome_unknown",
                    "changes_requested",
                  ].includes(r.status),
                ).length ? (
                  rows
                    .filter((r) =>
                      [
                        "in_review",
                        "outcome_unknown",
                        "changes_requested",
                      ].includes(r.status),
                    )
                    .map((r) => (
                      <button
                        key={r.id}
                        onClick={() => {
                          openFeature(r.feature);
                          setSelected(r.id);
                          setTab("Review");
                        }}
                      >
                        <Bell size={20} />
                        <div>
                          <strong>{r.name}</strong>
                          <small>
                            {pretty(r.status)} · version {r.version} · {r.owner}
                          </small>
                        </div>
                        <ArrowRight size={18} />
                      </button>
                    ))
                ) : (
                  <div className="product-empty">
                    <CheckCircle2 size={32} />
                    <h3>No review items in this session</h3>
                    <p>
                      Open a function, create an example and submit it for UI
                      review to see the connected inbox journey.
                    </p>
                    <button
                      className="btn btn-primary"
                      onClick={() => setView("overview")}
                    >
                      Open a workspace
                    </button>
                  </div>
                )}
              </div>
            </>
          )}
          {view === "module" && module && feature && (
            <>
              {activeJourney && (
                <div className="product-journey-bar">
                  <div>
                    <small>
                      CONNECTED JOURNEY · {journeyIndex + 1}/
                      {activeJourney.steps.length}
                    </small>
                    <strong>{activeJourney.title}</strong>
                  </div>
                  <div className="product-inline">
                    <button
                      className="btn btn-outline"
                      disabled={journeyIndex === 0}
                      onClick={() => {
                        setJourneyIndex((i) => i - 1);
                        openFeature(activeJourney.steps[journeyIndex - 1]);
                      }}
                    >
                      <ArrowLeft size={15} />
                      Previous step
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        if (journeyIndex + 1 < activeJourney.steps.length) {
                          setJourneyIndex((i) => i + 1);
                          openFeature(activeJourney.steps[journeyIndex + 1]);
                        } else
                          guarded(() => {
                            setView("journeys");
                            setJourney("");
                          });
                      }}
                    >
                      {journeyIndex + 1 === activeJourney.steps.length
                        ? "Finish walkthrough"
                        : "Next step"}
                      <ArrowRight size={15} />
                    </button>
                  </div>
                </div>
              )}
              <div className="product-workspace-head">
                <div>
                  <small>
                    {module.area} · {phaseFor(module.id).title}
                  </small>
                  <h3>{module.title}</h3>
                  <p>{module.description}</p>
                </div>
                <div className="product-controls">
                  <label>
                    Preview persona
                    <select
                      aria-label="Preview persona"
                      value={role}
                      onChange={(e) => setRole(e.target.value as ReviewRole)}
                    >
                      <option>Operator</option>
                      <option>Reviewer</option>
                      <option>Auditor</option>
                    </select>
                  </label>
                  <label>
                    Preview environment
                    <select
                      aria-label="Preview environment"
                      value={environment}
                      onChange={(e) => setEnvironment(e.target.value)}
                    >
                      <option>Development design</option>
                      <option>Staging design</option>
                      <option>Production design</option>
                    </select>
                  </label>
                  <label>
                    Screen state
                    <select
                      aria-label="Screen state"
                      value={screen}
                      onChange={(e) => setScreen(e.target.value as ScreenState)}
                    >
                      {screenStates.map((s) => (
                        <option value={s} key={s}>
                          {pretty(s)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
              <div className="product-function-layout">
                <aside aria-label="Workspace function screens">
                  <label className="product-search">
                    <Search size={16} />
                    <input
                      aria-label="Search workspace function screens"
                      placeholder="Find a screen…"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                    />
                  </label>
                  {module.features
                    .filter((f) =>
                      f.title.toLowerCase().includes(q.toLowerCase()),
                    )
                    .map((f, i) => (
                      <button
                        key={f.id}
                        className={f.id === feature.id ? "selected" : ""}
                        aria-current={f.id === feature.id ? "page" : undefined}
                        onClick={() => openFeature(f.id)}
                      >
                        <small>
                          {String(module.features.indexOf(f) + 1).padStart(
                            2,
                            "0",
                          )}{" "}
                          · {f.priority}
                        </small>
                        <strong>{f.title}</strong>
                        <span>
                          {reviewed.includes(f.id)
                            ? "UI reviewed"
                            : "Open for review"}
                        </span>
                      </button>
                    ))}
                  {!module.features.some((f) =>
                    f.title.toLowerCase().includes(q.toLowerCase()),
                  ) && <p>No matching screens.</p>}
                </aside>
                <article className="product-feature">
                  <header>
                    <div>
                      <small>FUNCTION WORKSPACE · {environment}</small>
                      <h3>{feature.title}</h3>
                      <p>{feature.summary}</p>
                    </div>
                    <span className="product-status draft">UI preview</span>
                  </header>
                  <div className="product-context">
                    <span>
                      <LockKeyhole size={15} />
                      {role} preview persona
                    </span>
                    <span>{feature.roles.join(" · ")}</span>
                  </div>
                  {feature.working_view && (
                    <div className="product-implemented">
                      <p>
                        {feature.implementation_note ||
                          "A bounded implemented workspace is available for this area."}
                      </p>
                      <button
                        className="btn btn-outline"
                        onClick={() => onNavigate(feature.working_view!)}
                      >
                        Open implemented workspace <ArrowRight size={15} />
                      </button>
                    </div>
                  )}
                  <div className="product-state" role="status">
                    <strong>{stateGuidance[screen].title}</strong>
                    <p>{stateGuidance[screen].body}</p>
                    {screen !== "ready" && (
                      <button
                        className="btn btn-outline"
                        onClick={() => {
                          if (screen === "permission_denied")
                            openGlobal("workspace_membership");
                          else if (screen === "validation_error") {
                            if (role !== "Operator") {
                              setNotice(
                                "Switch to the Operator preview persona to correct configuration.",
                              );
                              return;
                            }
                            if (rows.length >= UI_RECORD_LIMIT) {
                              setError(
                                "Export this UI session before creating another example.",
                              );
                              return;
                            }
                            const invalid = newUiRecord(
                              feature,
                              "UI-" + crypto.randomUUID(),
                            );
                            invalid.values[feature.fields[0].id] = "";
                            setDraft(invalid);
                            setScreen("ready");
                            setError(
                              "Complete the highlighted field before saving this example.",
                            );
                          } else if (screen === "timeout_unknown")
                            setTab("Review");
                          else setScreen("ready");
                        }}
                      >
                        {stateGuidance[screen].action}
                      </button>
                    )}
                  </div>
                  <nav
                    className="product-tabs product-detail-tabs"
                    aria-label="Function detail views"
                  >
                    {detailTabs.map((t) => (
                      <button
                        key={t}
                        aria-current={tab === t ? "page" : undefined}
                        className={tab === t ? "selected" : ""}
                        onClick={() => setTab(t)}
                      >
                        {t}
                      </button>
                    ))}
                  </nav>
                  {screen === "permission_denied" ? (
                    <div className="product-empty">
                      <LockKeyhole size={30} />
                      <h4>Restricted preview</h4>
                      <p>
                        Example record details are hidden in this state. Review
                        the required access below.
                      </p>
                      <ul>
                        {feature.roles.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                      <button
                        className="btn btn-outline"
                        onClick={() => openGlobal("workspace_membership")}
                      >
                        Open access request journey
                      </button>
                    </div>
                  ) : screen === "loading" ? (
                    <div
                      className="product-skeleton"
                      role="status"
                      aria-label="Loading function workspace"
                    >
                      <span />
                      <span />
                      <span />
                    </div>
                  ) : (
                    <>
                      {tab === "Overview" && (
                        <>
                          <div className="product-section">
                            <div>
                              <h4>Records and requests</h4>
                              <p>
                                {featureRows.length} synthetic examples ·
                                changes remain in this UI session.
                              </p>
                            </div>
                            <button
                              className="btn btn-primary"
                              disabled={!editable}
                              onClick={create}
                            >
                              <Plus size={16} />
                              Create example
                            </button>
                          </div>
                          {screen === "empty" || !featureRows.length ? (
                            <div className="product-empty">
                              <Layers3 size={32} />
                              <h4>Start this function journey</h4>
                              <p>
                                Create an example, configure its scope, submit
                                for review, switch persona and inspect the
                                resulting evidence.
                              </p>
                              <button
                                className="btn btn-outline"
                                disabled={!editable}
                                onClick={create}
                              >
                                Create first example
                              </button>
                            </div>
                          ) : (
                            <div className="product-records">
                              {featureRows.map((r) => (
                                <button
                                  key={r.id}
                                  className={
                                    r.id === selected ? "selected" : ""
                                  }
                                  onClick={() => {
                                    setSelected(r.id);
                                    setTab("Configuration");
                                  }}
                                >
                                  <div>
                                    <strong>{r.name}</strong>
                                    <small>
                                      {r.owner} · revision {r.version}
                                    </small>
                                  </div>
                                  <span
                                    className={"product-status " + r.status}
                                  >
                                    {pretty(r.status)}
                                  </span>
                                  <ArrowRight size={16} />
                                </button>
                              ))}
                            </div>
                          )}
                          <div className="product-steps">
                            <h4>The end-to-end handoff</h4>
                            <ol>
                              {feature.steps.map((s, i) => (
                                <li key={i}>
                                  <span>{i + 1}</span>
                                  {s}
                                </li>
                              ))}
                            </ol>
                          </div>
                        </>
                      )}
                      {tab === "Configuration" &&
                        (record ? (
                          <>
                            <div className="product-section">
                              <div>
                                <h4>{record.name}</h4>
                                <p>
                                  Revision {record.version} ·{" "}
                                  {pretty(record.status)}
                                </p>
                              </div>
                              <button
                                className="btn btn-outline"
                                disabled={
                                  !editable ||
                                  !["draft", "changes_requested"].includes(
                                    record.status,
                                  )
                                }
                                onClick={() => {
                                  setDraft(structuredClone(record));
                                  setError("");
                                }}
                              >
                                Edit example
                              </button>
                            </div>
                            <dl className="product-facts">
                              {feature.fields.map((f) => (
                                <div key={f.id}>
                                  <dt>{f.label}</dt>
                                  <dd>{record.values[f.id]}</dd>
                                </div>
                              ))}
                            </dl>
                            <div className="product-inline">
                              <button
                                className="btn btn-primary"
                                disabled={
                                  role !== "Operator" ||
                                  !["draft", "changes_requested"].includes(
                                    record.status,
                                  ) ||
                                  !["ready", "timeout_unknown"].includes(screen)
                                }
                                onClick={() => review("submit")}
                              >
                                Review submission <ArrowRight size={16} />
                              </button>
                              <button
                                className="btn btn-outline"
                                onClick={() => setTab("Review")}
                              >
                                Open review details
                              </button>
                            </div>
                          </>
                        ) : (
                          <div className="product-empty">
                            <h4>Select or create an example</h4>
                            <p>
                              Configuration values are pinned to a preview
                              revision before review.
                            </p>
                            <button
                              className="btn btn-outline"
                              onClick={() => setTab("Overview")}
                            >
                              Open records
                            </button>
                          </div>
                        ))}
                      {tab === "Review" &&
                        (record ? (
                          <>
                            <h4>Review {record.name}</h4>
                            <p>
                              <span
                                className={"product-status " + record.status}
                              >
                                {pretty(record.status)}
                              </span>{" "}
                              · pinned values stay attached to revision{" "}
                              {record.version}.
                            </p>
                            <dl className="product-facts">
                              {feature.fields.map((f) => (
                                <div key={f.id}>
                                  <dt>{f.label}</dt>
                                  <dd>{record.values[f.id]}</dd>
                                </div>
                              ))}
                            </dl>
                            <p>
                              Operator submits. Reviewer decides. Auditor
                              inspects evidence. This persona selector changes
                              the rehearsal only; actual user permissions are
                              unchanged.
                            </p>
                            <div className="product-inline">
                              {record.status === "in_review" ? (
                                <>
                                  <button
                                    className="btn btn-primary"
                                    disabled={
                                      role !== "Reviewer" || screen !== "ready"
                                    }
                                    onClick={() => review("approve")}
                                  >
                                    Approve UI example
                                  </button>
                                  <button
                                    className="btn btn-outline"
                                    disabled={
                                      role !== "Reviewer" || screen !== "ready"
                                    }
                                    onClick={() => review("rework")}
                                  >
                                    Return for rework
                                  </button>
                                  <button
                                    className="btn btn-outline"
                                    disabled={
                                      role !== "Reviewer" || screen !== "ready"
                                    }
                                    onClick={() => review("reject")}
                                  >
                                    Reject example
                                  </button>
                                </>
                              ) : record.status === "outcome_unknown" ? (
                                <button
                                  className="btn btn-outline"
                                  disabled={
                                    role === "Auditor" || screen !== "ready"
                                  }
                                  onClick={() => review("reconcile")}
                                >
                                  Reconcile existing preview request
                                </button>
                              ) : (
                                <button
                                  className="btn btn-outline"
                                  onClick={() => setTab("Configuration")}
                                >
                                  Open current configuration
                                </button>
                              )}
                            </div>
                            {record.status === "outcome_unknown" && (
                              <p className="product-warning">
                                No blind retry is offered. Switch the screen
                                state to ready, inspect the prior request and
                                rehearse reconciliation.
                              </p>
                            )}
                            {role !== "Reviewer" &&
                              record.status === "in_review" && (
                                <p className="product-warning">
                                  Switch Preview persona to Reviewer to rehearse
                                  a decision.
                                </p>
                              )}
                          </>
                        ) : (
                          <div className="product-empty">
                            <h4>No selected request</h4>
                            <p>
                              Select a preview record before opening its review.
                            </p>
                            <button
                              className="btn btn-outline"
                              onClick={() => setTab("Overview")}
                            >
                              Open records
                            </button>
                          </div>
                        ))}
                      {tab === "Activity" && (
                        <>
                          <h4>Outcome and evidence timeline</h4>
                          {record && (
                            <p>
                              <span
                                className={"product-status " + record.status}
                              >
                                {pretty(record.status)}
                              </span>{" "}
                              · revision {record.version}
                            </p>
                          )}
                          {record?.events.length ? (
                            <ol className="product-timeline">
                              {record.events.map((e, i) => (
                                <li key={i}>
                                  <Activity size={18} />
                                  <div>
                                    <strong>
                                      {pretty(e.label)} · UI event {i + 1}
                                    </strong>
                                    <small>
                                      {new Date(e.at).toLocaleString()}
                                    </small>
                                    <p>{e.note}</p>
                                  </div>
                                </li>
                              ))}
                            </ol>
                          ) : (
                            <p className="product-empty">
                              No transitions have been recorded for the selected
                              example.
                            </p>
                          )}
                          <p className="product-warning">
                            This is local UI review evidence, not an immutable
                            server audit log or deployment acceptance record.
                          </p>
                        </>
                      )}
                      {tab === "Access" && (
                        <>
                          <h4>Access and responsibility</h4>
                          <table className="product-access-table">
                            <thead>
                              <tr>
                                <th scope="col">Preview persona</th>
                                <th scope="col">Designed responsibility</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                <td>Operator</td>
                                <td>
                                  Create/configure an example and submit it for
                                  review.
                                </td>
                              </tr>
                              <tr>
                                <td>Reviewer</td>
                                <td>
                                  Inspect submitted values; approve, reject or
                                  return for rework.
                                </td>
                              </tr>
                              <tr>
                                <td>Auditor</td>
                                <td>
                                  Inspect configuration and UI event evidence
                                  without mutations.
                                </td>
                              </tr>
                            </tbody>
                          </table>
                          <h4>Intended enterprise roles</h4>
                          <p>{feature.roles.join(" · ")}</p>
                          <h4>Required boundaries</h4>
                          <ul>
                            <li>
                              Authenticated organization and environment
                              membership.
                            </li>
                            <li>Server-side role and object authorization.</li>
                            <li>
                              Independent reviewer rules where required by the
                              policy.
                            </li>
                            <li>
                              Redaction, export scope and audit correlation.
                            </li>
                          </ul>
                          <button
                            className="btn btn-outline"
                            onClick={() =>
                              openGlobal("role_and_permission_matrix")
                            }
                          >
                            Open role matrix screen
                          </button>
                        </>
                      )}
                      {tab === "API handoff" && (
                        <>
                          <h4>Implementation contract</h4>
                          <p>
                            This planned service route is design metadata. This
                            workspace does not invoke it.
                          </p>
                          <code className="product-code">
                            POST {feature.planned_path}
                          </code>
                          <dl className="product-facts">
                            <div>
                              <dt>Data entities</dt>
                              <dd>{feature.entities.join(" · ")}</dd>
                            </div>
                            <div>
                              <dt>Dependencies</dt>
                              <dd>{feature.dependencies.join(" · ")}</dd>
                            </div>
                          </dl>
                          <h4>Acceptance criteria</h4>
                          <ul>
                            {feature.acceptance.map((a) => (
                              <li key={a}>{a}</li>
                            ))}
                          </ul>
                          <button
                            className="btn btn-outline"
                            onClick={() => onDesign(module.id, feature.id)}
                          >
                            Open detailed design contract{" "}
                            <ArrowRight size={15} />
                          </button>
                        </>
                      )}
                    </>
                  )}
                  <footer className="product-review-footer">
                    <fieldset>
                      <legend>Manual UI review checklist</legend>
                      {reviewCriteria.map((c) => (
                        <label key={c.id}>
                          <input
                            type="checkbox"
                            checked={Boolean(
                              checks[feature.id]?.includes(c.id),
                            )}
                            onChange={(e) =>
                              toggleCriterion(c.id, e.target.checked)
                            }
                          />
                          {c.label}
                        </label>
                      ))}
                    </fieldset>
                    <label>
                      <input
                        type="checkbox"
                        disabled={!reviewComplete(checks, feature.id)}
                        checked={reviewed.includes(feature.id)}
                        onChange={(e) => {
                          setReviewed((prior) =>
                            e.target.checked
                              ? [
                                  ...prior.filter((x) => x !== feature.id),
                                  feature.id,
                                ]
                              : prior.filter((x) => x !== feature.id),
                          );
                          setUnsavedSession(true);
                        }}
                      />
                      Mark this function UI reviewed.
                    </label>
                    <p>
                      Complete all four checklist criteria first. This is your
                      UI attestation; it does not activate a backend or certify
                      production readiness.
                    </p>
                  </footer>
                </article>
              </div>
            </>
          )}
        </>
      )}
      {draft && feature && (
        <Modal
          title={"Configure " + feature.title}
          onClose={() => {
            leavingWorkspace.current = false;
            pending.current = () => setDraft(null);
            setDiscard(true);
          }}
        >
          <form onSubmit={save} className="product-form">
            <p className="product-warning">
              Use synthetic data and secret references only. This example stays
              in memory until you leave this workspace or export the handoff.
            </p>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <label>
              Example name
              <input
                required
                maxLength={120}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </label>
            <label>
              Responsible owner
              <input
                required
                maxLength={120}
                value={draft.owner}
                onChange={(e) => setDraft({ ...draft, owner: e.target.value })}
              />
            </label>
            {feature.fields.map((f) => (
              <label key={f.id}>
                {f.label}
                {f.type === "select" ? (
                  <select
                    aria-label={f.label}
                    aria-invalid={Boolean(issues[f.id])}
                    aria-describedby={"ui-field-" + feature.id + "-" + f.id}
                    value={draft.values[f.id]}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        values: { ...draft.values, [f.id]: e.target.value },
                      })
                    }
                  >
                    {f.options?.map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                ) : f.type === "json" ? (
                  <textarea
                    required
                    rows={5}
                    maxLength={2000}
                    aria-label={f.label}
                    aria-invalid={Boolean(issues[f.id])}
                    aria-describedby={"ui-field-" + feature.id + "-" + f.id}
                    value={draft.values[f.id]}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        values: { ...draft.values, [f.id]: e.target.value },
                      })
                    }
                  />
                ) : (
                  <input
                    required
                    type={
                      f.type === "number"
                        ? "number"
                        : f.type === "date"
                          ? "date"
                          : f.type === "email"
                            ? "email"
                            : "text"
                    }
                    min={f.min}
                    max={f.max}
                    step={f.type === "number" ? "any" : undefined}
                    maxLength={2000}
                    aria-label={f.label}
                    aria-invalid={Boolean(issues[f.id])}
                    aria-describedby={"ui-field-" + feature.id + "-" + f.id}
                    value={draft.values[f.id]}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        values: { ...draft.values, [f.id]: e.target.value },
                      })
                    }
                  />
                )}
                <small
                  id={"ui-field-" + feature.id + "-" + f.id}
                  className={issues[f.id] ? "product-field-error" : ""}
                >
                  {issues[f.id] ||
                    (f.type === "reference"
                      ? "Use env:NAME or secret://path. Never enter an actual credential."
                      : "Required · scoped to this example")}
                </small>
              </label>
            ))}
            <button
              className="btn btn-primary"
              disabled={!editable}
              type="submit"
            >
              Save UI example <CheckCircle2 size={17} />
            </button>
          </form>
        </Modal>
      )}
      {pinned && (
        <Modal
          title={"Confirm " + pretty(command) + " · UI example"}
          onClose={() => setPinned(null)}
        >
          <form className="product-form" onSubmit={confirm}>
            <p>
              <strong>{pinned.name}</strong> · revision {pinned.version} ·{" "}
              {role} preview
            </p>
            <p>
              This confirmation records a UI-only transition. It sends no
              backend command and changes no real permissions or customer data.
            </p>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <label className="product-check">
              <input
                type="checkbox"
                checked={scopeCheck}
                onChange={(e) => setScopeCheck(e.target.checked)}
              />
              I reviewed the example scope, values and environment.
            </label>
            <label className="product-check">
              <input
                type="checkbox"
                checked={effectCheck}
                onChange={(e) => setEffectCheck(e.target.checked)}
              />
              I understand the proposed state and its recovery behavior.
            </label>
            <label>
              Review note
              <textarea
                required
                minLength={5}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            <button
              className="btn btn-primary"
              disabled={!scopeCheck || !effectCheck || note.trim().length < 5}
            >
              Confirm UI {pretty(command)}
            </button>
          </form>
        </Modal>
      )}
      {discard && (
        <Modal
          title="Discard unsaved UI example?"
          onClose={() => setDiscard(false)}
        >
          <p>
            The unsaved example will be removed. Previously saved examples
            remain in this UI session.
          </p>
          <div className="product-inline">
            <button
              className="btn btn-outline"
              onClick={() => setDiscard(false)}
            >
              Keep editing
            </button>
            <button
              className="btn btn-primary"
              onClick={() => {
                setDraft(null);
                setDiscard(false);
                if (leavingWorkspace.current && unsavedSession)
                  setLeaveSession(true);
                else pending.current();
              }}
            >
              Discard example and continue
            </button>
          </div>
        </Modal>
      )}
      {leaveSession && (
        <Modal
          title="Export your UI review before leaving?"
          onClose={() => setLeaveSession(false)}
        >
          <p>
            Your local examples and review checklists have unexported changes.
            Leaving resets this UI session. Server project records are
            unaffected.
          </p>
          <div className="product-inline">
            <button
              className="btn btn-primary"
              onClick={() => {
                setLeaveSession(false);
                exportHandoff();
              }}
            >
              Stay and export handoff
            </button>
            <button
              className="btn btn-outline"
              onClick={() => setLeaveSession(false)}
            >
              Keep reviewing
            </button>
            <button
              className="btn btn-outline"
              onClick={() => {
                setUnsavedSession(false);
                setLeaveSession(false);
                pending.current();
              }}
            >
              Leave without exporting
            </button>
          </div>
        </Modal>
      )}
      {candidate && (
        <Modal
          title="Restore this UI handoff?"
          onClose={() => setCandidate(null)}
        >
          <p>
            This replaces {rows.length} current local examples and{" "}
            {reviewed.length} review markers with {candidate.records.length}{" "}
            imported examples and {candidate.reviewed.length} reviewed
            functions. It changes no server accounts, permissions, services or
            production acceptance gates.
          </p>
          {unsavedSession && (
            <p className="product-warning">
              Export the current UI review first if you want to keep its
              changes.
            </p>
          )}
          {candidate.legacy && (
            <p className="product-warning">
              Legacy 0.14 exports have no verified account scope or review
              checklist. Confirm the examples are yours; review markers will be
              cleared.
            </p>
          )}
          <label className="product-check">
            <input
              type="checkbox"
              checked={importAck}
              onChange={(e) => setImportAck(e.target.checked)}
            />
            I reviewed the file and want to replace this local UI session.
          </label>
          <button
            className="btn btn-primary"
            disabled={!importAck}
            onClick={applyImport}
          >
            Restore UI review
          </button>
        </Modal>
      )}
      {help && (
        <Modal
          title="Review the complete UI before implementation"
          onClose={() => setHelp(false)}
        >
          <ol className="product-help">
            <li>
              Choose an enterprise workspace or one of the six connected
              journeys.
            </li>
            <li>
              Open a function, create a synthetic example, then review
              configuration and access.
            </li>
            <li>
              Submit as Operator, switch the preview persona to Reviewer, and
              approve, reject or return for rework.
            </li>
            <li>
              Inspect activity and the planned API handoff. Rehearse all eight
              screen states, including uncertain outcomes.
            </li>
            <li>
              Mark the screen reviewed and export the handoff. Saved examples
              and review checks remain local. Import the exported handoff in the
              same account/workspace to resume later.
            </li>
            <li>
              Use the five-phase board to implement services and gather
              staging/deployment evidence afterwards.
            </li>
          </ol>
          <p>
            All {all.length} functions in the agreed {modules.length}-area
            catalog are addressable here. This is a bounded UI baseline;
            additional business requirements can extend it. UI review is not
            WCAG certification or production acceptance.
          </p>
        </Modal>
      )}
    </section>
  );
}
