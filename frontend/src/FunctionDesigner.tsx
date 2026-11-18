import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  Code2,
  Download,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import type { InterfaceDraft, InterfaceModule } from "./interfaceDesign";
import {
  checkKeys,
  defaultFunctionPlan,
  functionPreview,
  validateFunctionPlan,
  type FunctionPlan,
} from "./functionPlans";
import "./functions.css";
function exportJson(name: string, data: unknown) {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = u;
  a.download = name + ".json";
  a.click();
  URL.revokeObjectURL(u);
}
function ActionDialog({
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
          <small>FUNCTION SCREEN REVIEW</small>
          <h2>{title}</h2>
        </div>
        <button
          className="icon-btn"
          aria-label="Close function action"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </header>
      <div className="ops-dialog-body">{children}</div>
    </dialog>
  );
}
export function FunctionDesigner({
  module,
  draft,
  disabled,
  onChange,
  onNavigate,
}: {
  module: InterfaceModule;
  draft: InterfaceDraft;
  disabled: boolean;
  onChange: (plans: FunctionPlan[]) => void;
  onNavigate: (page: string) => void;
}) {
  const [selected, setSelected] = useState(() => {
      const initial = new URL(location.href).searchParams.get("feature");
      return module.features.some((f) => f.id === initial)
        ? initial!
        : module.features[0].id;
    }),
    [search, setSearch] = useState(""),
    [state, setState] = useState("ready"),
    [tab, setTab] = useState("screen"),
    [command, setCommand] = useState(""),
    [note, setNote] = useState(""),
    [trace, setTrace] = useState<ReturnType<typeof functionPreview> | null>(
      null,
    ),
    [notice, setNotice] = useState("");
  const feature =
      module.features.find((f) => f.id === selected) || module.features[0],
    plans = draft.config.function_plans || [],
    saved = plans.find((p) => p.feature_id === feature.id),
    plan = saved || defaultFunctionPlan(feature),
    errors = validateFunctionPlan(feature, plan),
    filtered = module.features.filter((f) =>
      (f.title + " " + f.summary + " " + f.fields.map((x) => x.label).join(" "))
        .toLowerCase()
        .includes(search.toLowerCase()),
    );
  function update(next: FunctionPlan) {
    if (disabled) return;
    onChange(
      saved
        ? plans.map((p) => (p.feature_id === feature.id ? next : p))
        : [...plans, next],
    );
    setNotice(
      "Function design updated in this interface draft. Save revision to retain it.",
    );
    setTrace(null);
  }
  function choose(id: string) {
    setSelected(id);
    setTrace(null);
    setState("ready");
    setNotice("");
    const url = new URL(location.href);
    url.searchParams.set("feature", id);
    window.history.replaceState(null, "", url);
  }
  function commandReview(e: React.FormEvent) {
    e.preventDefault();
    if (Object.keys(errors).length || disabled) return;
    setTrace(functionPreview(feature, state, command, note));
    setCommand("");
    setTab("screen");
  }
  const contract = {
    status: "planned_contract_not_registered",
    method: "POST",
    path: feature.planned_path,
    expected_plan_version: draft.version || 1,
    request: {
      feature_id: feature.id,
      environment: plan.values.environment,
      configuration: plan.values,
      reason: "Reviewed implementation request",
    },
    required_controls: [
      "Authenticated tenant and role scope",
      "CSRF and idempotency where applicable",
      "Server-side input validation",
      "Audit correlation and outcome reconciliation",
    ],
    success_states: ["accepted", "completed", "requires_review"],
    error_states: feature.states.filter(
      (x) => !["ready", "empty", "loading"].includes(x),
    ),
    runtime_activated: false,
  };
  return (
    <section
      className="function-designer ops-console"
      aria-label="Detailed function design"
    >
      <div className="ops-heading">
        <div>
          <small>LONG-TERM PLATFORM FUNCTIONS</small>
          <h3>{module.title} · function screens</h3>
          <p>
            Each remaining capability has a configurable UI design, review
            journey and implementation contract. Runtime acceptance is separate.
          </p>
        </div>
        <button
          className="btn btn-outline"
          onClick={() =>
            exportJson(module.id + "-function-scope", {
              module: module.id,
              definitions: module.features,
              plans,
              runtime_activated: false,
            })
          }
        >
          <Download size={16} /> Export module scope
        </button>
      </div>
      {feature.working_view&&<div className="ops-alert"><p>{feature.implementation_note}</p><button className="btn btn-primary" onClick={()=>onNavigate(feature.working_view!)}>Open implemented workspace <ArrowRight size={16}/></button></div>}
      <div className="function-layout">
        <aside className="function-list" aria-label="Module function list">
          <label className="ops-search">
            <Search size={16} />
            <input
              aria-label="Search module functions"
              placeholder="Find a function…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <span>
            {filtered.length} of {module.features.length} functions
          </span>
          <nav>
            {filtered.map((f, i) => (
              <button
                key={f.id}
                aria-current={f.id === feature.id ? "true" : undefined}
                onClick={() => choose(f.id)}
              >
                <small>
                  {String(module.features.indexOf(f) + 1).padStart(2, "0")} ·{" "}
                  {f.priority}
                </small>
                <strong>{f.title}</strong>
                <span>
                  {plans
                    .find((p) => p.feature_id === f.id)
                    ?.phase.replaceAll("_", " ") || "Planned UI"}
                </span>
              </button>
            ))}
          </nav>
          {!filtered.length && (
            <p role="status">No function matches. Clear your search.</p>
          )}
        </aside>
        <div className="function-detail">
          <header className="function-title">
            <div>
              <small>{feature.priority.toUpperCase()} / FUNCTION DESIGN</small>
              <h4>{feature.title}</h4>
              <p>{feature.summary}</p>
            </div>
            <span className="ops-badge">
              <ShieldCheck size={14} /> Runtime inactive
            </span>
          </header>
          <div className="function-meta">
            <span>{feature.fields.length} screen fields</span>
            <span>{feature.actions.length} review actions</span>
            <span>{feature.states.length} screen states</span>
            <span>{saved ? "Draft configured" : "Default design"}</span>
          </div>
          <div
            className="function-subnav"
            role="group"
            aria-label="Function design views"
          >
            {[
              ["screen", "Screen & states"],
              ["journey", "Journey & roles"],
              ["contract", "API & data"],
              ["acceptance", "UI review"],
            ].map(([key, label]) => (
              <button
                className={tab === key ? "active" : ""}
                aria-pressed={tab === key}
                key={key}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          {notice && (
            <p className="ops-alert success" role="status">
              {notice}
            </p>
          )}
          {disabled && (
            <p className="ops-permission">
              Read-only: your role, archive state or an active save prevents
              design changes.
            </p>
          )}
          <div className="function-content">
            {tab === "screen" && (
              <>
                <div className="function-screen-tools">
                  <label>
                    Screen state to review
                    <select
                      value={state}
                      onChange={(e) => {
                        setState(e.target.value);
                        setTrace(null);
                      }}
                    >
                      {feature.states.map((s) => (
                        <option key={s} value={s}>
                          {s.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="btn btn-outline"
                    onClick={() =>
                      exportJson(feature.id + "-screen", {
                        feature,
                        plan,
                        trace,
                        contract,
                      })
                    }
                  >
                    <Download size={15} /> Export screen
                  </button>
                </div>
                {["empty", "loading"].includes(state) ? (
                  <div className="ops-empty" role="status">
                    <h5>
                      {state === "empty"
                        ? "No records available yet"
                        : "Loading this capability"}
                    </h5>
                    <p>
                      {state === "empty"
                        ? "The future service will return scoped records here. Review the configuration and the first-use action."
                        : "The future service request is pending. Keep existing data and show progress without submitting another action."}
                    </p>
                    <button
                      className="btn btn-outline"
                      onClick={() => setState("ready")}
                    >
                      {state === "empty"
                        ? "Review first-use form"
                        : "Return to ready view"}
                    </button>
                  </div>
                ) : state !== "ready" ? (
                  <div className="ops-alert error" role="alert">
                    <strong>{state.replaceAll("_", " ")}</strong>
                    <p>
                      {
                        (
                          {
                            permission_denied:
                              "Access is unavailable for this role. Preserve the draft and explain the required permission.",
                            validation_error:
                              "Highlight invalid fields and provide an actionable correction.",
                            dependency_unavailable:
                              "The dependency did not respond. Preserve inputs and offer an explicit retry.",
                            timeout_unknown:
                              "The outcome is uncertain. Inspect the existing request before deciding whether another submission is safe.",
                            stale_revision:
                              "Another editor changed this record. Reload and compare revisions before applying changes.",
                          } as Record<string, string>
                        )[state]
                      }
                    </p>
                    <button
                      className="btn btn-outline"
                      onClick={() => setState("ready")}
                    >
                      Return to configuration
                    </button>
                  </div>
                ) : null}
                <div className="function-fields">
                  {feature.fields.map((f) => (
                    <label key={f.id}>
                      {f.label}
                      {f.type === "select" ? (
                        <select
                          disabled={disabled}
                          aria-label={f.label}
                          aria-describedby={feature.id+"-"+f.id+"-help"}
                          value={plan.values[f.id]}
                          onChange={(e) =>
                            update({
                              ...plan,
                              values: {
                                ...plan.values,
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
                          disabled={disabled}
                          aria-label={f.label}
                          aria-describedby={feature.id+"-"+f.id+"-help"}
                          rows={6}
                          value={plan.values[f.id]}
                          maxLength={2000}
                          onChange={(e) =>
                            update({
                              ...plan,
                              values: {
                                ...plan.values,
                                [f.id]: e.target.value,
                              },
                            })
                          }
                        />
                      ) : (
                        <input
                          disabled={disabled}
                          aria-label={f.label}
                          aria-describedby={feature.id+"-"+f.id+"-help"}
                          type={
                            ["number", "url", "date"].includes(f.type)
                              ? f.type
                              : "text"
                          }
                          min={f.min}
                          max={f.max}
                          step={f.type === "number" ? "any" : undefined}
                          maxLength={2000}
                          value={plan.values[f.id]}
                          onChange={(e) =>
                            update({
                              ...plan,
                              values: {
                                ...plan.values,
                                [f.id]: e.target.value,
                              },
                            })
                          }
                        />
                      )}
                      <small id={feature.id+"-"+f.id+"-help"} className={errors[f.id] ? "function-error" : ""}>
                        {errors[f.id] ||
                          (f.type === "reference"
                            ? "Reference only: never enter a secret value."
                            : "Planning metadata; does not modify a runtime service.")}
                      </small>
                    </label>
                  ))}
                </div>
                <div className="function-actions">
                  {feature.actions.map((a) => (
                    <button
                      key={a}
                      disabled={
                        disabled ||
                        Object.keys(errors).length > 0 ||
                        ["empty", "loading"].includes(state)
                      }
                      className="btn btn-outline"
                      onClick={() => {
                        setCommand(a);
                        setNote("");
                      }}
                    >
                      {a}
                      <ArrowRight size={15} />
                    </button>
                  ))}
                </div>
                {trace && (
                  <section
                    className="function-trace"
                    aria-label="Function review result"
                  >
                    <h5>UI review result</h5>
                    <p>{trace.boundary}</p>
                    <span className="ops-badge">
                      Provider calls: 0 · Business effects: 0
                    </span>
                    <ol>
                      {trace.steps.map((s) => (
                        <li key={s.label}>
                          <strong>{s.label}</strong>
                          <span>{s.state.replaceAll("_", " ")}</span>
                        </li>
                      ))}
                    </ol>
                    <p>{trace.note}</p>
                  </section>
                )}
              </>
            )}
            {tab === "journey" && (
              <>
                <h5>Complete user journey</h5>
                <ol className="function-journey">
                  {feature.steps.map((s, i) => (
                    <li key={s}>
                      <span>{i + 1}</span>
                      <div>
                        <strong>{s}</strong>
                        <p>
                          {
                            [
                              "Enter the feature-specific scope and environment.",
                              "Validate required values and bounded inputs.",
                              "Explain the intended permission and tenant boundary.",
                              "Show the exact proposed action and require a review note.",
                              "Show success, denial, timeout or stale-revision feedback.",
                              "Link the result to a versioned plan and evidence requirements.",
                            ][i]
                          }
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
                <h5>Intended operational roles</h5>
                <div className="function-pills">
                  {feature.roles.map((role) => (
                    <span key={role}>{role}</span>
                  ))}
                </div>
                <p>
                  These are design personas. Current editing permission is
                  enforced by the existing authenticated control-plane role.
                </p>
                <h5>Failure and recovery coverage</h5>
                <div className="function-pills">
                  {feature.states.map((s) => (
                    <span key={s}>{s.replaceAll("_", " ")}</span>
                  ))}
                </div>
              </>
            )}
            {tab === "contract" && (
              <>
                <h5>
                  <Code2 size={17} /> Planned API contract
                </h5>
                <p>
                  This endpoint is a design contract, not an active service
                  route. Review authorization, payload validation, idempotency
                  and evidence before implementing it.
                </p>
                <pre>{JSON.stringify(contract, null, 2)}</pre>
                <button
                  className="btn btn-outline"
                  onClick={() => exportJson(feature.id + "-contract", contract)}
                >
                  Export contract
                </button>
                <h5>Data and evidence objects</h5>
                <div className="function-pills">
                  {feature.entities.map((x) => (
                    <span key={x}>{x}</span>
                  ))}
                </div>
                <h5>Implementation dependencies</h5>
                <div className="function-pills">
                  {feature.dependencies.map((x) => (
                    <span key={x}>{x.replaceAll("_", " ")}</span>
                  ))}
                </div>
                <p>
                  Required evidence: successful sandbox operation, denied-role
                  and cross-tenant tests, dependency failure handling, audit
                  correlation, recovery and deployment-specific review.
                </p>
              </>
            )}
            {tab === "acceptance" && (
              <>
                <h5>Responsible owner & planning phase</h5>
                <div className="function-fields">
                  <label>
                    Function owner
                    <input
                      disabled={disabled}
                      maxLength={120}
                      value={plan.owner}
                      onChange={(e) =>
                        update({ ...plan, owner: e.target.value })
                      }
                    />
                    {errors.owner && (
                      <small className="function-error">{errors.owner}</small>
                    )}
                  </label>
                  <label>
                    Function planning phase
                    <select
                      disabled={disabled}
                      value={plan.phase}
                      onChange={(e) =>
                        update({
                          ...plan,
                          phase: e.target.value as FunctionPlan["phase"],
                        })
                      }
                    >
                      <option value="planned">UI planned</option>
                      <option value="ui_reviewed">UI reviewed</option>
                      <option value="backend_in_progress">
                        Backend implementation in progress
                      </option>
                      <option value="staging_review">
                        Staging review planned
                      </option>
                    </select>
                    {errors.phase && (
                      <small className="function-error">{errors.phase}</small>
                    )}
                  </label>
                </div>
                <h5>Manual UI review checks</h5>
                <div className="function-checks">
                  {feature.acceptance.map((label, i) => (
                    <label key={checkKeys[i]}>
                      <input
                        disabled={disabled}
                        type="checkbox"
                        checked={!!plan.checks[checkKeys[i]]}
                        onChange={(e) =>
                          update({
                            ...plan,
                            checks: {
                              ...plan.checks,
                              [checkKeys[i]]: e.target.checked,
                            },
                          })
                        }
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
                <label>
                  Implementation notes
                  <textarea
                    disabled={disabled}
                    rows={5}
                    maxLength={2000}
                    value={plan.notes}
                    onChange={(e) => update({ ...plan, notes: e.target.value })}
                    placeholder="Record the design decision, dependencies and evidence needed…"
                  />
                </label>
                <p>
                  UI review checks never mark a runtime service implemented or
                  production-approved. Save revision retains this function plan
                  alongside the module configuration.
                </p>
                <button
                  className="btn btn-outline"
                  disabled={disabled}
                  onClick={() => {
                    onChange(plans.filter((p) => p.feature_id !== feature.id));
                    setNotice(
                      "Function plan reset to its default UI design. Previous saved revisions remain in History.",
                    );
                  }}
                >
                  Reset function draft
                </button>
              </>
            )}
          </div>
        </div>
      </div>
      {command && (
        <ActionDialog
          title={command + " · " + feature.title}
          onClose={() => setCommand("")}
        >
          <form onSubmit={commandReview}>
            <p>
              Review the <strong>{state.replaceAll("_", " ")}</strong> scenario
              for this function. This confirmation generates a UI trace only.
            </p>
            <label>
              Function action note
              <textarea
                required
                rows={3}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Describe the reviewed scope and expected result…"
              />
            </label>
            <footer>
              <button
                className="btn btn-outline"
                type="button"
                onClick={() => setCommand("")}
              >
                Cancel review
              </button>
              <button
                className="btn btn-primary"
                disabled={disabled || Object.keys(errors).length > 0}
              >
                Generate UI review
              </button>
            </footer>
          </form>
        </ActionDialog>
      )}
    </section>
  );
}
