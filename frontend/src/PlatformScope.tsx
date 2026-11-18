import { useEffect, useState } from "react";
import {
  ArrowRight,
  Download,
  Layers3,
  Search,
  ShieldCheck,
} from "lucide-react";
import { api } from "./api";
import type { InterfaceModule } from "./interfaceDesign";
import "./functions.css";
export function PlatformScope({
  onOpen,
}: {
  onOpen: (module: string, feature: string) => void;
}) {
  const [modules, setModules] = useState<InterfaceModule[]>([]),
    [assets, setAssets] = useState<any[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [q, setQ] = useState(""),
    [area, setArea] = useState("all"),
    [moduleId, setModule] = useState("all"),
    [phase, setPhase] = useState("all"),
    [priority, setPriority] = useState("all"),
    [page, setPage] = useState(0);
  async function load() {
    setLoading(true);
    try {
      const [catalog, w] = await Promise.all([
        api("/v1/interface-catalog"),
        api("/v1/workbench"),
      ]);
      setModules(catalog.modules);
      setAssets(
        w.assets
          .filter((a: any) => a.kind === "blueprint" && a.status !== "archived")
          .sort((a: any, b: any) => b.updated - a.updated),
      );
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
  const all = modules.flatMap((m) =>
      m.features.map((f) => ({
        module: m,
        feature: f,
        plan: assets
          .find((a) => a.config.module === m.id)
          ?.config.function_plans?.find((p: any) => p.feature_id === f.id),
      })),
    ),
    filtered = all.filter(
      ({ module: m, feature: f, plan }) =>
        (area === "all" || m.area === area) &&
        (moduleId === "all" || m.id === moduleId) &&
        (phase === "all" || (plan?.phase || "planned") === phase) &&
        (priority === "all" || f.priority === priority) &&
        (
          m.title +
          " " +
          f.title +
          " " +
          f.summary +
          " " +
          f.fields.map((x) => x.label).join(" ")
        )
          .toLowerCase()
          .includes(q.toLowerCase()),
    ),
    pages = Math.max(1, Math.ceil(filtered.length / 12)),
    safePage = Math.min(page, pages - 1),
    reviewed = all.filter(
      (x) => x.plan?.phase && x.plan.phase !== "planned",
    ).length;
  function exportScope() {
    const u = URL.createObjectURL(
      new Blob(
        [
          JSON.stringify(
            {
              release: "0.16.0",
              scope:
                "Long-term UI design inventory; runtime acceptance separate",
              modules,
              selected_plans: assets.map((a) => ({
                module: a.config.module,
                asset_id: a.id,
                version: a.version,
                function_plans: a.config.function_plans || [],
              })),
              runtime_activated: false,
            },
            null,
            2,
          ),
        ],
        { type: "application/json" },
      ),
    );
    const a = document.createElement("a");
    a.href = u;
    a.download = "NEXUS_Long_Term_UI_Scope.json";
    a.click();
    URL.revokeObjectURL(u);
  }
  return (
    <section
      className="platform-scope ops-console"
      aria-label="Platform function map"
    >
      <div className="function-map-hero">
        <div>
          <small>DESIGN THE WHOLE PLATFORM BEFORE ACTIVATION</small>
          <h2>One map. Every planned capability.</h2>
          <p>
            Find the remaining enterprise functions, open their UI designs,
            assign an owner and keep a versioned implementation plan. A reviewed
            screen never marks its backend production-ready.
          </p>
        </div>
        <ShieldCheck size={62} />
      </div>
      <div className="ops-metrics">
        <article>
          <span>Module domains</span>
          <strong>{modules.length}</strong>
          <small>Existing operational workspaces</small>
        </article>
        <article>
          <span>Detailed function designs</span>
          <strong>{all.length}</strong>
          <small>
            {all.reduce((n, x) => n + x.feature.fields.length, 0)}{" "}
            feature-specific screen controls
          </small>
        </article>
        <article>
          <span>Manually reviewed UI plans</span>
          <strong>{reviewed}</strong>
          <small>Latest active plan per module · no runtime sign-off</small>
        </article>
      </div>
      {loading && <p role="status">Loading the complete function inventory…</p>}
      {error && (
        <div className="ops-alert error" role="alert">
          <p>{error}</p>
          <button className="btn btn-outline" onClick={load}>
            Retry inventory
          </button>
        </div>
      )}
      <div className="scope-filters">
        <label className="ops-search">
          <Search size={17} />
          <input
            aria-label="Search all platform functions"
            placeholder="Find a function, module or control…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <select
          aria-label="Filter function area"
          value={area}
          onChange={(e) => {
            setArea(e.target.value);
            setPage(0);
          }}
        >
          <option value="all">All areas</option>
          {Array.from(new Set(modules.map((m) => m.area))).map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
        <select
          aria-label="Filter function module"
          value={moduleId}
          onChange={(e) => {
            setModule(e.target.value);
            setPage(0);
          }}
        >
          <option value="all">All modules</option>
          {modules.map((m) => (
            <option key={m.id} value={m.id}>
              {m.title}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter function planning phase"
          value={phase}
          onChange={(e) => {
            setPhase(e.target.value);
            setPage(0);
          }}
        >
          <option value="all">All planning phases</option>
          <option value="planned">UI planned</option>
          <option value="ui_reviewed">UI reviewed</option>
          <option value="backend_in_progress">
            Backend in progress (planning)
          </option>
          <option value="staging_review">Staging review planned</option>
        </select>
        <select
          aria-label="Filter function priority"
          value={priority}
          onChange={(e) => {
            setPriority(e.target.value);
            setPage(0);
          }}
        >
          <option value="all">All priorities</option>
          <option>Foundation</option>
          <option>Advanced</option>
        </select>
        <button className="btn btn-outline" onClick={exportScope}>
          <Download size={16} /> Export full UI scope
        </button>
      </div>
      <div className="scope-result-heading">
        <strong>{filtered.length} matching functions</strong>
        <span>
          Each includes configuration, journey, intended roles, eight screen
          states, API handoff and UI review.
        </span>
      </div>
      <div className="scope-grid">
        {filtered
          .slice(safePage * 12, safePage * 12 + 12)
          .map(({ module: m, feature: f, plan }) => (
            <article key={f.id}>
              <div className="scope-card-top">
                <Layers3 size={22} />
                <span className="ops-badge">{f.priority}</span>
              </div>
              <small>
                {m.area} / {m.title}
              </small>
              <h3>{f.title}</h3>
              <p>{f.summary}</p>
              <div className="function-pills">
                <span>{f.fields.length} fields</span>
                <span>{f.actions.length} review actions</span>
                <span>{(plan?.phase || "planned").replaceAll("_", " ")}</span>
              </div>
              <button
                className="btn btn-primary"
                onClick={() => onOpen(m.id, f.id)}
              >
                Open function screen <ArrowRight size={16} />
              </button>
            </article>
          ))}
      </div>
      {!loading && !filtered.length && (
        <div className="ops-empty">
          <h3>No matching functions</h3>
          <p>Clear the filters to return to the complete inventory.</p>
          <button
            className="btn btn-outline"
            onClick={() => {
              setQ("");
              setArea("all");
              setModule("all");
              setPhase("all");
              setPriority("all");
              setPage(0);
            }}
          >
            Clear all filters
          </button>
        </div>
      )}
      <footer className="ops-pagination">
        <span>
          Page {safePage + 1} of {pages}
        </span>
        <button
          className="btn btn-outline"
          disabled={safePage === 0}
          onClick={() => setPage(safePage - 1)}
        >
          Previous functions
        </button>
        <button
          className="btn btn-outline"
          disabled={safePage + 1 >= pages}
          onClick={() => setPage(safePage + 1)}
        >
          Next functions
        </button>
      </footer>
      <div className="scope-boundary">
        <strong>Defined scope, tracked over time</strong>
        <p>
          This inventory expands the existing 18-module design. New requirements
          can be added as the project grows. Operational rehearsal commands,
          function screen designs and live services are separate layers; their
          counts are not a production-completion percentage.
        </p>
      </div>
    </section>
  );
}
