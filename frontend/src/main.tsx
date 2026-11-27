import { SecretInputStatus } from "./SecretInputStatus";
import { AuditRetention } from "./AuditRetention";
import { SignedAuditEvidence } from "./SignedAuditEvidence";
import { DurableExecution, DocumentLibrary } from "./LiveWorkspaces";
import { PlatformScope } from "./PlatformScope";
import { ProductBoundary } from "./ProductBoundary";
import { requestNavigationGuard } from "./navigationGuard";
import React, { useEffect, useState, useRef, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Compass,
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Blocks,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Code2,
  Copy,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  Fingerprint,
  FlaskConical,
  Gauge,
  GitBranch,
  Globe2,
  KeyRound,
  Layers3,
  LayoutDashboard,
  ListFilter,
  LockKeyhole,
  LogOut,
  Menu,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Shield,
  ShieldCheck,
  ShieldX,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  TriangleAlert,
  Users,
  Wallet,
  Waypoints,
  X,
  Zap,
} from "lucide-react";
import { api, setCsrf } from "./api";
import { sessionContext } from "./sessionContext";
import { EnvironmentSwitcher } from "./EnvironmentSwitcher";
import { recoveryPanelKey } from "./recoveryContext";
import { FlagshipHub } from "./FlagshipHub";
import { RuntimeConsole } from "./RuntimeConsole";
import { ProductionBoard } from "./ProductionBoard";
import { ImplementationStudio } from "./ImplementationStudio";

import { submitIntent, submissionMessage, IntentKeyRegistry } from "./runIntent";
import "./styles.css";
import "./neon.css";
import "./flagship.css";
import "./runtime.css";
import "./readability.css";
import "./clarity.css";
const RuntimeOperations = React.lazy(() =>
  import("./RuntimeOperations").then((m) => ({ default: m.RuntimeOperations })),
);
const ProductExperience = React.lazy(() =>
  import("./ProductExperienceView").then((m) => ({ default: m.ProductExperience })),
);
import "./studio.css";
try {
  document.documentElement.dataset.appearance =
    localStorage.getItem("nexus.appearance") || "light";
} catch {
  document.documentElement.dataset.appearance = "light";
}
const HybridRetrieval = lazy(() =>
  import("./EnterpriseRuntime").then((m) => ({ default: m.HybridRetrieval })),
);
const MemberAdmin = lazy(() =>
  import("./EnterpriseRuntime").then((m) => ({ default: m.MemberAdmin })),
);
const EnvironmentSetup = lazy(() =>
  import("./EnvironmentSetupPanel").then((m) => ({ default: m.EnvironmentSetup })),
);
type Row = Record<string, any>;
const nav = [
  ["overview", "AI command center", LayoutDashboard],
  ["product", "Product UI walkthrough", Compass],
  ["scope", "Platform function map", Layers3],
  ["studio", "Enterprise design studio", Layers3],
  ["agents", "Agent registry", Blocks],
  ["agentRuns", "Agent execution", Play],
  ["workflows", "Workflow Studio", GitBranch],
  ["prompts", "Prompt registry", Code2],
  ["documents", "Document library", BookOpen],
  ["knowledge", "Knowledge & RAG", Database],
  ["models", "Model gateway", Layers3],
  ["connectors", "Integration catalog", Waypoints],
  ["tools", "Tools & grants", KeyRound],
  ["guardrails", "Safety workbench", ShieldCheck],
  ["policies", "Policy engine", Shield],
  ["approvals", "Human approvals", FileCheck2],
  ["executions", "Execution ledger", Activity],
  ["observability", "Traces & observability", Activity],
  ["evaluationlab", "Evaluation lab", FlaskConical],
  ["evaluations", "Policy regression", CheckCheck],
  ["usage", "AI FinOps", Wallet],
  ["incidents", "Security center", ShieldX],
  ["audit", "Audit explorer", Fingerprint],
  ["operations", "Release readiness", Gauge],
  ["settings", "Workspace settings", Settings2],
] as const;
const friendly = (s: string) =>
  s?.replaceAll("_", " ").replace(/\b\w/g, (x) => x.toUpperCase());
