import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Boxes,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Cloud,
  Code2,
  Copy,
  Database,
  Download,
  FileText,
  FlaskConical,
  GitBranch,
  History,
  Layers3,
  LockKeyhole,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  ShieldX,
  Sparkles,
  Trash2,
  Upload,
  Wallet,
  Waypoints,
  X,
  Zap,
} from "lucide-react";
import { api } from "./api";
type R = Record<string, any>;
const pretty = (s: string) =>
  s?.replaceAll("_", " ").replace(/\b\w/g, (x) => x.toUpperCase());
const when = (s: number) =>
  new Date(s * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const ref = (s: string) => s?.slice(0, 8).toUpperCase();
const icons: R = {
  workflow: GitBranch,
  prompt: Code2,
  model: Boxes,
  knowledge: BookOpen,
  connector: Waypoints,
  guardrail: ShieldCheck,
  benchmark: FlaskConical,
  budget: Wallet,
  release: Cloud,
  blueprint: Layers3,
};
const routes: R = {
  workflows: "workflow",
  prompts: "prompt",
  models: "model",
  knowledge: "knowledge",
  connectors: "connector",
  guardrails: "guardrail",
  evaluationlab: "benchmark",
  usage: "budget",
  operations: "release",
};
const labels: R = {
  workflow: "Workflow",
  prompt: "Prompt",
  model: "Model route",
  knowledge: "Knowledge source",
  connector: "Connector",
  guardrail: "Guardrail",
  benchmark: "Retrieval suite",
  budget: "Cost scenario",
  release: "Release plan",
  blueprint: "Interface plan",
};
const intros: R = {
  workflows: [
    "WORKFLOW STUDIO",
    "Design the path. Inspect every gate.",
    "Build versioned agent pipelines and run deterministic previews. External tools remain behind the governed action dispatcher.",
  ],
  prompts: [
    "PROMPT REGISTRY",
    "Make every instruction reviewable.",
    "Version prompts, render variables, inspect revisions and test deterministic assertions before connecting a model.",
  ],
  models: [
    "MODEL GATEWAY",
    "A home for your model contracts.",
    "Manage provider routes, timeouts and token limits. A validated configuration is not a verified provider connection.",
  ],
  knowledge: [
    "KNOWLEDGE & RETRIEVAL",
    "Ground the workflow in evidence.",
    "Import English or Arabic text, configure chunking and retrieve cited source excerpts using local BM25 ranking.",
  ],
  connectors: [
    "INTEGRATION CATALOG",
    "Explicit contracts. Bounded access.",
    "Design REST and MCP integrations with named scopes and secure credential references. External connections are unverified.",
  ],
  guardrails: [
    "SAFETY WORKBENCH",
    "Test the boundary before dispatch.",
    "Create local input rules, inspect detection signals and preview redaction. Runtime business policy stays authoritative.",
  ],
  evaluationlab: [
    "EVALUATION LAB",
    "Replace assumptions with evidence.",
    "Run repeatable retrieval benchmarks against your own sources. Results are calculated and saved, never invented.",
  ],
  usage: [
    "AI FINOPS",
    "Plan the cost before you scale.",
    "Estimate token scenarios using your rates. Provider billing, measured token usage and enforced spend caps are not connected.",
  ],
  operations: [
    "RELEASE READINESS",
    "Ship with a clear evidence trail.",
    "Version release plans, inspect rollback procedures and distinguish software capabilities from infrastructure prerequisites.",
  ],
};

function defaults(kind: string): R {
  const configs: R = {
    workflow: {
      nodes: [
        { id: "input", kind: "input", label: "Receive request", ref_id: "" },
        { id: "policy", kind: "policy", label: "Evaluate policy", ref_id: "" },
        {
          id: "approval",
          kind: "approval",
          label: "Independent review",
          ref_id: "",
        },
        { id: "tool", kind: "tool", label: "Business action", ref_id: "" },
        { id: "verify", kind: "verify", label: "Verify outcome", ref_id: "" },
        { id: "output", kind: "output", label: "Return evidence", ref_id: "" },
      ],
      description: "",
    },
    prompt: {
      template:
        "Use only the supplied evidence.\nQuestion: {{question}}\nEvidence: {{context}}\nCite your sources.",
      required_terms: ["Evidence"],
      forbidden_terms: [],
    },
    model: {
      provider: "Azure OpenAI",
      model: "enterprise-chat",
      endpoint: "",
      credential_ref: "",
      token_limit: 4096,
      timeout_ms: 30000,
      temperature: 0.2,
    },
    knowledge: {
      source: "Workspace document",
      language: "English",
      chunk_size: 700,
      content: "",
    },
    connector: {
      protocol: "REST",
      endpoint: "",
      credential_ref: "",
      scopes: ["read"],
      read_only: true,
    },
    guardrail: {
      blocked_terms: ["bypass approval"],
      detect_email: true,
      detect_override: true,
      mode: "block",
    },
    benchmark: {
      top_k: 3,
      cases: [
        {
          query: "purchase approval",
          expected_title: "Procurement policy handbook",
        },
      ],
    },
    budget: {
      monthly_limit: 500,
      input_per_million: 1,
      output_per_million: 3,
      currency: "USD",
    },
    release: {
      target: "Local",
      artifact: "nexus-ai-control",
      rollback:
        "Restore the prior source and compatible reviewed backup; verify readiness before resuming.",
      checks: [
        "Authentication and tenant isolation",
        "Independent approvals",
        "Reconciliation and recovery",
        "Independent security review",
      ],
    },
  };
  return {
    kind,
    name: "",
    description: "",
    config: structuredClone(configs[kind]),
  };
}
function Tag({ value }: { value: string }) {
  return (
    <span className={"nx-tag " + value}>
      {value === "validated" ? "Config checked" : pretty(value)}
    </span>
  );
}
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="nx-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
function exportJson(name: string, value: any) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name.replace(/[^a-zA-Z0-9_-]/g, "_") + ".json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Drawer({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const old = document.activeElement as HTMLElement;
    const frame = requestAnimationFrame(() =>
      root.current
        ?.querySelector<HTMLElement>("button,input,select,textarea")
        ?.focus(),
    );
    function key(e: KeyboardEvent) {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const items = Array.from(
          root.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
          ) || [],
        ).filter((x) => x.getClientRects().length);
        if (!items.length) {
          e.preventDefault();
          return;
        }
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", key);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", key);
      document.body.style.overflow = overflow;
      old?.focus();
    };
  }, []);
  return (
    <div
      className="nx-overlay"
      onMouseDown={(e) => e.target === e.currentTarget && close()}
    >
      <div
        className="nx-drawer"
        ref={root}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <div>
            <span className="nx-eyebrow">NEXUS / DESIGN WORKSPACE</span>
            <h2>{title}</h2>
          </div>
          <button
            className="nx-icon"
            onClick={close}
            aria-label="Close workspace editor"
          >
            <X size={21} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

function Workflow({
  nodes,
  active,
  onSelect,
  states = [],
}: {
  nodes: R[];
  active?: number;
  onSelect?: (i: number) => void;
  states?: R[];
}) {
  const symbols: R = {
    input: FileText,
    retrieve: Database,
    prompt: Code2,
    guardrail: ShieldCheck,
    policy: GitBranch,
    approval: LockKeyhole,
    tool: Waypoints,
    verify: CheckCircle2,
    output: Layers3,
  };
  return (
    <div className="nx-flow" aria-label="Workflow steps in execution order">
      {nodes.map((node, i) => {
        const Icon = symbols[node.kind] || Circle;
        const state = states.find((s) => s.id === node.id);
        return (
          <React.Fragment key={node.id}>
            {i > 0 && (
              <div className="nx-flow-arrow">
                <ChevronRight size={18} />
              </div>
            )}
            <button
              className={
                "nx-node " +
                (active === i ? "selected " : "") +
                (state?.status || "")
              }
              onClick={() => onSelect?.(i)}
              disabled={!onSelect}
              aria-label={"Step " + (i + 1) + ": " + node.label}
            >
              <span className="nx-node-num">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className={"nx-node-icon " + node.kind}>
                <Icon size={22} />
              </span>
              <strong>{node.label}</strong>
              <small>{state ? pretty(state.status) : pretty(node.kind)}</small>
            </button>
          </React.Fragment>
        );
      })}
    </div>
  );
}

function Result({ run }: { run: R }) {
  const r = run.result || {};
  return (
    <div className="nx-result" aria-live="polite">
      <div className="nx-result-heading">
        <span>
          <CheckCircle2 size={18} /> Run {ref(run.id)}
        </span>
        <Tag value={run.status} />
        <small>{run.duration_ms?.toFixed(2)} ms</small>
        <button
          className="nx-link"
          onClick={() => exportJson("NEXUS_run_" + ref(run.id), run)}
        >
          <Download size={14} /> JSON
        </button>
      </div>
      {r.boundary && (
        <p className="nx-boundary">
          <ShieldCheck size={15} />
          {r.boundary}
        </p>
      )}
      {r.steps && (
        <>
          <Workflow nodes={r.steps} states={r.steps} />
          <div className="nx-step-log">
            {r.steps.map((s: R) => (
              <div key={s.id}>
                <Tag value={s.status} />
                <strong>{s.label}</strong>
                <p>{s.detail}</p>
              </div>
            ))}
          </div>
        </>
      )}
      {r.rendered && <pre className="nx-code nx-rendered">{r.rendered}</pre>}
      {r.checks?.map((c: any, i: number) => (
        <div className="nx-check" key={i}>
          <Circle size={16} />
          {typeof c === "string" ? c : c.name}
          <Tag
            value={
              typeof c === "string" ? "planned" : c.passed ? "passed" : "failed"
            }
          />
        </div>
      ))}
      {r.citations && (
        <div className="nx-citations">
          {r.citations.length ? (
            r.citations.map((c: R) => (
              <article key={c.asset_id + ":" + c.chunk}>
                <div>
                  <BookOpen size={17} />
                  <strong>{c.title}</strong>
                  <span>
                    Chunk {c.chunk} · BM25 {c.score}
                  </span>
                </div>
                <p dir="auto">{c.text}</p>
                <small>{c.source}</small>
              </article>
            ))
          ) : (
            <p>
              No matching source excerpts. Add a source or change the search
              terms.
            </p>
          )}
        </div>
      )}
      {r.cases && (
        <>
          <div className="nx-score">
            <strong>
              {r.passed}/{r.total}
            </strong>
            <span>Passed · {r.metric}</span>
          </div>
          {r.cases.map((c: R, i: number) => (
            <div className="nx-check nx-benchmark-case" key={i}>
              <Tag value={c.passed ? "passed" : "failed"} />
              <div>
                <strong>{c.query}</strong>
                <p>
                  Expected: {c.expected_title}
                  <br />
                  Retrieved: {c.retrieved_titles.join(", ") || "No sources"}
                </p>
              </div>
            </div>
          ))}
        </>
      )}
      {r.verdict && (
        <>
          <div className="nx-score">
            <Tag value={r.verdict} />
            <span>
              {r.signals.length ? r.signals.join(" · ") : "No matching signals"}
            </span>
          </div>
          <pre className="nx-code">
            {r.output || "Output withheld by the selected block rule."}
          </pre>
        </>
      )}
      {r.estimated_cost !== undefined && (
        <div className="nx-cost-result">
          <span>Scenario estimate</span>
          <strong>${r.estimated_cost.toFixed(4)}</strong>
          <p>
            {r.input_tokens.toLocaleString()} input ·{" "}
            {r.output_tokens.toLocaleString()} output tokens
          </p>
          <Tag value={r.over_budget ? "over_budget" : "within_plan"} />
          <div className="nx-progress">
            <i
              style={{
                width:
                  Math.min(
                    100,
                    r.monthly_limit
                      ? (r.estimated_cost / r.monthly_limit) * 100
                      : 100,
                  ) + "%",
              }}
            />
          </div>
          <small>
            Against your ${r.monthly_limit.toLocaleString()} planning limit
          </small>
        </div>
      )}
      {r.configuration_valid && (
        <div className="nx-check">
          <CheckCircle2 size={18} /> Configuration schema passed{" "}
          <Tag value="connection_unverified" />
        </div>
      )}
    </div>
  );
}

export function FlagshipHub({
  page,
  legacy,
  me,
  onNavigate,
  onRun,
}: {
  page: string;
  legacy: R;
  me: R;
  onNavigate: (p: string) => void;
  onRun: () => void;
}) {
  const [state, setState] = useState<R>({
      assets: [],
      runs: [],
      mode: "local",
    }),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState("all"),
    [selected, setSelected] = useState(""),
    [draft, setDraft] = useState<R | null>(null),
    [tab, setTab] = useState("configure"),
    [history, setHistory] = useState<R[]>([]),
    [result, setResult] = useState<R | null>(null),
    [trace, setTrace] = useState<R | null>(null),
    [node, setNode] = useState(0);
  const [query, setQuery] = useState("purchase approval supplier threshold"),
    [amount, setAmount] = useState(12500),
    [variables, setVariables] = useState(
      '{"context":"Synthetic procurement policy evidence."}',
    ),
    [inputTokens, setInputTokens] = useState(100000),
    [outputTokens, setOutputTokens] = useState(20000);
  const kind = routes[page];
  const canEdit =
    me.permissions?.includes("operate") &&
    (kind !== "guardrail" || me.permissions?.includes("policy"));
  async function refresh() {
    try {
      const r = await api("/v1/workbench");
      setState(r);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, []);
  async function task(fn: () => Promise<any>, message?: string) {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      await refresh();
      if (message) setNotice(message);
      return r;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  const assets: R[] = state.assets;
  const live = assets.filter((a) => a.status !== "archived");
  const runs: R[] = state.runs;
  const filtered = assets.filter(
    (a) =>
      a.kind === kind &&
      (status === "archived"
        ? a.status === "archived"
        : a.status !== "archived" &&
          (status === "all" || a.status === status)) &&
      JSON.stringify([a.name, a.description, a.config])
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const current = filtered.find((a) => a.id === selected) || filtered[0];
  function edit(asset?: R, type = kind) {
    setDraft(structuredClone(asset || defaults(type)));
    setTab("configure");
    setResult(null);
    setHistory([]);
    setNode(0);
    setError("");
  }
  function config(key: string, value: any) {
    setDraft((d) => (d ? { ...d, config: { ...d.config, [key]: value } } : d));
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const payload = {
      kind: draft.kind,
      name: draft.name,
      description: draft.description,
      config: draft.config,
    };
    const r = await task(
      () =>
        api(
          draft.id ? "/v1/workbench/" + draft.id : "/v1/workbench",
          draft.id ? "PUT" : "POST",
          draft.id ? { ...payload, expected_version: draft.version } : payload,
        ),
      "Design saved with an immutable revision.",
    );
    if (r) {
      setDraft(r);
      setSelected(r.id);
    }
  }
  async function run(asset: R) {
    const r = await task(() =>
      api("/v1/workbench/" + asset.id + "/run", "POST", {
        query,
        amount,
        variables: asset.kind === "prompt" ? JSON.parse(variables) : {},
        input_tokens: inputTokens,
        output_tokens: outputTokens,
      }),
    );
    if (r) setResult(r);
  }
  function openTest(asset: R) {
    edit(asset);
    setTab("test");
  }
  async function historyTab() {
    setTab("history");
    if (draft?.id) {
      const r = await task(() => api("/v1/workbench/" + draft.id + "/history"));
      if (r) setHistory(r);
    }
  }
  function nodeChange(key: string, value: any) {
    if (!draft) return;
    const nodes = structuredClone(draft.config.nodes);
    nodes[node][key] = value;
    config("nodes", nodes);
  }
  function moveNode(direction: number) {
    if (!draft) return;
    const nodes = structuredClone(draft.config.nodes),
      next = node + direction;
    if (
      node === 0 ||
      node === nodes.length - 1 ||
      next <= 0 ||
      next >= nodes.length - 1
    )
      return;
    [nodes[node], nodes[next]] = [nodes[next], nodes[node]];
    config("nodes", nodes);
    setNode(next);
  }
  const nodeKinds = [
    "retrieve",
    "prompt",
    "guardrail",
    "policy",
    "approval",
    "tool",
    "verify",
  ];
  const workflow = page === "workflows" && current;
  const c = draft?.config || {};
  const count = (k: string) => live.filter((a) => a.kind === k).length;
  const title = intros[page];
  const runList = runs.filter(
    (r) =>
      (!kind || r.kind === kind) &&
      (!search ||
        JSON.stringify(r).toLowerCase().includes(search.toLowerCase())),
  );
  const starter = () =>
    task(
      () => api("/v1/workbench-starter", "POST"),
      "Synthetic starter designs loaded. No provider connection or deployment was activated.",
    );
  const runTable = (list: R[]) =>
    list.length ? (
      <div className="nx-table-wrap">
        <table className="nx-table">
          <thead>
            <tr>
              <th>Trace / asset</th>
              <th>Operation</th>
              <th>Result</th>
              <th>Duration</th>
              <th>Recorded</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.slice(0, 12).map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>
                    {assets.find((a) => a.id === r.asset_id)?.name ||
                      "Workspace run"}
                  </strong>
                  <small>
                    RUN-{ref(r.id)} · v{r.asset_version}
                  </small>
                </td>
                <td>{labels[r.kind]}</td>
                <td>
                  <Tag value={r.status} />
                </td>
                <td>{r.duration_ms.toFixed(2)} ms</td>
                <td>{when(r.created)}</td>
                <td>
                  <button
                    className="nx-icon"
                    aria-label={"Inspect run " + ref(r.id)}
                    onClick={() => setTrace(r)}
                  >
                    <ArrowUpRight size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <div className="nx-empty compact">
        <Activity size={30} />
        <h3>No runs recorded yet</h3>
        <p>
          Run a saved workflow preview, retrieval query or evaluation to
          generate real local evidence.
        </p>
        <button className="nx-link" onClick={() => onNavigate("workflows")}>
          Open Workflow Studio <ArrowRight size={15} />
        </button>
      </div>
    );
  if (loading)
    return (
      <div className="nx-loading">
        <span className="spinner" /> Loading AI workspace…
      </div>
    );
  return (
    <div className="nx-hub">
      {error && (
        <div className="nx-alert" role="alert">
          <ShieldX size={17} />
          <span>{error}</span>
          <button
            aria-label="Dismiss workbench error"
            onClick={() => setError("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {notice && (
        <div className="nx-notice" role="status">
          <CheckCircle2 size={17} />
          <span>{notice}</span>
          <button
            aria-label="Dismiss confirmation"
            onClick={() => setNotice("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {!canEdit && (
        <p className="nx-permission">
          <LockKeyhole size={14} /> Your role can inspect this workspace.
          Creating, testing and revising designs requires the operate
          permission.
        </p>
      )}

      {page === "overview" && (
        <>
          <section className="nx-hero">
            <div>
              <span className="nx-eyebrow">
                <i /> THE ENTERPRISE AI CONTROL PLANE
              </span>
              <h2>
                Build with intelligence.
                <br />
                <em>Operate with confidence.</em>
              </h2>
              <p>
                From the first prompt to a governed action.
                <br />
                One workspace for your AI engineering lifecycle.
              </p>
              <div className="nx-hero-actions">
                <button
                  className="btn btn-primary"
                  onClick={() => onNavigate("workflows")}
                >
                  <GitBranch size={16} /> Open Workflow Studio{" "}
                  <ArrowRight size={16} />
                </button>
                <button
                  className="nx-link"
                  onClick={() => onNavigate("operations")}
                >
                  View readiness <ArrowUpRight size={14} />
                </button>
              </div>
            </div>
            <img
              src="/nexus-agent-neon.png"
              alt="NEXUS AI assistant at a holographic control platform"
            />
            <span className="nx-hero-label">
              <ShieldCheck size={14} /> Governed by design
            </span>
          </section>
          <div className="nx-metrics">
            {[
              [
                "Active agents",
                legacy.overview.active_agents || 0,
                "Registered workload identities",
                Boxes,
              ],
              [
                "Governed actions",
                legacy.overview.actions || 0,
                "Actual policy decisions",
                GitBranch,
              ],
              [
                "Pending approvals",
                legacy.overview.pending || 0,
                "Independent human review",
                LockKeyhole,
              ],
              [
                "Verified outcomes",
                legacy.overview.verified || 0,
                "Recorded business outcomes",
                CheckCircle2,
              ],
              [
                "Design assets",
                live.length,
                "Versioned workspace records",
                Layers3,
              ],
              [
                "Workbench runs",
                runs.length,
                "Latest 100 recorded previews",
                FlaskConical,
              ],
            ].map(([label, value, hint, Icon]: any) => (
              <div className="nx-metric" key={label}>
                <span>
                  {label}
                  <Icon size={16} />
                </span>
                <strong>{value}</strong>
                <small>{hint}</small>
              </div>
            ))}
          </div>
          <div className="nx-section-heading">
            <div>
              <span className="nx-eyebrow">YOUR ENGINEERING WORKSPACE</span>
              <h2>Every capability. One connected lifecycle.</h2>
            </div>
            {canEdit &&
              me.permissions?.includes("policy") &&
              state.mode === "local" && (
                <button
                  className="btn btn-outline"
                  disabled={busy}
                  onClick={starter}
                >
                  <Sparkles size={15} /> Load synthetic starter designs
                </button>
              )}
          </div>
          <div className="nx-capabilities">
            {[
              [
                "workflows",
                "Agent orchestration",
                "Design pipelines, human checkpoints and controlled tool steps.",
                "workflow",
                "cyan",
              ],
              [
                "knowledge",
                "Knowledge & RAG",
                "Import bilingual sources and inspect cited retrieval results.",
                "knowledge",
                "teal",
              ],
              [
                "prompts",
                "Prompt engineering",
                "Version, render and test your instruction contracts.",
                "prompt",
                "violet",
              ],
              [
                "models",
                "Model gateway",
                "Configure providers, token limits and timeout policies.",
                "model",
                "blue",
              ],
              [
                "evaluationlab",
                "Evaluation lab",
                "Measure retrieval against repeatable, inspectable cases.",
                "benchmark",
                "amber",
              ],
              [
                "guardrails",
                "Safety & governance",
                "Test input boundaries and review policy-controlled actions.",
                "guardrail",
                "pink",
              ],
            ].map(([route, label, body, k, tone]) => {
              const Icon = icons[k];
              return (
                <button
                  className={"nx-capability " + tone}
                  key={route}
                  onClick={() => onNavigate(route)}
                >
                  <span className="nx-capability-icon">
                    <Icon size={22} />
                  </span>
                  <span className="nx-card-count">{count(k)} assets</span>
                  <h3>{label}</h3>
                  <p>{body}</p>
                  <span className="nx-capability-link">
                    Open workspace <ArrowUpRight size={15} />
                  </span>
                </button>
              );
            })}
          </div>
          <div className="nx-two">
            <section className="nx-panel">
              <div className="nx-panel-heading">
                <div>
                  <h2>Action activity</h2>
                  <p>Policy decisions over the last 7 days</p>
                </div>
                <span className="nx-live">
                  <i /> Runtime records
                </span>
              </div>
              <div className="nx-legend">
                <span>
                  <i />
                  Allowed
                </span>
                <span>
                  <i />
                  Approval required
                </span>
                <span>
                  <i />
                  Denied
                </span>
              </div>
              <div className="nx-chart">
                {(legacy.overview.trend || []).map((d: R, i: number) => {
                  const max = Math.max(
                    1,
                    ...(legacy.overview.trend || []).map(
                      (v: R) => v.allowed + v.approval + v.denied,
                    ),
                  );
                  return (
                    <div className="nx-chart-column" key={i}>
                      <div
                        className="nx-bar-space"
                        aria-label={`${d.day}: ${d.allowed} allowed, ${d.approval} review, ${d.denied} denied`}
                      >
                        <i style={{ height: (d.allowed / max) * 100 + "%" }} />
                        <i style={{ height: (d.approval / max) * 100 + "%" }} />
                        <i style={{ height: (d.denied / max) * 100 + "%" }} />
                      </div>
                      <small>{d.day}</small>
                    </div>
                  );
                })}
              </div>
              <div className="nx-panel-foot">
                Counts come from recorded action decisions.
                <button
                  className="nx-link"
                  onClick={() => onNavigate("executions")}
                >
                  View ledger <ArrowRight size={13} />
                </button>
              </div>
            </section>
            <section className="nx-panel">
              <div className="nx-panel-heading">
                <div>
                  <h2>Attention & assurance</h2>
                  <p>Signals that require a human decision</p>
                </div>
                <ShieldCheck size={21} />
              </div>
              {[
                [
                  "approvals",
                  `${legacy.overview.pending || 0} approvals pending`,
                  "Review an exact payload before the displayed expiry.",
                  LockKeyhole,
                ],
                [
                  "executions",
                  `${(legacy.actions || []).filter((a: R) => a.status === "outcome_unknown").length} unknown outcomes`,
                  "Reconcile uncertainty before recreating a business effect.",
                  RefreshCw,
                ],
                [
                  "connectors",
                  "External connections unverified",
                  "Design contracts are saved; provider access is not activated.",
                  Cloud,
                ],
                [
                  "operations",
                  "Production readiness gates",
                  "Inspect identity, telemetry, recovery and release evidence.",
                  ShieldCheck,
                ],
              ].map(([route, label, body, Icon]: any) => (
                <button
                  className="nx-attention"
                  key={route}
                  onClick={() => onNavigate(route)}
                >
                  <span>
                    <Icon size={19} />
                  </span>
                  <div>
                    <strong>{label}</strong>
                    <p>{body}</p>
                  </div>
                  <ChevronRight size={16} />
                </button>
              ))}
            </section>
          </div>
          <section className="nx-panel">
            <div className="nx-panel-heading">
              <div>
                <h2>Recent workbench evidence</h2>
                <p>Measured local runs linked to versioned assets</p>
              </div>
              <button
                className="nx-link"
                onClick={() => onNavigate("observability")}
              >
                All traces <ArrowRight size={14} />
              </button>
            </div>
            {runTable(runs)}
          </section>
        </>
      )}

      {title && (
        <>
          <section className="nx-feature-banner">
            <span className="nx-feature-symbol">
              {React.createElement(icons[kind], { size: 31, strokeWidth: 1.5 })}
            </span>
            <div>
              <span className="nx-eyebrow">{title[0]}</span>
              <h2>{title[1]}</h2>
              <p>{title[2]}</p>
            </div>
            <span className="nx-maturity">
              {kind === "knowledge" || kind === "benchmark"
                ? "LOCAL ENGINE"
                : "DESIGN WORKSPACE"}
            </span>
          </section>
          <div className="nx-toolbar">
            <div className="nx-search">
              <Search size={16} />
              <input
                aria-label="Search design assets"
                placeholder={`Search ${labels[kind].toLowerCase()}s…`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="nx-tabs" aria-label="Asset status">
              {["all", "draft", "validated", "archived"].map((s) => (
                <button
                  key={s}
                  className={status === s ? "selected" : ""}
                  onClick={() => setStatus(s)}
                >
                  {s === "validated" ? "Config checked" : pretty(s)}
                </button>
              ))}
            </div>
            <button
              className="nx-icon"
              aria-label="Refresh design workspace"
              onClick={refresh}
            >
              <RefreshCw size={16} />
            </button>
            <button
              className="btn btn-primary"
              disabled={!canEdit || busy}
              onClick={() => edit()}
            >
              <Plus size={16} /> New {labels[kind].toLowerCase()}
            </button>
          </div>
          {filtered.length === 0 ? (
            <section className="nx-panel nx-empty">
              <span className="nx-empty-symbol">
                {React.createElement(icons[kind], { size: 32 })}
              </span>
              <h2>
                {search || status !== "all"
                  ? "No designs match this view"
                  : "Start with a clear design"}
              </h2>
              <p>
                {search || status !== "all"
                  ? "Try another search or status filter."
                  : `Create a ${labels[kind].toLowerCase()} or load the synthetic starter workspace to explore complete examples.`}
              </p>
              <div>
                <button
                  className="btn btn-primary"
                  disabled={!canEdit}
                  onClick={() => edit()}
                >
                  <Plus size={16} /> Create {labels[kind].toLowerCase()}
                </button>
                {state.mode === "local" && (
                  <button
                    className="btn btn-outline"
                    disabled={!canEdit || busy}
                    onClick={starter}
                  >
                    <Sparkles size={16} /> Load starter designs
                  </button>
                )}
              </div>
            </section>
          ) : (
            <>
              {workflow && (
                <section className="nx-panel nx-canvas">
                  <div className="nx-panel-heading">
                    <div>
                      <span className="nx-eyebrow">
                        VISUAL PIPELINE / DRY-RUN DESIGN
                      </span>
                      <h2>{current.name}</h2>
                    </div>
                    <select
                      aria-label="Select workflow"
                      value={current.id}
                      onChange={(e) => setSelected(e.target.value)}
                    >
                      {filtered.map((a) => (
                        <option value={a.id} key={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </select>
                    <Tag value={current.status} />
                  </div>
                  <Workflow
                    nodes={current.config.nodes}
                    onSelect={() => edit(current)}
                  />
                  <div className="nx-panel-foot">
                    <span>No external effects occur in a preview.</span>
                    <button
                      className="btn btn-outline"
                      onClick={() => openTest(current)}
                      disabled={!canEdit}
                    >
                      <Play size={15} /> Dry run workflow
                    </button>
                    <button
                      className="nx-link"
                      onClick={onRun}
                      disabled={!canEdit}
                    >
                      Run governed action <ArrowUpRight size={15} />
                    </button>
                  </div>
                </section>
              )}
              <div
                className={
                  "nx-asset-grid " + (kind === "knowledge" ? "knowledge" : "")
                }
              >
                {filtered.map((a) => {
                  const Icon = icons[a.kind];
                  return (
                    <article className="nx-asset-card" key={a.id}>
                      <div className="nx-asset-top">
                        <span className={"nx-asset-icon " + a.kind}>
                          <Icon size={22} />
                        </span>
                        <Tag value={a.status} />
                        <small>v{a.version}</small>
                      </div>
                      <h3>{a.name}</h3>
                      <p>{a.description || "Versioned workspace design"}</p>
                      {a.kind === "model" && (
                        <>
                          <div className="nx-property">
                            <span>Provider</span>
                            <strong>{a.config.provider}</strong>
                          </div>
                          <div className="nx-property">
                            <span>Deployment / model</span>
                            <code>{a.config.model}</code>
                          </div>
                          <div className="nx-property">
                            <span>Output cap / timeout</span>
                            <strong>
                              {a.config.token_limit.toLocaleString()} tokens ·{" "}
                              {a.config.timeout_ms / 1000}s
                            </strong>
                          </div>
                          <span className="nx-status-line">
                            <Circle size={9} /> Connection unverified
                          </span>
                        </>
                      )}
                      {a.kind === "prompt" && (
                        <>
                          <pre className="nx-code nx-prompt-snippet">
                            {a.config.template.slice(0, 190)}
                            {a.config.template.length > 190 ? "…" : ""}
                          </pre>
                          <div className="nx-chip-row">
                            {Array.from(
                              new Set(
                                a.config.template.match(/{{\s*\w+\s*}}/g) || [],
                              ),
                            ).map((v: any) => (
                              <span key={v}>{v}</span>
                            ))}
                          </div>
                        </>
                      )}
                      {a.kind === "knowledge" && (
                        <>
                          <div className="nx-property">
                            <span>Language</span>
                            <strong>{a.config.language}</strong>
                          </div>
                          <div className="nx-property">
                            <span>Source content</span>
                            <strong>
                              {a.config.content.length.toLocaleString()}{" "}
                              characters
                            </strong>
                          </div>
                          <div className="nx-property">
                            <span>Chunk size</span>
                            <strong>{a.config.chunk_size} characters</strong>
                          </div>
                          <span className="nx-status-line teal">
                            <CheckCircle2 size={13} /> Available to local BM25
                            retrieval
                          </span>
                        </>
                      )}
                      {a.kind === "connector" && (
                        <>
                          <div className="nx-property">
                            <span>Contract</span>
                            <strong>
                              {a.config.protocol} ·{" "}
                              {a.config.read_only
                                ? "Read-only"
                                : "Tool operations"}
                            </strong>
                          </div>
                          <div className="nx-chip-row">
                            {a.config.scopes.map((s: string) => (
                              <span key={s}>{s}</span>
                            ))}
                          </div>
                          <span className="nx-status-line">
                            <Circle size={9} /> Connection unverified
                          </span>
                        </>
                      )}
                      {a.kind === "guardrail" && (
                        <div className="nx-chip-row">
                          {a.config.detect_email && (
                            <span>Email detection</span>
                          )}
                          {a.config.detect_override && (
                            <span>Instruction override</span>
                          )}
                          <span>{a.config.mode}</span>
                          <span>{a.config.blocked_terms.length} terms</span>
                        </div>
                      )}
                      {a.kind === "workflow" && (
                        <div className="nx-chip-row">
                          <span>{a.config.nodes.length} steps</span>
                          <span>
                            {
                              a.config.nodes.filter((n: R) =>
                                ["policy", "approval", "guardrail"].includes(
                                  n.kind,
                                ),
                              ).length
                            }{" "}
                            control steps
                          </span>
                          <span>Dry-run engine</span>
                        </div>
                      )}
                      {a.kind === "benchmark" && (
                        <div className="nx-property">
                          <span>Test cases</span>
                          <strong>
                            {a.config.cases.length} · recall at {a.config.top_k}
                          </strong>
                        </div>
                      )}
                      {a.kind === "budget" && (
                        <>
                          <div className="nx-budget-number">
                            ${a.config.monthly_limit.toLocaleString()}
                            <small>monthly planning limit</small>
                          </div>
                          <div className="nx-property">
                            <span>Per million input / output</span>
                            <strong>
                              ${a.config.input_per_million} / $
                              {a.config.output_per_million}
                            </strong>
                          </div>
                          <span className="nx-status-line">
                            Estimate only · no enforced spend cap
                          </span>
                        </>
                      )}
                      {a.kind === "release" && (
                        <>
                          <div className="nx-property">
                            <span>Target</span>
                            <strong>{a.config.target}</strong>
                          </div>
                          <div className="nx-chip-row">
                            <span>{a.config.checks.length} planned gates</span>
                            <span>No deployment performed</span>
                          </div>
                        </>
                      )}
                      <footer>
                        <small>Updated {when(a.updated)}</small>
                        <div>
                          <button
                            className="nx-icon"
                            title="Download design JSON"
                            aria-label={"Download " + a.name}
                            onClick={() => exportJson(a.name, a)}
                          >
                            <Download size={15} />
                          </button>
                          <button className="nx-link" onClick={() => edit(a)}>
                            Open <ArrowUpRight size={14} />
                          </button>
                        </div>
                      </footer>
                      <div className="nx-card-actions">
                        <button
                          className="btn btn-outline"
                          disabled={!canEdit || a.status === "archived"}
                          onClick={() => openTest(a)}
                        >
                          <Play size={14} />
                          {a.kind === "workflow"
                            ? "Dry run"
                            : a.kind === "knowledge"
                              ? "Retrieve evidence"
                              : a.kind === "prompt"
                                ? "Render & test"
                                : a.kind === "guardrail"
                                  ? "Test input"
                                  : a.kind === "benchmark"
                                    ? "Run benchmark"
                                    : a.kind === "budget"
                                      ? "Calculate scenario"
                                      : "Inspect plan"}
                        </button>
                        <button
                          className="nx-link"
                          disabled={!canEdit}
                          onClick={() => {
                            const d = structuredClone(a);
                            delete d.id;
                            delete d.version;
                            d.name += " (copy)";
                            edit(d);
                          }}
                        >
                          <Copy size={14} /> Duplicate
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
              {page === "operations" && (
                <section className="nx-panel">
                  <div className="nx-panel-heading">
                    <div>
                      <h2>Capability & integration gates</h2>
                      <p>
                        Readiness is evidence-based; configuration is not
                        deployment.
                      </p>
                    </div>
                    <ShieldCheck size={22} />
                  </div>
                  {[
                    [
                      "Local identity, roles and CSRF",
                      "Implemented in control plane",
                      "settings",
                    ],
                    [
                      "Policy decisions and independent approval",
                      "Implemented for synthetic business actions",
                      "policies",
                    ],
                    [
                      "Versioned design assets and deterministic evaluation",
                      "Implemented in the local workbench",
                      "evaluationlab",
                    ],
                    [
                      "Provider execution and usage ledger",
                      "Integration required",
                      "models",
                    ],
                    [
                      "Customer APIs, managed secrets and egress controls",
                      "Integration required",
                      "connectors",
                    ],
                    [
                      "Cloud deployment, recovery and independent review",
                      "Evidence required",
                      "operations",
                    ],
                  ].map(([name, status, route]) => (
                    <div className="nx-readiness-line" key={name}>
                      <Circle size={16} />
                      <div>
                        <strong>{name}</strong>
                        <small>{status}</small>
                      </div>
                      <button
                        className="nx-link"
                        onClick={() => onNavigate(route)}
                      >
                        Inspect <ArrowUpRight size={14} />
                      </button>
                    </div>
                  ))}
                </section>
              )}
              {runList.length > 0 && (
                <section className="nx-panel">
                  <div className="nx-panel-heading">
                    <div>
                      <h2>Recorded {labels[kind].toLowerCase()} runs</h2>
                      <p>
                        Latest results are tied to their saved asset version.
                      </p>
                    </div>
                    <History size={20} />
                  </div>
                  {runTable(runList)}
                </section>
              )}
            </>
          )}
        </>
      )}

      {page === "observability" && (
        <>
          <section className="nx-feature-banner">
            <span className="nx-feature-symbol">
              <Activity size={31} />
            </span>
            <div>
              <span className="nx-eyebrow">TRACES & OBSERVABILITY</span>
              <h2>Follow the evidence, end to end.</h2>
              <p>
                Inspect actual local workbench measurements and governed
                business actions. External model telemetry is not connected.
              </p>
            </div>
            <span className="nx-maturity">LOCAL RUNTIME</span>
          </section>
          <div className="nx-metrics four">
            {[
              ["Workbench runs", runs.length],
              [
                "Completed",
                runs.filter((r) => r.status === "completed").length,
              ],
              [
                "Gated previews",
                runs.filter((r) => r.status === "gated").length,
              ],
              [
                "Mean local duration",
                runs.length
                  ? (
                      runs.reduce((n, r) => n + r.duration_ms, 0) / runs.length
                    ).toFixed(1) + " ms"
                  : "—",
              ],
            ].map(([label, value]) => (
              <div className="nx-metric" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <small>Latest 100 recorded workbench runs</small>
              </div>
            ))}
          </div>
          <div className="nx-toolbar">
            <div className="nx-search">
              <Search size={16} />
              <input
                aria-label="Search local traces"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search trace IDs, asset types or results…"
              />
            </div>
            <button className="btn btn-outline" onClick={refresh}>
              <RefreshCw size={15} /> Refresh traces
            </button>
            <button
              className="btn btn-outline"
              onClick={() => exportJson("NEXUS_workbench_runs", runList)}
            >
              <Download size={15} /> Export local runs
            </button>
          </div>
          <section className="nx-panel">
            <div className="nx-panel-heading">
              <div>
                <h2>Workbench trace ledger</h2>
                <p>
                  Measured duration, version context and inspectable outputs
                </p>
              </div>
              <Activity size={21} />
            </div>
            {runTable(runList)}
          </section>
          <section className="nx-panel">
            <div className="nx-panel-heading">
              <div>
                <h2>Governed business execution</h2>
                <p>
                  Independent action and approval records remain in the control
                  plane.
                </p>
              </div>
              <button
                className="nx-link"
                onClick={() => onNavigate("executions")}
              >
                Open full ledger <ArrowRight size={14} />
              </button>
            </div>
            <div className="nx-business-traces">
              {(legacy.actions || []).slice(0, 5).map((a: R) => (
                <button key={a.id} onClick={() => onNavigate("executions")}>
                  <GitBranch size={18} />
                  <div>
                    <strong>ACT-{ref(a.id)}</strong>
                    <small>
                      {a.envelope?.action} · {when(a.created)}
                    </small>
                  </div>
                  <Tag value={a.status} />
                  <ChevronRight size={16} />
                </button>
              ))}
              {!legacy.actions?.length && (
                <p>
                  No governed actions yet. Run a synthetic supplier lookup or
                  purchase request to create a trail.
                </p>
              )}
            </div>
          </section>
        </>
      )}

      {draft && (
        <Drawer
          title={draft.id ? draft.name : "New " + labels[draft.kind]}
          close={() => setDraft(null)}
        >
          <div className="nx-editor-meta">
            <Tag value={draft.status || "draft"} />
            <span>
              {draft.id ? "Version " + draft.version : "Unsaved design"}
            </span>
            <span>Staging workspace</span>
            {draft.id && (
              <button
                className="nx-link"
                onClick={() => exportJson(draft.name, draft)}
              >
                <Download size={14} /> Export design
              </button>
            )}
          </div>
          <div className="nx-editor-tabs">
            {[
              ["configure", "Configuration", Settings2],
              ["test", "Test bench", FlaskConical],
              ["history", "Version history", History],
            ].map(([id, label, Icon]: any) => (
              <button
                className={tab === id ? "active" : ""}
                key={id}
                onClick={() => (id === "history" ? historyTab() : setTab(id))}
              >
                <Icon size={15} />
                {label}
              </button>
            ))}
          </div>
          {error && (
            <div className="nx-alert nx-editor-error" role="alert">
              {error}
            </div>
          )}
          {tab === "configure" && (
            <form onSubmit={save} className="nx-editor-form">
              <fieldset
                disabled={!canEdit || draft.status === "archived" || busy}
              >
                <div className="nx-two-fields">
                  <Field label="Name">
                    <input
                      required
                      minLength={2}
                      maxLength={120}
                      value={draft.name}
                      onChange={(e) =>
                        setDraft({ ...draft, name: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Description">
                    <input
                      maxLength={500}
                      value={draft.description}
                      onChange={(e) =>
                        setDraft({ ...draft, description: e.target.value })
                      }
                    />
                  </Field>
                </div>
                {draft.kind === "workflow" && (
                  <>
                    <Workflow
                      nodes={c.nodes}
                      active={node}
                      onSelect={setNode}
                    />
                    <div className="nx-builder-tools">
                      <button
                        type="button"
                        className="btn btn-outline"
                        disabled={c.nodes.length >= 12}
                        onClick={() => {
                          const nodes = structuredClone(c.nodes);
                          nodes.splice(nodes.length - 1, 0, {
                            id: crypto.randomUUID().slice(0, 8),
                            kind: "prompt",
                            label: "New prompt",
                            ref_id: "",
                          });
                          config("nodes", nodes);
                          setNode(nodes.length - 2);
                        }}
                      >
                        <Plus size={15} /> Add step
                      </button>
                      <button
                        type="button"
                        className="nx-icon"
                        disabled={node <= 1 || node >= c.nodes.length - 1}
                        aria-label="Move selected step earlier"
                        onClick={() => moveNode(-1)}
                      >
                        <ArrowUp size={16} />
                      </button>
                      <button
                        type="button"
                        className="nx-icon"
                        disabled={node === 0 || node >= c.nodes.length - 2}
                        aria-label="Move selected step later"
                        onClick={() => moveNode(1)}
                      >
                        <ArrowDown size={16} />
                      </button>
                      <button
                        type="button"
                        className="nx-icon"
                        disabled={node === 0 || node === c.nodes.length - 1}
                        aria-label="Remove selected step"
                        onClick={() => {
                          config(
                            "nodes",
                            c.nodes.filter((_: R, i: number) => i !== node),
                          );
                          setNode(0);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <div className="nx-two-fields">
                      <Field label="Selected step label">
                        <input
                          value={c.nodes[node]?.label || ""}
                          maxLength={70}
                          onChange={(e) => nodeChange("label", e.target.value)}
                        />
                      </Field>
                      <Field label="Step kind">
                        <select
                          value={c.nodes[node]?.kind}
                          disabled={node === 0 || node === c.nodes.length - 1}
                          onChange={(e) => {
                            nodeChange("kind", e.target.value);
                            const nodes = structuredClone(c.nodes);
                            nodes[node] = {
                              ...nodes[node],
                              kind: e.target.value,
                              ref_id: "",
                              ref_version: null,
                            };
                            config("nodes", nodes);
                          }}
                        >
                          {["input", ...nodeKinds, "output"].map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                      </Field>
                    </div>
                    {["prompt", "retrieve", "guardrail"].includes(
                      c.nodes[node]?.kind,
                    ) && (
                      <Field label="Optional versioned asset reference">
                        <select
                          value={c.nodes[node]?.ref_id || ""}
                          onChange={(e) => {
                            const nodes = structuredClone(c.nodes);
                            nodes[node] = {
                              ...nodes[node],
                              ref_id: e.target.value,
                              ref_version:
                                live.find((a) => a.id === e.target.value)
                                  ?.version || null,
                            };
                            config("nodes", nodes);
                          }}
                        >
                          <option value="">
                            Use workspace default / preview behavior
                          </option>
                          {live
                            .filter(
                              (a) =>
                                a.kind ===
                                (
                                  {
                                    prompt: "prompt",
                                    retrieve: "knowledge",
                                    guardrail: "guardrail",
                                  } as R
                                )[c.nodes[node]?.kind],
                            )
                            .map((a) => (
                              <option value={a.id} key={a.id}>
                                {a.name} · v{a.version}
                              </option>
                            ))}
                        </select>
                      </Field>
                    )}
                    <p className="nx-boundary">
                      Input must be first and Output last. Tool steps require
                      preceding policy and independent approval gates, plus a
                      subsequent verification step.
                    </p>
                  </>
                )}
                {draft.kind === "prompt" && (
                  <>
                    <Field
                      label="Prompt template"
                      hint="Variables use {{question}}, {{context}} or your own names."
                    >
                      <textarea
                        className="nx-template"
                        required
                        minLength={3}
                        maxLength={12000}
                        value={c.template}
                        onChange={(e) => config("template", e.target.value)}
                      />
                    </Field>
                    <div className="nx-two-fields">
                      <Field label="Required terms (comma separated)">
                        <input
                          value={c.required_terms.join(",")}
                          onChange={(e) =>
                            config(
                              "required_terms",
                              e.target.value.split(",").filter(Boolean),
                            )
                          }
                        />
                      </Field>
                      <Field label="Forbidden terms (comma separated)">
                        <input
                          value={c.forbidden_terms.join(",")}
                          onChange={(e) =>
                            config(
                              "forbidden_terms",
                              e.target.value.split(",").filter(Boolean),
                            )
                          }
                        />
                      </Field>
                    </div>
                  </>
                )}
                {draft.kind === "knowledge" && (
                  <>
                    <div className="nx-two-fields">
                      <Field label="Source / provenance">
                        <input
                          maxLength={300}
                          value={c.source}
                          onChange={(e) => config("source", e.target.value)}
                        />
                      </Field>
                      <Field label="Language">
                        <select
                          value={c.language}
                          onChange={(e) => config("language", e.target.value)}
                        >
                          {["English", "Arabic", "Bilingual"].map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                      </Field>
                    </div>
                    <Field label="Chunk size (characters)">
                      <input
                        type="number"
                        min={200}
                        max={2000}
                        value={c.chunk_size}
                        onChange={(e) =>
                          config("chunk_size", Number(e.target.value))
                        }
                      />
                    </Field>
                    <label className="nx-import">
                      <Upload size={17} /> Import UTF-8 .txt or .md
                      <input
                        type="file"
                        accept=".txt,.md"
                        onChange={async (e) => {
                          const f = e.target.files?.[0];
                          if (!f) return;
                          if (f.size > 60000) {
                            setError(
                              "Choose a text file smaller than 60 KB (content limit: 24000 characters).",
                            );
                            return;
                          }
                          const content = await f.text();
                          if (content.length > 24000) {
                            setError(
                              "Document content exceeds 24000 characters.",
                            );
                            return;
                          }
                          config("content", content);
                        }}
                      />
                    </label>
                    <Field
                      label="Document content"
                      hint="This rehearsal accepts plain text or Markdown. Use Document library for working PDF/DOCX/OCR intake. Embeddings remain separate work."
                    >
                      <textarea
                        className="nx-template"
                        dir="auto"
                        minLength={10}
                        maxLength={24000}
                        required
                        value={c.content}
                        onChange={(e) => config("content", e.target.value)}
                      />
                    </Field>
                  </>
                )}
                {draft.kind === "model" && (
                  <>
                    <div className="nx-two-fields">
                      <Field label="Provider">
                        <select
                          value={c.provider}
                          onChange={(e) => {
                            config("provider", e.target.value);
                            if (e.target.value === "Ollama") {
                              config("endpoint", "http://127.0.0.1:11434");
                              config("credential_ref", "");
                            }
                          }}
                        >
                          {[
                            "Azure OpenAI",
                            "OpenAI",
                            "Ollama",
                            "Anthropic",
                            "Local endpoint",
                          ].map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Model / deployment alias">
                        <input
                          required
                          maxLength={100}
                          value={c.model}
                          onChange={(e) => config("model", e.target.value)}
                        />
                      </Field>
                    </div>
                    <Field label={c.provider === "Ollama" ? "Local Ollama endpoint" : "HTTPS endpoint (optional)"}>
                      <input
                        value={c.endpoint}
                        placeholder={c.provider === "Ollama" ? "http://127.0.0.1:11434" : "https://your-resource.example"}
                        readOnly={c.provider === "Ollama"}
                        onChange={(e) => config("endpoint", e.target.value)}
                      />
                    </Field>
                    <Field
                      label="Credential environment reference"
                      hint={c.provider === "Ollama" ? "Leave empty for local Ollama. Enable the exact installed model in server settings." : "Reference only, for example env:NEXUS_LLM_API_KEY. Never paste a credential."}
                    >
                      <input
                        value={c.credential_ref}
                        disabled={c.provider === "Ollama"}
                        onChange={(e) =>
                          config("credential_ref", e.target.value)
                        }
                      />
                    </Field>
                    <div className="nx-two-fields">
                      <Field label="Output token cap">
                        <input
                          type="number"
                          min={128}
                          max={128000}
                          value={c.token_limit}
                          onChange={(e) =>
                            config("token_limit", Number(e.target.value))
                          }
                        />
                      </Field>
                      <Field label="Timeout (ms)">
                        <input
                          type="number"
                          min={1000}
                          max={120000}
                          value={c.timeout_ms}
                          onChange={(e) =>
                            config("timeout_ms", Number(e.target.value))
                          }
                        />
                      </Field>
                    </div>
                    <Field label="Temperature">
                      <input
                        type="number"
                        step="0.1"
                        min={0}
                        max={2}
                        value={c.temperature}
                        onChange={(e) =>
                          config("temperature", Number(e.target.value))
                        }
                      />
                    </Field>
                    <p className="nx-boundary">
                      Saving or checking this route does not call the provider
                      or resolve the credential reference.
                    </p>
                  </>
                )}
                {draft.kind === "connector" && (
                  <>
                    <div className="nx-two-fields">
                      <Field label="Protocol">
                        <select
                          value={c.protocol}
                          onChange={(e) => config("protocol", e.target.value)}
                        >
                          {["REST", "MCP", "Webhook", "Database"].map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Access contract">
                        <select
                          value={c.read_only ? "read" : "write"}
                          onChange={(e) =>
                            config("read_only", e.target.value === "read")
                          }
                        >
                          <option value="read">Read only</option>
                          <option value="write">Tool operations</option>
                        </select>
                      </Field>
                    </div>
                    <Field label="HTTPS endpoint (optional)">
                      <input
                        value={c.endpoint}
                        onChange={(e) => config("endpoint", e.target.value)}
                      />
                    </Field>
                    <Field
                      label="Credential environment reference"
                      hint="A reference only. It is not read, resolved or used by this design workspace."
                    >
                      <input
                        value={c.credential_ref}
                        onChange={(e) =>
                          config("credential_ref", e.target.value)
                        }
                      />
                    </Field>
                    <Field label="Requested scopes (comma separated)">
                      <input
                        value={c.scopes.join(",")}
                        onChange={(e) =>
                          config(
                            "scopes",
                            e.target.value.split(",").filter(Boolean),
                          )
                        }
                      />
                    </Field>
                    <p className="nx-boundary">
                      Scope configuration does not grant runtime access.
                      Existing tool grants, role checks and policy gates remain
                      separate.
                    </p>
                  </>
                )}
                {draft.kind === "guardrail" && (
                  <>
                    <Field label="Blocked terms (comma separated)">
                      <input
                        value={c.blocked_terms.join(",")}
                        onChange={(e) =>
                          config(
                            "blocked_terms",
                            e.target.value.split(",").filter(Boolean),
                          )
                        }
                      />
                    </Field>
                    <Field label="Matching behavior">
                      <select
                        value={c.mode}
                        onChange={(e) => config("mode", e.target.value)}
                      >
                        <option value="block">Block matching input</option>
                        <option value="redact">Show redacted output</option>
                      </select>
                    </Field>
                    <label className="nx-checkbox">
                      <input
                        type="checkbox"
                        checked={c.detect_email}
                        onChange={(e) =>
                          config("detect_email", e.target.checked)
                        }
                      />{" "}
                      Detect email addresses
                    </label>
                    <label className="nx-checkbox">
                      <input
                        type="checkbox"
                        checked={c.detect_override}
                        onChange={(e) =>
                          config("detect_override", e.target.checked)
                        }
                      />{" "}
                      Detect known instruction-override phrases
                    </label>
                    <p className="nx-boundary">
                      Local deterministic testing only. These rules are not
                      automatically applied to external model traffic.
                    </p>
                  </>
                )}
                {draft.kind === "benchmark" && (
                  <>
                    <Field label="Top K source chunks">
                      <input
                        type="number"
                        min={1}
                        max={5}
                        value={c.top_k}
                        onChange={(e) =>
                          config("top_k", Number(e.target.value))
                        }
                      />
                    </Field>
                    {c.cases.map((item: R, i: number) => (
                      <div className="nx-case-edit" key={i}>
                        <Field label={"Case " + (i + 1) + " query"}>
                          <input
                            required
                            value={item.query}
                            onChange={(e) =>
                              config(
                                "cases",
                                c.cases.map((v: R, j: number) =>
                                  j === i ? { ...v, query: e.target.value } : v,
                                ),
                              )
                            }
                          />
                        </Field>
                        <Field label="Expected document title">
                          <input
                            required
                            value={item.expected_title}
                            onChange={(e) =>
                              config(
                                "cases",
                                c.cases.map((v: R, j: number) =>
                                  j === i
                                    ? { ...v, expected_title: e.target.value }
                                    : v,
                                ),
                              )
                            }
                          />
                        </Field>
                        <button
                          type="button"
                          className="nx-icon"
                          disabled={c.cases.length === 1}
                          aria-label={"Remove benchmark case " + (i + 1)}
                          onClick={() =>
                            config(
                              "cases",
                              c.cases.filter((_: R, j: number) => i !== j),
                            )
                          }
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="btn btn-outline"
                      disabled={c.cases.length >= 30}
                      onClick={() =>
                        config("cases", [
                          ...c.cases,
                          { query: "", expected_title: "" },
                        ])
                      }
                    >
                      <Plus size={15} /> Add case
                    </button>
                  </>
                )}
                {draft.kind === "budget" && (
                  <>
                    <Field label="Monthly planning limit (USD)">
                      <input
                        type="number"
                        min={0}
                        max={10000000}
                        step="0.01"
                        value={c.monthly_limit}
                        onChange={(e) =>
                          config("monthly_limit", Number(e.target.value))
                        }
                      />
                    </Field>
                    <div className="nx-two-fields">
                      <Field label="Input cost per million tokens (USD)">
                        <input
                          type="number"
                          min={0}
                          max={10000}
                          step="0.01"
                          value={c.input_per_million}
                          onChange={(e) =>
                            config("input_per_million", Number(e.target.value))
                          }
                        />
                      </Field>
                      <Field label="Output cost per million tokens (USD)">
                        <input
                          type="number"
                          min={0}
                          max={10000}
                          step="0.01"
                          value={c.output_per_million}
                          onChange={(e) =>
                            config("output_per_million", Number(e.target.value))
                          }
                        />
                      </Field>
                    </div>
                    <p className="nx-boundary">
                      Rates are user-supplied scenario assumptions. No provider
                      invoice data or atomic budget enforcement is connected.
                    </p>
                  </>
                )}
                {draft.kind === "release" && (
                  <>
                    <div className="nx-two-fields">
                      <Field label="Release target">
                        <select
                          value={c.target}
                          onChange={(e) => config("target", e.target.value)}
                        >
                          {["Local", "AWS", "Azure", "Kubernetes"].map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Artifact">
                        <input
                          required
                          value={c.artifact}
                          onChange={(e) => config("artifact", e.target.value)}
                        />
                      </Field>
                    </div>
                    <Field label="Rollback procedure">
                      <textarea
                        required
                        minLength={5}
                        maxLength={2000}
                        value={c.rollback}
                        onChange={(e) => config("rollback", e.target.value)}
                      />
                    </Field>
                    <Field label="Planned validation gates (one per line)">
                      <textarea
                        value={c.checks.join("\n")}
                        onChange={(e) =>
                          config(
                            "checks",
                            e.target.value.split("\n").filter(Boolean),
                          )
                        }
                      />
                    </Field>
                    <p className="nx-boundary">
                      A saved plan does not certify its checks or deploy the
                      application.
                    </p>
                  </>
                )}
              </fieldset>
              <div className="nx-editor-footer">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!canEdit || busy || draft.status === "archived"}
                >
                  <Check size={16} />{" "}
                  {draft.id ? "Save new revision" : "Save design"}
                </button>
                {draft.id && draft.status !== "archived" && (
                  <button
                    type="button"
                    className="btn btn-outline"
                    disabled={
                      !canEdit ||
                      busy ||
                      (draft.kind === "model" &&
                        !me.permissions?.includes("manage"))
                    }
                    onClick={async () => {
                      const r = await task(
                        () =>
                          api(
                            "/v1/workbench/" + draft.id + "/validate",
                            "POST",
                            { expected_version: draft.version },
                          ),
                        "Saved configuration schema checked. External connectivity was not tested.",
                      );
                      if (r) setDraft(r);
                    }}
                  >
                    <ShieldCheck size={16} /> Check saved config
                  </button>
                )}
                {draft.id && draft.status !== "archived" && (
                  <button
                    type="button"
                    className="nx-link nx-danger"
                    disabled={!canEdit || busy}
                    onClick={async () => {
                      const r = await task(
                        () =>
                          api(
                            "/v1/workbench/" + draft.id + "/archive",
                            "POST",
                            { expected_version: draft.version },
                          ),
                        "Asset archived. Version history and runs preserved.",
                      );
                      if (r) setDraft(r);
                    }}
                  >
                    Archive saved asset
                  </button>
                )}
              </div>
            </form>
          )}
          {tab === "test" && (
            <div className="nx-testbench">
              {!draft.id ? (
                <div className="nx-empty compact">
                  <h3>Save this design first</h3>
                  <p>
                    Tests execute the saved version so results remain
                    reproducible.
                  </p>
                  <button
                    className="btn btn-outline"
                    onClick={() => setTab("configure")}
                  >
                    Back to configuration
                  </button>
                </div>
              ) : (
                <>
                  <p className="nx-boundary">
                    Runs use saved version {draft.version}. Save configuration
                    edits before testing. No external endpoint or language model
                    is called.
                  </p>
                  {["prompt", "knowledge", "guardrail", "workflow"].includes(
                    draft.kind,
                  ) && (
                    <Field
                      label={
                        draft.kind === "knowledge"
                          ? "Retrieval query"
                          : "Test input / question"
                      }
                    >
                      <textarea
                        dir="auto"
                        maxLength={2000}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </Field>
                  )}
                  {draft.kind === "prompt" && (
                    <Field label="Additional template variables (JSON object)">
                      <textarea
                        className="nx-code-input"
                        value={variables}
                        onChange={(e) => setVariables(e.target.value)}
                      />
                    </Field>
                  )}
                  {draft.kind === "workflow" && (
                    <Field label="Synthetic purchase amount for policy preview (USD)">
                      <input
                        type="number"
                        min={0.01}
                        max={99999999}
                        step=".01"
                        value={amount}
                        onChange={(e) => setAmount(Number(e.target.value))}
                      />
                    </Field>
                  )}
                  {draft.kind === "budget" && (
                    <div className="nx-two-fields">
                      <Field label="Estimated input tokens">
                        <input
                          type="number"
                          min={0}
                          max={1000000000}
                          value={inputTokens}
                          onChange={(e) =>
                            setInputTokens(Number(e.target.value))
                          }
                        />
                      </Field>
                      <Field label="Estimated output tokens">
                        <input
                          type="number"
                          min={0}
                          max={1000000000}
                          value={outputTokens}
                          onChange={(e) =>
                            setOutputTokens(Number(e.target.value))
                          }
                        />
                      </Field>
                    </div>
                  )}
                  <button
                    className="btn btn-primary"
                    disabled={!canEdit || busy || draft.status === "archived"}
                    onClick={() => run(draft)}
                  >
                    <Play size={16} />
                    {busy
                      ? "Running…"
                      : draft.kind === "workflow"
                        ? "Run dry preview"
                        : draft.kind === "knowledge"
                          ? "Retrieve cited evidence"
                          : draft.kind === "benchmark"
                            ? "Run retrieval benchmark"
                            : draft.kind === "budget"
                              ? "Calculate scenario"
                              : "Run saved-version test"}
                  </button>
                  {result && <Result run={result} />}
                </>
              )}
            </div>
          )}
          {tab === "history" && (
            <div className="nx-history">
              {!history.length ? (
                <p>No saved revisions yet.</p>
              ) : (
                history.map((h) => (
                  <details key={h.id}>
                    <summary>
                      <History size={17} />
                      <strong>Version {h.version}</strong>
                      <Tag value={h.snapshot.status} />
                      <span>{when(h.created)}</span>
                    </summary>
                    <pre className="nx-code">
                      {JSON.stringify(h.snapshot, null, 2)}
                    </pre>
                    <button
                      className="nx-link"
                      onClick={() =>
                        exportJson(draft.name + "_v" + h.version, h.snapshot)
                      }
                    >
                      <Download size={14} /> Download revision
                    </button>
                  </details>
                ))
              )}
            </div>
          )}
        </Drawer>
      )}
      {trace && (
        <Drawer
          title={"Run evidence · " + ref(trace.id)}
          close={() => setTrace(null)}
        >
          <div className="nx-testbench">
            <Result run={trace} />
            <details className="nx-raw">
              <summary>Inspect full run record</summary>
              <pre className="nx-code">{JSON.stringify(trace, null, 2)}</pre>
            </details>
          </div>
        </Drawer>
      )}
    </div>
  );
}