const short = (s: string) => s?.slice(0, 8).toUpperCase();
const date = (n: number) =>
  new Date(n * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value}>
      <i />
      {friendly(value)}
    </span>
  );
}
function Logo({ light = false }: { light?: boolean }) {
  return (
    <div className={"brand " + (light ? "light" : "")}>
      <span className="brand-mark">
        <Layers3 size={23} />
      </span>
      <span>
        NEXUS<small>AI CONTROL</small>
      </span>
    </div>
  );
}
function Empty({
  icon: Icon = Layers3,
  title,
  body,
  action,
}: {
  icon?: any;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon size={27} />
      </span>
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    ref.current?.showModal();
    ref.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    return () => {
      ref.current?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={"dialog " + (wide ? "wide" : "")}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-labelledby="dialog-title"
    >
      <div className="dialog-head">
        <div>
          <span className="eyebrow">NEXUS WORKSPACE</span>
          <h2 id="dialog-title">{title}</h2>
        </div>
        <button
          className="icon-btn"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function StatusMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="inline-note">
      <ShieldCheck size={17} />
      <span>{children}</span>
    </div>
  );
}
function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const [config, setConfig] = useState<Row>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  useEffect(() => {
    api("/auth/config")
      .then(setConfig)
      .catch(() =>
        setError("The API is unavailable. Start the backend and try again."),
      );
  }, []);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const d = new FormData(e.currentTarget);
    try {
      const r = await api("/auth/local/login", "POST", {
        email: d.get("email"),
        password: d.get("password"),
      });
      setCsrf(r.csrf);
      onSignedIn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="signin">
      <section className="signin-story">
        <div className="signin-grid" />
        <Logo light />
        <div className="story-content">
          <div className="story-kicker">
            <span /> GOVERNANCE · SECURITY · OPERATIONS
          </div>
          <div className="project-title-tag">ENTERPRISE AI ENGINEERING</div>
          <h1>
            Enterprise Agentic AI
            <br />
            <em>Governance, Security</em>
            <br />
            &amp; Operations Platform
            <span className="project-shortname">(NEXUS AI Control)</span>
          </h1>
          <p className="story-description">
            Move from autonomous intent to accountable execution.
            <br />
            One place to govern agents, secure actions, and verify outcomes.
          </p>
          <img
            className="governance-visual"
            src="/nexus-agent-neon.png"
            alt="A luminous AI assistant above a holographic platform in a blue server room"
          />
          <div className="story-capabilities">
            <span>
              <Fingerprint size={15} /> Identity
            </span>
            <span>
              <ShieldCheck size={15} /> Governance
            </span>
            <span>
              <Activity size={15} /> Operations
            </span>
          </div>
        </div>
        <div className="story-footer">
          <span>
            <LockKeyhole size={14} /> Governed by design
          </span>
          <span>NEXUS / 01</span>
        </div>
      </section>
      <main className="signin-form">
        <div className="signin-top">
          <span>Enterprise agent governance</span>
          <span className="pill neutral">
            {config.mode === "local"
              ? "LOCAL WORKSPACE"
              : "ORGANIZATION ACCESS"}
          </span>
        </div>
        <div className="signin-box">
          <div className="welcome-symbol">
            <Layers3 size={25} />
          </div>
          <span className="eyebrow">WELCOME TO YOUR CONTROL PLANE</span>
          <h2>
            Sign in to <em>NEXUS.</em>
          </h2>
          <p className="muted">
            Secure access. Clear oversight. Confident operations.
          </p>
          {config.oidc && (
            <>
              <a className="btn btn-outline full" href="/auth/oidc/start">
                <Shield size={17} />
                Continue with organization SSO
                <ArrowUpRight size={16} />
              </a>
              <div className="divider">or sign in to the local workspace</div>
            </>
          )}
          {config.local_login && (
            <form onSubmit={submit}>
              <Field label="Work email">
                <input
                  type="email"
                  name="email"
                  placeholder="you@company.com"
                  required
                  autoComplete="username"
                />
              </Field>
              <Field label="Password">
                <div className="password-input">
                  <input
                    type={show ? "text" : "password"}
                    name="password"
                    placeholder="Enter your workspace password"
                    required
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShow(!show)}
                    aria-label={show ? "Hide password" : "Show password"}
                  >
                    {show ? "Hide" : "Show"}
                  </button>
                </div>
              </Field>
              <div className="form-hint">
                <LockKeyhole size={13} />
                Your session stays on this device.
              </div>
              {error && (
                <div role="alert" className="error">
                  <TriangleAlert size={16} />
                  {error}
                </div>
              )}
              <button className="btn btn-primary full" disabled={busy}>
                {busy ? "Signing in…" : "Sign in to workspace"}
                <ArrowRight size={17} />
              </button>
            </form>
          )}
          {!config.local_login && !config.oidc && (
            <div className="error">
              Configure your identity provider to enable sign-in.
            </div>
          )}
          <div className="signin-access">
            <KeyRound size={17} />
            <div>
              <strong>Need workspace access?</strong>
              <p>Ask your administrator to provision your account.</p>
            </div>
          </div>
          <div className="local-explainer">
            <span className="status-dot" />
            Synthetic local workspace. Use the accounts and generated password
            from the setup terminal.
          </div>
        </div>
        <div className="signin-bottom">
          <span>© {new Date().getFullYear()} NEXUS AI Control</span>
          <span>
            <ShieldCheck size={14} /> Secure session access
          </span>
        </div>
      </main>
      <div className="signin-feature-rail" aria-label="Platform capabilities">
        {[
          [Layers3, "Architecture"],
          [Waypoints, "Tools & grants"],
          [GitBranch, "Policy engine"],
          [Users, "Human review"],
          [Fingerprint, "Audit evidence"],
          [ShieldCheck, "Security"],
          [Gauge, "Operations"],
        ].map(([Icon, label], i) => {
          const TileIcon = Icon as any;
          return (
            <div className={"neon-tile tone-" + i} key={String(label)}>
              <TileIcon size={28} strokeWidth={1.7} />
              <strong>{String(label)}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}
function App({ intentKeys }: { intentKeys: IntentKeyRegistry }) {
  const [largeText, setLargeText] = useState(() => {
    try {
      return localStorage.getItem("nexus.largeText") === "1";
    } catch {
      return false;
    }
  });
  const [appearance, setAppearance] = useState(
    () => document.documentElement.dataset.appearance || "light",
  );
  useEffect(() => {
    document.documentElement.dataset.appearance = appearance;
    try {
      localStorage.setItem("nexus.appearance", appearance);
    } catch {}
  }, [appearance]);
  useEffect(() => {
    document.documentElement.dataset.readability = largeText
      ? "large"
      : "comfortable";
    try {
      localStorage.setItem("nexus.largeText", largeText ? "1" : "0");
    } catch {}
  }, [largeText]);
  const [me, setMe] = useState<Row | null>(null),
    [loading, setLoading] = useState(true),
    [page, setPage] = useState(location.hash.slice(1) || "overview");
  const [data, setData] = useState<Row>({
    agents: [],
    tools: [],
    policies: [],
    approvals: [],
    actions: [],
    audit: [],
    evaluations: [],
    incidents: [],
    overview: {},
    settings: {},
    operations: {},
  });
  const [query, setQuery] = useState(""),
    [error, setError] = useState(""),
    [toast, setToast] = useState(""),
    [busy, setBusy] = useState(false),
    [mobile, setMobile] = useState(false),
    [filter, setFilter] = useState("all");
  const [operationsTab, setOperationsTab] = useState("readiness");
  const [modal, setModal] = useState<Row | null>(null);
  const [runToolId, setRunToolId] = useState("");
  const [quickOpen, setQuickOpen] = useState(false),
    [quickQuery, setQuickQuery] = useState("");
  const [auditRows, setAuditRows] = useState<Row[]>([]),
    [auditCursor, setAuditCursor] = useState<string | null>(null),
    [auditLoading, setAuditLoading] = useState(false),
    [auditError, setAuditError] = useState("");
  const auditRequest = useRef(0);
  const [auditRevision, setAuditRevision] = useState(0);
  function openRun() {
    setRunToolId("");
    setModal({ type: "run" });
  }
  const can = (p: string) => me?.permissions?.includes(p);
  async function session() {
    try {
      const r = await api("/v1/me");
      recoveryPanelKey(r);
      sessionContext.adopt(r);
      setMe(r);
      setCsrf(r.csrf);
    } catch (e) {
      if ((e as {code?:string}).code === "STALE_CONTEXT_RESPONSE") return;
      sessionContext.clear();
      setCsrf("");
      setMe(null);
    } finally {
      setLoading(false);
    }
  }
  async function refresh() {
    if (!me) return;
    try {
      const paths = [
        "overview",
        "agents",
        "tools",
        "policies",
        "approvals",
        "actions",
        "audit-events",
        "evaluations",
        "incidents",
        "settings",
        "operations",
      ];
      const results = await Promise.all(paths.map((p) => api("/v1/" + p)));
      setData({
        overview: results[0],
        agents: results[1],
        tools: results[2],
        policies: results[3],
        approvals: results[4],
        actions: results[5],
        audit: results[6],
        evaluations: results[7],
        incidents: results[8],
        settings: results[9],
        operations: results[10],
      });
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    session();
    const discover = () => { if (document.visibilityState === "visible") session(); };
    window.addEventListener("focus", discover);
    document.addEventListener("visibilitychange", discover);
    return () => { window.removeEventListener("focus",discover); document.removeEventListener("visibilitychange",discover); };
  }, []);
  useEffect(() => {
    if (me) {
      refresh();
      const id = setInterval(refresh, 10000);
      return () => clearInterval(id);
    }
  }, [me]);
  useEffect(() => {
    const fn = (event: HashChangeEvent) => {
      const target = event.newURL;
      const apply = () => {
        const next = new URL(target);
        if (location.href !== target)
          window.history.pushState(null, "", target);
        setPage(next.hash.slice(1) || "overview");
        setQuery("");
        setFilter("all");
        setMobile(false);
        window.scrollTo(0, 0);
      };
      if (requestNavigationGuard(apply)) {
        window.history.replaceState(null, "", event.oldURL);
        return;
      }
      apply();
    };
    window.addEventListener("hashchange", fn);
    return () => window.removeEventListener("hashchange", fn);
  }, []);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(""), 5500);
      return () => clearTimeout(t);
    }
  }, [toast]);
  useEffect(() => {
    const keyboard = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setQuickOpen((v) => !v);
        setQuickQuery("");
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, []);
  useEffect(() => {
    if (!me || page !== "audit") return;
    let cancelled = false;
    auditRequest.current += 1;
    setAuditRows([]);
    setAuditCursor(null);
    setAuditError("");
    setAuditLoading(true);
    const timer = setTimeout(() => {
      api("/v1/audit-page?q=" + encodeURIComponent(query) + "&limit=25")
        .then((result) => {
          if (!cancelled) {
            setAuditRows(result.items);
            setAuditCursor(result.next_cursor);
          }
        })
        .catch((e) => {
          if (!cancelled) setAuditError(e.message);
        })
        .finally(() => {
          if (!cancelled) setAuditLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [me, page, query, auditRevision]);
  async function moreAudit() {
    if (!auditCursor || auditLoading) return;
    setAuditLoading(true);
    setAuditError("");
    const revision = auditRequest.current;
    try {
      const result = await api(
        "/v1/audit-page?q=" +
          encodeURIComponent(query) +
          "&limit=25&cursor=" +
          encodeURIComponent(auditCursor),
      );
      if (revision === auditRequest.current) {
        setAuditRows((rows) => [...rows, ...result.items]);
        setAuditCursor(result.next_cursor);
      }
    } catch (e) {
      if (revision === auditRequest.current)
        setAuditError((e as Error).message);
    } finally {
      if (revision === auditRequest.current) setAuditLoading(false);
    }
  }
  const go = (p: string) => {
    location.hash = p;
  };
  async function perform(
    fn: () => Promise<any>,
    message: string | ((result: any) => string),
    close = true,
  ) {
    setBusy(true);
    try {
      const result = await fn();
      if (close) setModal(null);
      setToast(typeof message === "function" ? message(result) : message);
      await refresh();
      return result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  function matching(rows: Row[]) {
    return rows.filter((r) =>
      JSON.stringify(r).toLowerCase().includes(query.toLowerCase()),
    );
  }
  async function detail(a: Row) {
    try {
      setModal({ type: "execution", row: await api("/v1/actions/" + a.id) });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (loading)
    return (
      <div className="loading-screen">
        <Logo />
        <span className="spinner" />
        Opening your workspace…
      </div>
    );
  if (!me) return <Login onSignedIn={session} />;
  const o = data.overview,
    pending = data.approvals.filter((a: Row) => a.status === "pending").length,
    policy = data.policies.find((p: Row) => p.active);
  const title = nav.find((n) => n[0] === page)?.[1] || "Overview";
  const descriptions: Row = {
    product:
      "Review the enterprise UI end to end, then implement and accept each phase.",
    overview: "Your agents, actions and decisions. One connected view.",
    studio:
      "Prepare every enterprise interface, then activate each backend capability step by step.",
    scope:
      "A complete, searchable UI scope for long-term enterprise platform development.",
    agents: "Know what is running, who owns it and what it can access.",
    agentRuns:
      "Execute persisted workflows with independent review and recoverable checkpoints.",
    documents:
      "Ingest authorized text evidence and retrieve versioned, access-filtered citations.",
    workflows: "Version an agent pipeline and inspect each control gate.",
    prompts:
      "Maintain instruction contracts, variables and deterministic checks.",
    knowledge: "Find authorized source evidence with local hybrid retrieval.",
    models: "Define provider routes and inspect their integration boundaries.",
    connectors:
      "Design external interface contracts and least-privilege scopes.",
    guardrails: "Inspect input rules and redaction before orchestration.",
    observability:
      "Trace recorded workbench runs and business action evidence.",
    evaluationlab: "Measure retrieval with repeatable, versioned test cases.",
    tools: "A deliberate boundary between intelligence and action.",
    policies: "Clear rules. Deterministic decisions. Versioned evidence.",
    approvals: "Human judgement, exactly where it matters.",
    executions: "Follow every action from intent to verified outcome.",
    audit: "The evidence behind every decision.",
    usage: "Understand usage before making cost claims.",
    evaluations: "Prove policy behaviour with repeatable checks.",
    incidents: "Contain risk. Preserve evidence. Recover deliberately.",
    settings: "The people and boundaries of your workspace.",
    operations:
      "See what is configured, what needs attention, and what comes next.",
  };
  const primary =
    page === "agents" ? (
      <button
        className="btn btn-primary"
        onClick={() => setModal({ type: "agent" })}
      >
        <Plus size={16} />
        Register agent
      </button>
    ) : page === "policies" ? (
      <button
        className="btn btn-primary"
        onClick={() => setModal({ type: "policy" })}
      >
        <SlidersHorizontal size={16} />
        Update guardrails
      </button>
    ) : page === "evaluations" ? (
      <button
        className="btn btn-primary"
        onClick={() =>
          perform(
            () => api("/v1/evaluations", "POST"),
            "Policy evaluation completed.",
          )
        }
        disabled={busy || !can("operate")}
      >
        <Play size={16} />
        Run evaluation
      </button>
    ) : (
      <button
        className="btn btn-primary"
        onClick={openRun}
        disabled={!can("operate")}
      >
        <Play size={15} />
        Run governed action
      </button>
    );
  const tableActions = (rows: Row[]) =>
    rows.length ? (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Action / reference</th>
              <th>Agent</th>
              <th>Policy decision</th>
              <th>Outcome</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {matching(rows).map((a: Row) => (
              <tr
                key={a.id}
                onClick={() => detail(a)}
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && detail(a)}
              >
                <td>
                  <div className="table-title">
                    <span
                      className={
                        "small-icon " +
                        (a.envelope.action === "supplier:read"
                          ? "teal"
                          : "blue")
                      }
                    >
                      <GitBranch size={16} />
                    </span>
                    <div>
                      <strong>
                        {a.envelope.action === "supplier:read"
                          ? "Supplier lookup"
                          : "Purchase request"}
                      </strong>
                      <small>ACT-{short(a.id)}</small>
                    </div>
                  </div>
                </td>
                <td>
                  {data.agents.find((v: Row) => v.id === a.agent_id)?.name ||
                    short(a.agent_id)}
                </td>
                <td>
                  <Badge value={a.decision} />
                </td>
                <td>
                  <Badge value={a.status} />
                </td>
                <td className="muted">{date(a.created)}</td>
                <td>
                  <ChevronRight size={16} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <Empty
        icon={Activity}
        title="Your next action starts here"
        body="Run a synthetic supplier lookup or purchase request to see the complete governance path."
        action={
          <button
            className="btn btn-outline"
            onClick={openRun}
            disabled={!can("operate")}
          >
            <Play size={15} />
            Run first action
          </button>
        }
      />
    );
  function formSubmit(
    e: React.FormEvent<HTMLFormElement>,
    callback: (d: FormData) => Promise<any>,
    message: string,
  ) {
    e.preventDefault();
    const d = new FormData(e.currentTarget);
    perform(() => callback(d), message);
  }
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#workspace-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("workspace-content")?.focus();
        }}
      >
        Skip to workspace content
      </a>
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <Logo light />
        <div className="workspace-picker">
          <span className="workspace-symbol">N</span>
          <div>
            <strong>{me.workspace}</strong>
            <small>Governance workspace</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <span className="nav-label">BUILD & ORCHESTRATE</span>
        <nav>
          {nav.map(([key, label, Icon], i) => (
            <React.Fragment key={key}>
              {key === "tools" && (
                <span className="nav-label secondary">GOVERN & PROTECT</span>
              )}
              {key === "executions" && (
                <span className="nav-label secondary">OPERATE & ASSURE</span>
              )}
              <a
                href={"#" + key}
                className={page === key ? "active" : ""}
                aria-current={page === key ? "page" : undefined}
              >
                <Icon size={18} />
                <span>{label}</span>
                {key === "approvals" && pending > 0 && (
                  <b className="nav-count">{pending}</b>
                )}
              </a>
            </React.Fragment>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="protected">
            <ShieldCheck size={19} />
            <div>
              <strong>Governance is active</strong>
              <small>
                {data.settings.policy_engine === "opa"
                  ? "OPA enforcement"
                  : "Reference policy engine"}
              </small>
            </div>
            <span className="status-dot" />
          </div>
          <div className="profile">
            <span className="avatar">
              {me.user.name
                .split(" ")
                .map((s: string) => s[0])
                .join("")}
            </span>
            <div>
              <strong>{me.user.name}</strong>
              <small>{friendly(me.user.role)}</small>
            </div>
            <button
              aria-label="Sign out"
              title="Sign out"
              onClick={() => {
                const leave = () =>
                  perform(async () => {
                    await api("/auth/logout", "POST");
                    setCsrf("");
                    sessionContext.clear();
                    setMe(null);
                  }, "Signed out.");
                if (!requestNavigationGuard(leave)) leave();
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      {mobile && (
        <button
          className="mobile-overlay"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu icon-btn"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <button
              className="text-size-control"
              aria-pressed={largeText}
              onClick={() => setLargeText((v) => !v)}
              title="Toggle larger dashboard text"
            >
              Aa <span>{largeText ? "Large text" : "Text size"}</span>
            </button>
            <button
              className="quick-search"
              onClick={() => {
                setQuickOpen(true);
                setQuickQuery("");
              }}
              aria-label="Search workspace navigation"
            >
              <Search size={16} />
              <span>Jump to a view</span>
              <kbd>⌘ / Ctrl K</kbd>
            </button>
            <EnvironmentSwitcher me={me} />
            <button
              className="text-size-control"
              onClick={() =>
                setAppearance((v) => (v === "light" ? "dark" : "light"))
              }
              aria-label="Switch workspace appearance"
            >
              {appearance === "light" ? "Light theme" : "Dark theme"}
            </button>
            <span className="synthetic">
              {me.synthetic ? "SYNTHETIC DATA" : "HTTP BUSINESS"}
            </span>
            <button
              className="icon-btn notification"
              aria-label={`${pending} pending approvals`}
              onClick={() => go("approvals")}
            >
              <Bell size={19} />
              {pending > 0 && <i />}
            </button>
            <span className="avatar small">
              {me.user.name
                .split(" ")
                .map((s: string) => s[0])
                .join("")}
            </span>
          </div>
        </header>
        <main className="content" id="workspace-content" tabIndex={-1}>
          {!me.synthetic && (
            <div className="http-mode-banner" role="status">
              <strong>HTTP business adapter enabled.</strong> Approved actions
              may create records in the configured customer system. Review the
              destination before submission.
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "overview"
                  ? "YOUR GOVERNANCE WORKSPACE"
                  : "NEXUS / CONTROL PLANE"}
              </div>
              <h1>{page === "overview" ? "AI command center" : title}</h1>
              <p>{descriptions[page]}</p>
            </div>
            <div className="heading-actions">
              <button
                className="btn btn-outline refresh"
                onClick={() => {
                  refresh();
                  setAuditRevision((v) => v + 1);
                }}
                aria-label="Refresh workspace"
              >
                <RefreshCw size={15} />
              </button>
              {![
                "studio",
                "scope",
                "product",
                "agentRuns",
                "documents",
              ].includes(page) &&
                ((page === "agents" && can("manage")) ||
                  (page === "policies" && can("policy")) ||
                  !["agents", "policies"].includes(page)) &&
                primary}
            </div>
          </div>
          {error && (
            <div className="error global-error" role="alert">
              <TriangleAlert size={17} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {page === "agentRuns" && (
            <DurableExecution key={recoveryPanelKey(me)} me={me} data={data} onNavigate={go} />
          )}
          {page === "documents" && <DocumentLibrary key={recoveryPanelKey(me)} me={me} />}
          {page === "product" && (
            <React.Suspense
              fallback={<p role="status">Loading product UI walkthrough…</p>}
            >
              <ProductBoundary onExit={() => go("overview")}>
                <ProductExperience
                  me={me}
                  onNavigate={go}
                  onDesign={(module, feature) => {
                    const url = new URL(location.href);
                    url.searchParams.set("design", module);
                    url.searchParams.set("feature", feature);
                    history.replaceState(null, "", url);
                    go("studio");
                  }}
                />
              </ProductBoundary>
            </React.Suspense>
          )}
          {page === "scope" && (
            <PlatformScope
              onOpen={(module, feature) => {
                const url = new URL(location.href);
                url.searchParams.set("design", module);
                url.searchParams.set("feature", feature);
                history.replaceState(null, "", url);
                go("studio");
              }}
            />
          )}
          {page === "studio" && (
            <ImplementationStudio me={me} onNavigate={go} />
          )}
          {page === "operations" && (
            <div
              className="operations-tabs"
              role="tablist"
              aria-label="Release readiness views"
              onKeyDown={(e) => {
                const tabs = Array.from(
                  e.currentTarget.querySelectorAll<HTMLButtonElement>(
                    '[role="tab"]',
                  ),
                );
                const index = tabs.indexOf(
                  document.activeElement as HTMLButtonElement,
                );
                if (
                  ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)
                ) {
                  e.preventDefault();
                  const next =
                    e.key === "Home"
                      ? 0
                      : e.key === "End"
                        ? tabs.length - 1
                        : (index +
                            (e.key === "ArrowRight" ? 1 : -1) +
                            tabs.length) %
                          tabs.length;
                  tabs[next].click();
                  tabs[next].focus();
                }
              }}
            >
              {[
                ["readiness", "Readiness board"],
                ["plans", "Release plans"],
                ["signals", "Runtime signals"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  id={"operations-tab-" + id}
                  role="tab"
                  aria-selected={operationsTab === id}
                  aria-controls={"operations-panel-" + id}
                  tabIndex={operationsTab === id ? 0 : -1}
                  onClick={() => setOperationsTab(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          {page === "operations" && operationsTab === "readiness" && (
            <div
              role="tabpanel"
              id="operations-panel-readiness"
              aria-labelledby="operations-tab-readiness"
            >
              <ProductionBoard
                me={me}
                onNavigate={go}
                onDesign={(id) => {
                  const url = new URL(location.href);
                  url.searchParams.set("design", id);
                  history.replaceState(null, "", url);
                  go("studio");
                }}
              />
            </div>
          )}
          {[
            "overview",
            "workflows",
            "prompts",
            "models",
            "connectors",
            "guardrails",
            "evaluationlab",
            "observability",
            "usage",
            "operations",
          ].includes(page) &&
            (page !== "operations" || operationsTab === "plans") && (
              <div
                {...(page === "operations"
                  ? {
                      role: "tabpanel",
                      id: "operations-panel-plans",
                      "aria-labelledby": "operations-tab-plans",
                    }
                  : {})}
              >
                <FlagshipHub
                  key={page}
                  page={page}
                  legacy={data}
                  me={me}
                  onNavigate={go}
                  onRun={openRun}
                />
              </div>
            )}
          {page === "knowledge" && (
            <Suspense
              fallback={<p role="status">Loading evidence workspace…</p>}
            >
              <HybridRetrieval key={recoveryPanelKey(me)} me={me} />
            </Suspense>
          )}
          {page === "agents" && (
            <>
              <div className="toolbar">
                <div className="search">
                  <Search size={17} />
                  <input
                    aria-label="Search agents"
                    placeholder="Search agents, frameworks or owners…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <div className="segmented">
                  {["all", "active", "draft", "suspended"].map((x) => (
                    <button
                      key={x}
                      className={filter === x ? "selected" : ""}
                      onClick={() => setFilter(x)}
                    >
                      {friendly(x)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="agent-grid">
                {matching(data.agents)
                  .filter((a) => filter === "all" || a.status === filter)
                  .map((a: Row) => (
                    <article className="agent-card" key={a.id}>
                      <div className="agent-card-top">
                        <span className={"agent-art " + a.risk}>
                          <Blocks size={27} />
                        </span>
                        <Badge value={a.status} />
                      </div>
                      <h2>{a.name}</h2>
                      <p>Scoped workload identity · {me.environment}</p>
                      <div className="agent-tags">
                        <span>{a.framework}</span>
                        <span>v{a.version}</span>
                      </div>
                      <div className="agent-card-meta">
                        <span>
                          Risk tier <b>{friendly(a.risk)}</b>
                        </span>
                        <span>
                          Identity generation <b>{a.generation}</b>
                        </span>
                      </div>
                      <button
                        className="card-link"
                        onClick={async () =>
                          setModal({
                            type: "agent-detail",
                            row: await api("/v1/agents/" + a.id),
                          })
                        }
                      >
                        Open agent workspace
                        <ArrowUpRight size={17} />
                      </button>
                    </article>
                  ))}
              </div>
              {!matching(data.agents).length && (
                <Empty
                  title="No agents match"
                  body="Try another search or register an agent."
                />
              )}
            </>
          )}
          {page === "tools" && (
            <>
              <StatusMessage>
                {me.synthetic
                  ? "The local synthetic connector is configured. External"
                  : "An operator-configured HTTP contract adapter is enabled. Additional"}
                endpoints and business credentials are not exposed to the agent.
              </StatusMessage>
              <div className="tool-grid">
                {data.tools.map((t: Row) => (
                  <article className="panel tool-card" key={t.id}>
                    <div className="tool-heading">
                      <span className="tool-icon">
                        <Waypoints size={29} />
                      </span>
                      <Badge value={t.status} />
                    </div>
                    <h2>{t.name}</h2>
                    <p>
                      {t.kind === "supplier"
                        ? "Read synthetic supplier records through scoped access."
                        : "Create a synthetic purchase request under policy control."}
                    </p>
                    <dl>
                      <div>
                        <dt>Action scope</dt>
                        <dd>
                          <code>
                            {t.kind === "supplier"
                              ? "supplier:read"
                              : "purchase:create"}
                          </code>
                        </dd>
                      </div>
                      <div>
                        <dt>Schema version</dt>
                        <dd>{t.version}</dd>
                      </div>
                      <div>
                        <dt>Risk tier</dt>
                        <dd>
                          <Badge value={t.risk} />
                        </dd>
                      </div>
                      <div>
                        <dt>Connection</dt>
                        <dd>Local mock business system</dd>
                      </div>
                    </dl>
                    <button
                      className="btn btn-outline full"
                      onClick={() => setModal({ type: "schema", row: t })}
                    >
                      <Code2 size={16} />
                      Inspect typed schema
                      <ArrowUpRight size={15} />
                    </button>
                  </article>
                ))}
              </div>
            </>
          )}
          {page === "policies" && (
            <>
              <div className="policy-banner">
                <span className="policy-symbol">
                  <ShieldCheck size={34} />
                </span>
                <div>
                  <span className="eyebrow">ACTIVE BUSINESS GUARDRAILS</span>
                  <h2>Clear limits. Independent decisions.</h2>
                  <p>
                    Default deny, scoped tool access and version-bound approval.
                  </p>
                </div>
                <span className="badge active">Version {policy?.version}</span>
              </div>
              <div className="policy-cards">
                <div className="panel rule-card">
                  <span className="small-icon teal">
                    <Check size={20} />
                  </span>
                  <h3>Allow</h3>
                  <strong>
                    ≤ ${Number(policy?.threshold).toLocaleString()}
                  </strong>
                  <p>Within granted low-risk limits</p>
                </div>
                <div className="panel rule-card">
                  <span className="small-icon amber">
                    <Users size={20} />
                  </span>
                  <h3>Require approval</h3>
                  <strong>
                    Up to ${Number(policy?.maximum).toLocaleString()}
                  </strong>
                  <p>Above the threshold, independent review</p>
                </div>
                <div className="panel rule-card">
                  <span className="small-icon red">
                    <ShieldX size={20} />
                  </span>
                  <h3>Deny</h3>
                  <strong>
                    &gt; ${Number(policy?.maximum).toLocaleString()}
                  </strong>
                  <p>Above maximum, no connector call</p>
                </div>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Policy version history</h2>
                    <p>Historical decisions keep their original version</p>
                  </div>
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>Policy</th>
                      <th>Version</th>
                      <th>Threshold</th>
                      <th>Maximum</th>
                      <th>State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.policies.map((p: Row) => (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.name}</strong>
                        </td>
                        <td>v{p.version}</td>
                        <td>USD {p.threshold}</td>
                        <td>USD {p.maximum}</td>
                        <td>
                          <Badge value={p.active ? "active" : "superseded"} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}
          {page === "approvals" && (
            <>
              <div className="toolbar">
                <div className="segmented">
                  {["all", "pending", "approved", "rejected", "expired"].map(
                    (x) => (
                      <button
                        className={filter === x ? "selected" : ""}
                        key={x}
                        onClick={() => setFilter(x)}
                      >
                        {friendly(x)}
                      </button>
                    ),
                  )}
                </div>
                <span className="muted">
                  {pending} awaiting independent review
                </span>
              </div>
              <div className="approval-list">
                {data.approvals
                  .filter((a: Row) => filter === "all" || a.status === filter)
                  .map((a: Row) => (
                    <div className="panel approval-card" key={a.id}>
                      <span className="approval-art">
                        <FileCheck2 size={25} />
                      </span>
                      <div className="approval-summary">
                        <span className="eyebrow">
                          APR-{short(a.id)} · POLICY V{a.policy_version}
                        </span>
                        <h2>
                          Purchase request{" "}
                          <span>
                            USD{" "}
                            {Number(
                              a.action.envelope.arguments.amount,
                            ).toLocaleString()}
                          </span>
                        </h2>
                        <p>
                          {
                            data.agents.find(
                              (v: Row) => v.id === a.action.agent_id,
                            )?.name
                          }{" "}
                          · {a.action.envelope.arguments.supplier_id}
                        </p>
                        <div>
                          <Badge value={a.status} />
                          <span className="muted">
                            {a.status === "pending"
                              ? "Expires " + date(a.expires)
                              : "Reviewed request"}
                          </span>
                        </div>
                      </div>
                      <button
                        className="btn btn-outline"
                        onClick={() => setModal({ type: "approval", row: a })}
                      >
                        Review request
                        <ArrowRight size={15} />
                      </button>
                    </div>
                  ))}
              </div>
              {!data.approvals.filter(
                (a: Row) => filter === "all" || a.status === filter,
              ).length && (
                <section className="panel">
                  <Empty
                    icon={CheckCheck}
                    title="All clear in this queue"
                    body="Requests that require independent review will appear here."
                  />
                </section>
              )}
            </>
          )}
          {page === "executions" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Action ledger</h2>
                  <p>Queued, denied, reviewed and executed intents</p>
                </div>
                <div className="search compact">
                  <Search size={16} />
                  <input
                    aria-label="Search actions"
                    placeholder="Search actions…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
              </div>
              {tableActions(data.actions)}
            </section>
          )}
          {page === "audit" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Evidence explorer</h2>
                  <p>Tenant-scoped, correlated event records</p>
                </div>
                <button
                  className="btn btn-outline"
                  disabled={!can("export") || busy}
                  onClick={async () => {
                    const r = await perform(
                      () => api("/v1/audit-exports", "POST"),
                      "Evidence export created.",
                      false,
                    );
                    if (r) window.location.href = r.url;
                  }}
                >
                  <Download size={16} />
                  Export JSON
                </button>
              </div>
              <SignedAuditEvidence key={recoveryPanelKey(me)} me={me} />
              <AuditRetention key={recoveryPanelKey(me)} me={me} />
              <div className="audit-search search">
                <Search size={17} />
                <input
                  aria-label="Filter audit events"
                  maxLength={120}
                  placeholder="Filter by event, actor, action or trace…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Event</th>
                      <th>Actor</th>
                      <th>Action</th>
                      <th>Recorded</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {auditRows.map((e: Row) => (
                      <tr
                        key={e.id}
                        onClick={() => setModal({ type: "event", row: e })}
                      >
                        <td>
                          <div className="table-title">
                            <span className="small-icon blue">
                              <Fingerprint size={16} />
                            </span>
                            <strong>{e.event}</strong>
                          </div>
                        </td>
                        <td>
                          <code>
                            {e.actor === "worker"
                              ? "Execution worker"
                              : e.actor === "system"
                                ? "System"
                                : short(e.actor)}
                          </code>
                        </td>
                        <td>
                          {e.action_id
                            ? "ACT-" + short(e.action_id)
                            : "Workspace event"}
                        </td>
                        <td>{date(e.created)}</td>
                        <td>
                          <ChevronRight size={16} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="audit-pagination" aria-live="polite">
                <span>
                  {auditLoading
                    ? "Loading evidence…"
                    : `${auditRows.length} events loaded`}
                </span>
                {auditError && (
                  <span role="alert" className="audit-error">
                    {auditError}
                  </span>
                )}
                {auditCursor && (
                  <button
                    className="btn btn-outline"
                    onClick={moreAudit}
                    disabled={auditLoading}
                  >
                    Load more events <ArrowDown size={15} />
                  </button>
                )}
                {!auditLoading && !auditRows.length && !auditError && (
                  <span>No events match this search.</span>
                )}
              </div>
            </section>
          )}
          {page === "evaluations" && (
            <>
              <StatusMessage>
                These are actual runtime policy-boundary checks. They do not
                replace the backend security test suite or certify production
                readiness.
              </StatusMessage>
              {data.evaluations.length ? (
                data.evaluations.map((ev: Row) => (
                  <section className="panel evaluation-card" key={ev.id}>
                    <div className="panel-heading">
                      <div>
                        <span className="eyebrow">{ev.suite}</span>
                        <h2>
                          Policy evaluation{" "}
                          <span className="muted">EV-{short(ev.id)}</span>
                        </h2>
                        <p>{date(ev.created)}</p>
                      </div>
                      <div className="evaluation-score">
                        <strong>
                          {ev.passed}/{ev.total}
                        </strong>
                        <span>checks passed</span>
                      </div>
                    </div>
                    <table>
                      <thead>
                        <tr>
                          <th>Case</th>
                          <th>Expected</th>
                          <th>Observed</th>
                          <th>Result</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ev.cases.map((v: Row) => (
                          <tr key={v.name}>
                            <td>{friendly(v.name.replaceAll("-", " "))}</td>
                            <td>{friendly(v.expected)}</td>
                            <td>{friendly(v.actual)}</td>
                            <td>
                              <Badge value={v.passed ? "passed" : "failed"} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </section>
                ))
              ) : (
                <section className="panel">
                  <Empty
                    icon={FlaskConical}
                    title="Turn assumptions into evidence"
                    body="Run the active policy against threshold, maximum and allowed-read boundaries. Results are persisted with the suite version."
                  />
                </section>
              )}
            </>
          )}
          {page === "incidents" && (
            <>
              {data.incidents.length ? (
                data.incidents.map((i: Row) => (
                  <section className="panel incident-card" key={i.id}>
                    <span className="small-icon red">
                      <ShieldX size={22} />
                    </span>
                    <div>
                      <span className="eyebrow">
                        INC-{short(i.id)} · {date(i.created)}
                      </span>
                      <h2>{i.title}</h2>
                      <p>{i.reason}</p>
                      <div className="agent-tags">
                        <span>Agent suspended</span>
                        <span>Credentials revoked</span>
                        <span>Grants removed</span>
                      </div>
                    </div>
                    <Badge value={i.status} />
                  </section>
                ))
              ) : (
                <section className="panel">
                  <Empty
                    icon={ShieldCheck}
                    title="No containment incidents recorded"
                    body="Use the agent workspace to contain a compromised agent. New dispatch is blocked, credentials are revoked and tool grants are removed."
                    action={
                      <button
                        className="btn btn-outline"
                        onClick={() => go("agents")}
                      >
                        Open agent registry
                        <ArrowUpRight size={15} />
                      </button>
                    }
                  />
                </section>
              )}
              <StatusMessage>
                Containment cannot undo an external action already dispatched.
                Inspect in-flight and unknown executions separately.
              </StatusMessage>
            </>
          )}
          {["models", "usage"].includes(page) && <RuntimeConsole key={recoveryPanelKey(me)} me={me} />}
          {page === "operations" && operationsTab === "signals" && (
            <div
              role="tabpanel"
              id="operations-panel-signals"
              aria-labelledby="operations-tab-signals"
            >
              <React.Suspense
                fallback={<p role="status">Loading operating signals…</p>}
              >
                <RuntimeOperations key={recoveryPanelKey(me)} me={me} />
              </React.Suspense>
              <section className="operations-intro">
                <div>
                  <span className="eyebrow">OPERATIONAL ASSURANCE</span>
                  <h2>
                    Know what is ready.
                    <br />
                    See what comes next.
                  </h2>
                  <p>
                    Configuration signals help you prepare your environment.
                    They are not a production security certification.
                  </p>
                </div>
                <ShieldCheck size={76} strokeWidth={1} />
              </section>
              <div className="readiness-grid">
                {(data.operations.checks || []).map((check: Row) => (
                  <section className="panel readiness-card" key={check.name}>
                    <div>
                      <span className={"readiness-state " + check.state}>
                        {friendly(check.state)}
                      </span>
                      <h2>{check.name}</h2>
                      <p>{check.detail}</p>
                    </div>
                    <ChevronRight size={18} />
                  </section>
                ))}
              </div>
              <section className="panel maintenance-card">
                <div>
                  <h2>Expired-record maintenance</h2>
                  <p>
                    {data.operations.expired_sessions ?? 0} expired sessions ·{" "}
                    {data.operations.expired_exports ?? 0} expired exports in
                    this workspace.
                  </p>
                  <p>
                    Preview cleanup from the backend terminal. Add{" "}
                    <code>--apply</code> after reviewing the counts. Audit
                    events and business actions are preserved.
                  </p>
                </div>
                <code>python -m nexus.cli maintenance</code>
              </section>
            </div>
          )}
          {page === "settings" && (
            <>
              <Suspense
                fallback={<p role="status">Loading account controls…</p>}
              >
                <MemberAdmin me={me} />
                <EnvironmentSetup key={`${me.user.org_id}:${me.user.id}`} me={{ user: me.user }} />
              </Suspense>
              <SecretInputStatus key={recoveryPanelKey(me)} me={me} />
              <div className="settings-grid">
                <section className="panel settings-card">
                  <h2>Environment & controls</h2>
                  <dl>
                    {[
                      ["Environment", me.environment],
                      ["Runtime", friendly(data.settings.mode || "local")],
                      ["Policy engine", data.settings.policy_engine],
                      ["Database", data.settings.database],
                      ["Data", "Synthetic only"],
                      [
                        "SSO",
                        data.settings.identity?.sso_configured
                          ? "Configured"
                          : "Not configured",
                      ],
                      [
                        "Schema version",
                        String(data.settings.identity?.schema_version || 3),
                      ],
                      ["PKCE", "S256 / server-side state"],
                    ].map(([a, b]) => (
                      <div key={a}>
                        <dt>{a}</dt>
                        <dd>{b}</dd>
                      </div>
                    ))}
                  </dl>
                </section>
                <section className="panel settings-card">
                  <h2>Implementation boundaries</h2>
                  <p>
                    Build status is explicit, so the interface never implies an
                    integration is live.
                  </p>
                  <ul>
                    {(data.settings.limitations || []).map((v: string) => (
                      <li key={v}>{v}</li>
                    ))}
                  </ul>
                  <a
                    className="text-btn"
                    href="/api/docs"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open API reference
                    <ExternalLink size={14} />
                  </a>
                </section>
              </div>
            </>
          )}
          <footer className="content-footer">
            <span>
              <ShieldCheck size={14} />
              NEXUS AI Control · Governed actions. Verifiable outcomes.
            </span>
            <span>
              Updated{" "}
              {o.updated
                ? new Date(o.updated * 1000).toLocaleTimeString()
                : "—"}{" "}
              · Engineering workspace v0.16.0
            </span>
          </footer>
        </main>
      </div>
      {quickOpen && (
        <Modal
          title="Jump to a workspace view"
          onClose={() => setQuickOpen(false)}
        >
          <div className="search command-search">
            <Search size={18} />
            <input
              autoFocus
              data-autofocus
              aria-label="Find a workspace view"
              placeholder="Search agents, policies, approvals…"
              value={quickQuery}
              onChange={(e) => setQuickQuery(e.target.value)}
            />
          </div>
          <div className="command-results">
            {nav
              .filter(([, label]) =>
                label.toLowerCase().includes(quickQuery.toLowerCase()),
              )
              .map(([key, label, Icon]) => (
                <button
                  key={key}
                  onClick={() => {
                    go(key);
                    setQuickOpen(false);
                  }}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                  <ArrowUpRight size={15} />
                </button>
              ))}
            {!nav.some(([, label]) =>
              label.toLowerCase().includes(quickQuery.toLowerCase()),
            ) && <p>No matching views. Try “agents” or “audit”.</p>}
          </div>
        </Modal>
      )}
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={19} />
          {toast}
        </div>
      )}
      {modal && (
        <Modal
          title={
            (
              {
                agent: "Register a new agent",
                run: "Run a governed action",
                policy: "Update policy guardrails",
                approval: "Review requested action",
                "agent-detail": modal.row?.name,
                execution: "Action evidence",
                schema: "Registered tool schema",
                event: "Audit event",
                credential: "Workload credential",
                confirm: "Confirm containment",
                member: "Revoke workspace access",
              } as Row
            )[modal.type] || "Workspace"
          }
          onClose={() => setModal(null)}
          wide={["execution", "approval", "agent-detail"].includes(modal.type)}
        >
          {error && (
            <div className="error" role="alert">
              <TriangleAlert size={16} />
              {error}
            </div>
          )}
          {modal.type === "member" && (
            <form
              onSubmit={(e) =>
                formSubmit(
                  e,
                  (d) =>
                    api("/v1/members/" + modal.row.id + "/revoke", "POST", {
                      reason: d.get("reason"),
                    }),
                  "Member access revoked. Existing sessions ended.",
                )
              }
            >
              <StatusMessage>
                Revoke access for {modal.row.name} ({modal.row.email}). Existing
                sessions will end immediately. External identity-provider access
                and owned agent containment must be managed separately.
              </StatusMessage>
              <Field label="Reason for revocation">
                <textarea
                  name="reason"
                  required
                  minLength={8}
                  maxLength={500}
                  placeholder="Record the reason for the audit trail"
                />
              </Field>
              <div className="modal-actions">
                <button
                  className="btn btn-outline"
                  type="button"
                  onClick={() => setModal(null)}
                >
                  Cancel
                </button>
                <button className="btn btn-primary" disabled={busy}>
                  Revoke access
                </button>
              </div>
            </form>
          )}
          {modal.type === "agent" && (
            <form
              onSubmit={(e) =>
                formSubmit(
                  e,
                  (d) =>
                    api("/v1/agents", "POST", {
                      name: d.get("name"),
                      framework: d.get("framework"),
                      risk: d.get("risk"),
                    }),
                  "Agent registered in Draft.",
                )
              }
            >
              <StatusMessage>
                New agents have no implicit tool access. Add scoped grants
                before activation.
              </StatusMessage>
              <Field label="Agent name">
                <input
                  name="name"
                  minLength={2}
                  maxLength={80}
                  required
                  placeholder="e.g. Procurement Assistant"
                />
              </Field>
              <div className="form-grid">
                <Field label="Framework">
                  <select name="framework">
                    <option>Python SDK</option>
                    <option>LangGraph adapter</option>
                    <option>Custom adapter</option>
                  </select>
                </Field>
                <Field label="Risk tier">
                  <select name="risk">
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                    <option value="high">High</option>
                  </select>
                </Field>
              </div>
              <button className="btn btn-primary full" disabled={busy}>
                <Plus size={16} />
                Register draft agent
              </button>
            </form>
          )}
          {modal.type === "run" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const d = new FormData(e.currentTarget);
                const tool = data.tools.find(
                  (t: Row) => t.id === d.get("tool"),
                );
                if (!tool) {
                  setError("Choose a business tool before submitting.");
                  return;
                }
                const purchase = tool.kind === "purchase";
                const body = {
                  agent_id: d.get("agent"),
                  tool_id: tool.id,
                  request: {
                    tool_version: "1.0",
                    schema_version: "1",
                    action: purchase ? "purchase:create" : "supplier:read",
                    resource: purchase ? "purchase_requests" : "suppliers",
                    arguments: purchase
                      ? {
                          supplier_id: d.get("supplier"),
                          amount: Number(d.get("amount")).toFixed(2),
                          currency: "USD",
                          purpose: d.get("purpose"),
                        }
                      : { supplier_id: d.get("supplier") },
                    simulation: d.get("simulation"),
                  },
                };
                const fingerprint = JSON.stringify(body);
                perform(
                  () =>
                    submitIntent(intentKeys.forContext(recoveryPanelKey(me)), fingerprint, (key) =>
                      api("/v1/console/actions", "POST", body, key),
                    ),
                  submissionMessage,
                ).then((result) => {
                  if (result) {
                    setFilter("all");
                    go(
                      result.status === "awaiting_approval"
                        ? "approvals"
                        : "executions",
                    );
                  }
                });
              }}
            >
              <StatusMessage>
                Select a business tool explicitly. Supplier directory performs a
                read-only lookup. Purchase requests evaluates the amount and
                purpose against policy.{" "}
                {me.synthetic
                  ? "This runner uses the local synthetic connector."
                  : "Approved requests can create records in the configured customer system. Review the destination in Runtime signals."}
              </StatusMessage>
              <Field label="Requesting agent">
                <select name="agent">
                  {data.agents
                    .filter((a: Row) => a.status === "active")
                    .map((a: Row) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Business tool">
                <select
                  name="tool"
                  required
                  value={runToolId}
                  onChange={(e) => setRunToolId(e.target.value)}
                >
                  <option value="" disabled>
                    Choose a business tool
                  </option>
                  {data.tools.map((t: Row) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="form-grid">
                <Field
                  label={
                    me.synthetic
                      ? "Synthetic supplier"
                      : "Customer supplier reference"
                  }
                >
                  {!me.synthetic ? (
                    <input
                      name="supplier"
                      required
                      maxLength={64}
                      pattern="[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}"
                      placeholder="Customer supplier ID"
                    />
                  ) : (
                    <select name="supplier">
                      <option>SUP-DEMO-104</option>
                      <option>SUP-DEMO-205</option>
                    </select>
                  )}
                </Field>
                {data.tools.find((t: Row) => t.id === runToolId)?.kind ===
                  "purchase" && (
                  <Field label="Purchase amount (USD)">
                    <input
                      name="amount"
                      type="number"
                      min="0.01"
                      max="99999999"
                      step="0.01"
                      defaultValue={me.synthetic ? "12500" : ""}
                      required
                    />
                  </Field>
                )}
              </div>
              {data.tools.find((t: Row) => t.id === runToolId)?.kind ===
                "purchase" && (
                <Field label="Purchase purpose">
                  <input
                    name="purpose"
                    minLength={3}
                    maxLength={300}
                    required
                    defaultValue={
                      me.synthetic ? "Replacement pumps - synthetic pilot" : ""
                    }
                  />
                </Field>
              )}
              {runToolId && (
                <StatusMessage>
                  {data.tools.find((t: Row) => t.id === runToolId)?.kind ===
                  "purchase"
                    ? "Purchase request selected. Policy may allow it, require independent approval, or deny it."
                    : "Supplier lookup selected. No purchase amount or purpose is sent; this lookup does not create a purchase approval."}
                </StatusMessage>
              )}
              {me.synthetic ? (
                <details className="simulation">
                  <summary>
                    <FlaskConical size={15} />
                    Synthetic failure scenario
                  </summary>
                  <Field label="Connector behaviour">
                    <select name="simulation">
                      <option value="normal">Normal result</option>
                      <option value="timeout_after_commit">
                        Timeout after commit (unknown outcome)
                      </option>
                      <option value="fail_before_commit">
                        Reject before commit
                      </option>
                      <option value="mismatch">
                        Return a mismatched supplier
                      </option>
                    </select>
                  </Field>
                </details>
              ) : (
                <input type="hidden" name="simulation" value="normal" />
              )}
              <button
                className="btn btn-primary full"
                disabled={
                  busy ||
                  !runToolId ||
                  !data.agents.some((a: Row) => a.status === "active")
                }
              >
                <Play size={16} />
                Submit for policy evaluation
              </button>
            </form>
          )}
          {modal.type === "policy" && (
            <form
              onSubmit={(e) =>
                formSubmit(
                  e,
                  (d) =>
                    api("/v1/policies/activate", "POST", {
                      expected_version: policy.version,
                      threshold: Number(d.get("threshold")).toFixed(2),
                      maximum: Number(d.get("maximum")).toFixed(2),
                      reason: d.get("reason"),
                    }),
                  "New policy version activated. Prior pending authorizations require re-evaluation.",
                )
              }
            >
              <StatusMessage>
                Changing the active policy blocks dispatch of prior-version
                queued authorizations. Historical evidence is preserved.
              </StatusMessage>
              <div className="form-grid">
                <Field label="Approval threshold (USD)">
                  <input
                    name="threshold"
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    defaultValue={policy?.threshold}
                  />
                </Field>
                <Field label="Maximum permitted amount (USD)">
                  <input
                    name="maximum"
                    type="number"
                    min="0.01"
                    step="0.01"
                    required
                    defaultValue={policy?.maximum}
                  />
                </Field>
              </div>
              <Field label="Reason for activation">
                <textarea
                  name="reason"
                  minLength={5}
                  maxLength={500}
                  required
                  placeholder="Why is this policy changing?"
                />
              </Field>
              <button className="btn btn-primary full" disabled={busy}>
                <ShieldCheck size={16} />
                Activate version {policy?.version + 1}
              </button>
            </form>
          )}
          {modal.type === "approval" && (
            <>
              <div className="review-layout">
                <section>
                  <Badge value={modal.row.status} />
                  <h3>
                    Purchase request · USD{" "}
                    {Number(
                      modal.row.action.envelope.arguments.amount,
                    ).toLocaleString()}
                  </h3>
                  <dl className="detail-list">
                    {[
                      [
                        "Supplier",
                        modal.row.action.envelope.arguments.supplier_id,
                      ],
                      ["Purpose", modal.row.action.envelope.arguments.purpose],
                      ["Policy reason", modal.row.action.reason],
                      ["Policy version", "v" + modal.row.policy_version],
                      ["Expires", date(modal.row.expires)],
                    ].map(([a, b]: any) => (
                      <div key={a}>
                        <dt>{a}</dt>
                        <dd>{b}</dd>
                      </div>
                    ))}
                  </dl>
                  <label className="hash-label">
                    Immutable SHA-256 fingerprint
                  </label>
                  <code className="hash">{modal.row.payload_hash}</code>
                  <details>
                    <summary>Inspect canonical action</summary>
                    <pre>
                      {JSON.stringify(modal.row.action.envelope, null, 2)}
                    </pre>
                  </details>
                </section>
                <section className="review-controls">
                  <ShieldCheck size={28} />
                  <h3>Independent review</h3>
                  <p>
                    Approval applies only to this exact payload, policy version
                    and expiry. Execution is a separate step.
                  </p>
                  {modal.row.self_review && (
                    <div className="error">
                      You requested this action. Another authorized reviewer
                      must decide it.
                    </div>
                  )}
                  {!can("approve") && (
                    <StatusMessage>
                      Sign in with the independently provisioned reviewer
                      account to decide.
                    </StatusMessage>
                  )}
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = e.nativeEvent as SubmitEvent;
                      const decision = (f.submitter as HTMLButtonElement)
                        ?.value;
                      const d = new FormData(e.currentTarget);
                      perform(
                        () =>
                          api(
                            "/v1/approvals/" + modal.row.id + "/decision",
                            "POST",
                            {
                              decision,
                              expected_version: modal.row.version,
                              request_hash: modal.row.payload_hash,
                              comment: d.get("comment"),
                            },
                          ),
                        "Review decision recorded.",
                      );
                    }}
                  >
                    <Field label="Decision note">
                      <textarea
                        name="comment"
                        minLength={5}
                        maxLength={500}
                        required
                        placeholder="Record the reason for your decision"
                      />
                    </Field>
                    <div className="review-buttons">
                      <button
                        name="decision"
                        value="reject"
                        className="btn btn-outline"
                        disabled={
                          busy ||
                          !can("approve") ||
                          modal.row.self_review ||
                          modal.row.status !== "pending"
                        }
                      >
                        Reject
                      </button>
                      <button
                        name="decision"
                        value="approve"
                        className="btn btn-primary"
                        disabled={
                          busy ||
                          !can("approve") ||
                          modal.row.self_review ||
                          modal.row.status !== "pending"
                        }
                      >
                        Approve action
                        <Check size={15} />
                      </button>
                    </div>
                  </form>
                </section>
              </div>
            </>
          )}
          {modal.type === "execution" && (
            <>
              <div className="execution-summary">
                <span className="small-icon blue">
                  <GitBranch size={23} />
                </span>
                <div>
                  <h3>
                    {friendly(modal.row.envelope.action.replace(":", " "))}
                  </h3>
                  <code>
                    ACT-{short(modal.row.id)} · Policy v
                    {modal.row.policy_version}
                  </code>
                </div>
                <Badge value={modal.row.status} />
              </div>
              <div className="execution-facts">
                <div>
                  <span>Business reference</span>
                  <strong>
                    {modal.row.external_ref || "Not verified yet"}
                  </strong>
                </div>
                <div>
                  <span>Execution attempts</span>
                  <strong>{modal.row.attempts}</strong>
                </div>
                <div>
                  <span>Trace</span>
                  <code>{short(modal.row.trace_id)}</code>
                </div>
              </div>
              <h3 className="section-title">The evidence timeline</h3>
              <div className="timeline">
                {modal.row.events.map((ev: Row) => (
                  <div className="timeline-event" key={ev.id}>
                    <span>
                      <Check size={13} />
                    </span>
                    <div>
                      <strong>{friendly(ev.event.replaceAll(".", " "))}</strong>
                      <p>
                        {date(ev.created)} ·{" "}
                        {ev.actor === "worker"
                          ? "Execution worker"
                          : short(ev.actor)}
                      </p>
                      {ev.detail.reason && <code>{ev.detail.reason}</code>}
                    </div>
                  </div>
                ))}
              </div>
              {modal.row.status === "outcome_unknown" && (
                <div className="unknown-card">
                  <TriangleAlert size={24} />
                  <div>
                    <strong>Outcome is unknown. Do not blindly retry.</strong>
                    <p>
                      Look up the authoritative mock business result using this
                      action's stable reference.
                    </p>
                  </div>
                  <button
                    className="btn btn-primary"
                    disabled={!can("operate") || busy}
                    onClick={() =>
                      perform(
                        () =>
                          api(
                            "/v1/actions/" + modal.row.id + "/reconcile",
                            "POST",
                          ),
                        "Reconciliation completed. Inspect the updated outcome.",
                      )
                    }
                  >
                    Reconcile
                  </button>
                </div>
              )}
              <details>
                <summary>Immutable request & verification</summary>
                <pre>
                  {JSON.stringify(
                    {
                      request: modal.row.envelope,
                      verification: modal.row.verification,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </>
          )}
          {modal.type === "agent-detail" && (
            <>
              <div className="agent-detail-top">
                <span className={"agent-art " + modal.row.risk}>
                  <Blocks size={30} />
                </span>
                <div>
                  <Badge value={modal.row.status} />
                  <p>
                    {modal.row.framework} · v{modal.row.version} · {me.environment}
                  </p>
                </div>
              </div>
              <div className="identity-box">
                <Fingerprint size={22} />
                <div>
                  <strong>Distinct workload identity</strong>
                  <code>{modal.row.id}</code>
                </div>
                <span>Generation {modal.row.generation}</span>
              </div>
              <h3 className="section-title">Explicit tool grants</h3>
              {modal.row.grants.length ? (
                modal.row.grants.map((g: Row) => (
                  <div className="grant-row" key={g.id}>
                    <Waypoints size={18} />
                    <div>
                      <strong>
                        {data.tools.find((t: Row) => t.id === g.tool_id)?.name}
                      </strong>
                      <code>{g.scope}</code>
                    </div>
                    {can("manage") && (
                      <button
                        className="text-btn danger"
                        disabled={busy}
                        onClick={() =>
                          perform(
                            () =>
                              api(
                                "/v1/agents/" +
                                  modal.row.id +
                                  "/tool-grants/" +
                                  g.id,
                                "DELETE",
                              ),
                            "Grant revoked. Workload generation advanced.",
                          )
                        }
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <p className="muted">
                  No grants. Tool access is denied by default.
                </p>
              )}
              {can("manage") && (
                <form
                  className="grant-form"
                  onSubmit={(e) =>
                    formSubmit(
                      e,
                      (d) => {
                        const tool = data.tools.find(
                          (t: Row) => t.id === d.get("tool"),
                        );
                        return api(
                          "/v1/agents/" + modal.row.id + "/tool-grants",
                          "POST",
                          {
                            tool_id: tool.id,
                            scope:
                              tool.kind === "supplier"
                                ? "supplier:read"
                                : "purchase:create",
                          },
                        );
                      },
                      "Scoped grant added.",
                    )
                  }
                >
                  <Field label="Add an allowlisted tool">
                    <select name="tool">
                      {data.tools.map((t: Row) => (
                        <option value={t.id} key={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <button className="btn btn-outline" disabled={busy}>
                    <Plus size={15} />
                    Grant access
                  </button>
                </form>
              )}
              <div className="agent-lifecycle-actions">
                {can("manage") && modal.row.status !== "active" && (
                  <button
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={() =>
                      perform(
                        () =>
                          api(
                            "/v1/agents/" +
                              modal.row.id +
                              "/lifecycle/activate",
                            "POST",
                            { reason: "Activated after explicit grant review" },
                          ),
                        "Agent activated.",
                      )
                    }
                  >
                    <Play size={15} />
                    Activate agent
                  </button>
                )}
                {can("manage") && (
                  <button
                    className="btn btn-outline"
                    disabled={busy}
                    onClick={async () => {
                      const r = await perform(
                        () =>
                          api(
                            "/v1/agents/" + modal.row.id + "/lifecycle/rotate",
                            "POST",
                            {
                              reason:
                                "Operator requested workload credential rotation",
                            },
                          ),
                        "Credential rotated.",
                        false,
                      );
                      if (r) setModal({ type: "credential", row: r });
                    }}
                  >
                    <KeyRound size={15} />
                    Rotate credential
                  </button>
                )}
                {can("contain") && (
                  <button
                    className="btn btn-danger"
                    onClick={() =>
                      setModal({ type: "confirm", row: modal.row })
                    }
                  >
                    <ShieldX size={15} />
                    Contain agent
                  </button>
                )}
              </div>
            </>
          )}
          {modal.type === "confirm" && (
            <form
              onSubmit={(e) =>
                formSubmit(
                  e,
                  (d) =>
                    api("/v1/agents/" + modal.row.id + "/contain", "POST", {
                      reason: d.get("reason"),
                    }),
                  "Agent contained. Inspect in-flight actions separately.",
                )
              }
            >
              <div className="error">
                <TriangleAlert size={19} />
                This suspends {modal.row.name}, revokes workload credentials and
                removes all tool grants.
              </div>
              <p>
                New dispatch is blocked. External actions already dispatched
                cannot be undone.
              </p>
              <Field label="Containment reason">
                <textarea
                  name="reason"
                  required
                  minLength={5}
                  maxLength={500}
                />
              </Field>
              <button className="btn btn-danger full" disabled={busy}>
                Confirm containment
              </button>
            </form>
          )}
          {modal.type === "credential" && (
            <>
              <div className="error">
                <KeyRound size={18} />
                Shown once. Keep this workload credential outside prompts,
                source code and ordinary logs.
              </div>
              <code className="hash secret-value">{modal.row.credential}</code>
              <button
                className="btn btn-outline"
                onClick={async () => {
                  await navigator.clipboard.writeText(modal.row.credential);
                  setToast("Credential copied. Store it securely.");
                }}
              >
                <Copy size={16} />
                Copy credential
              </button>
              <p className="muted">
                Exchange it at POST /v1/workload/token/{modal.row.id}. Existing
                tokens were invalidated by rotation.
              </p>
            </>
          )}
          {modal.type === "schema" && (
            <>
              <StatusMessage>
                {modal.row.name} · Schema {modal.row.version} · Local synthetic
                connector
              </StatusMessage>
              <pre>{JSON.stringify(modal.row.schema_json, null, 2)}</pre>
            </>
          )}
          {modal.type === "event" && (
            <pre>{JSON.stringify(modal.row, null, 2)}</pre>
          )}
        </Modal>
      )}
    </div>
  );
}
function ContextRoot() {
  const intentKeys = useRef(new IntentKeyRegistry());
  const [epoch,setEpoch] = useState(() => sessionContext.capture().epoch);
  useEffect(() => sessionContext.subscribe(setEpoch),[]);
  return <App key={epoch} intentKeys={intentKeys.current} />;
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ContextRoot />
  </React.StrictMode>,
);
