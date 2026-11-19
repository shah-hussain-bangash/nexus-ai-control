import fixtures from "./demo-data.json";
import { validateInterface, type InterfaceModule } from "./interfaceDesign";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public requestId: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
const working: Record<string, any> = structuredClone(fixtures);
const modules: InterfaceModule[] = working["/v1/interface-catalog"].modules;
function saveRevision(row: any) {
  const path = "/v1/workbench/" + row.id + "/history";
  const history = working[path] || [];
  working[path] = [
    {
      id: crypto.randomUUID(),
      asset_id: row.id,
      version: row.version,
      created: Date.now() / 1000,
      snapshot: structuredClone(row),
      author_id: "synthetic-preview",
    },
    ...history,
  ];
}
function validate(row: any) {
  const spec = modules.find((m) => m.id === row.config.module);
  if (!spec) throw new Error("Unknown interface module.");
  const errors = validateInterface(spec, row);
  if (Object.keys(errors).length)
    throw new Error(Object.values(errors).join(" "));
  return spec;
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, 90));
  const signinPreview = new URL(location.href).searchParams.get("screen") === "signin";
  if (path === "/v1/me" && signinPreview) throw new ApiError("Synthetic sign-in preview",401,"PREVIEW_SIGNIN","");
  if (path === "/auth/config")
    return { mode: "preview", local_login: signinPreview, oidc: false } as T;
  const data = body as Record<string, any> | undefined;
  const workbench = working["/v1/workbench"];
  const assets = workbench.assets as any[];
  if (method === "POST" && path === "/v1/interface-starter")
    return { created: 0, runtime_activated: false, synthetic: true } as T;
  if (
    method === "POST" &&
    path === "/v1/workbench" &&
    data?.kind === "blueprint"
  ) {
    const row = {
      ...structuredClone(data),
      id: crypto.randomUUID(),
      kind: "blueprint",
      version: 1,
      status: "draft",
      org_id: "northstar",
      env: "staging",
      created: Date.now() / 1000,
      updated: Date.now() / 1000,
      author_id: "synthetic-preview",
    };
    validate(row);
    assets.unshift(row);
    saveRevision(row);
    return structuredClone(row) as T;
  }
  const match = path.match(
    /^\/v1\/workbench\/([^/]+)(?:\/(validate|archive|run))?$/,
  );
  const row = match
    ? assets.find((a) => a.id === match[1] && a.kind === "blueprint")
    : undefined;
  if (row && method !== "GET") {
    if (row.status === "archived" && match?.[2] !== "archive")
      throw new Error(
        "Archived interface plans are read-only. Restore as a separate draft.",
      );
    if (method === "PUT" && !match?.[2]) {
      if (data?.expected_version !== row.version)
        throw new Error(
          "Another editor changed this preview record. Refresh first.",
        );
      validate(data);
      Object.assign(row, structuredClone(data), {
        kind: "blueprint",
        version: row.version + 1,
        status: "draft",
        updated: Date.now() / 1000,
      });
      saveRevision(row);
      return structuredClone(row) as T;
    }
    if (
      method === "POST" &&
      ["validate", "archive"].includes(match?.[2] || "")
    ) {
      if (data?.expected_version !== row.version)
        throw new Error("Refresh this preview revision first.");
      validate(row);
      row.status = match?.[2] === "validate" ? "validated" : "archived";
      row.version++;
      row.updated = Date.now() / 1000;
      saveRevision(row);
      return structuredClone(row) as T;
    }
    if (method === "POST" && match?.[2] === "run") {
      const spec = validate(row);
      const action = spec.actions.find(
        (a) => a.id === data?.variables?.design_action,
      );
      const scenario = data?.variables?.design_scenario || "happy_path";
      const result = {
        module: spec.id,
        title: spec.title,
        action: action?.label || "Full interface journey",
        scenario,
        configured_fields: Object.keys(row.config.values).length,
        runtime_activated: false,
        provider_calls: 0,
        business_effects: 0,
        boundary:
          "Client-only synthetic interface preview. No runtime service, provider request or business action was executed.",
        steps: spec.stages.map((s, i) => ({
          ...s,
          status:
            scenario === "happy_path" || i < 2
              ? "design_checked"
              : i === 2
                ? "simulated_stop"
                : "not_simulated",
          detail:
            scenario === "happy_path" || i < 2
              ? s.description
              : "UI scenario: " +
                scenario.replaceAll("_", " ") +
                ". No real operation attempted.",
        })),
      };
      const run = {
        id: crypto.randomUUID(),
        asset_id: row.id,
        asset_version: row.version,
        kind: "blueprint",
        status: "completed",
        duration_ms: 0,
        created: Date.now() / 1000,
        result,
      };
      workbench.runs.unshift(run);
      return structuredClone(run) as T;
    }
  }
  if (method !== "GET")
    throw new Error(
      "Only interface-plan actions are interactive in this synthetic preview. Run the full source for authenticated control-plane operations.",
    );
  const url = new URL(path, location.origin);
  if (url.pathname === "/v1/workspace-environments") {
    return {
      workspace: { id: "northstar", name: "Northstar · synthetic preview" },
      current_environment: "staging",
      switching_enabled: false,
      read_only: true,
      items: [
        {
          key: "staging",
          name: "Staging",
          state: "active",
          version: 1,
          human_runtime_enabled: true,
        },
        {
          key: "production",
          name: "Production",
          state: "preparing",
          version: 1,
          human_runtime_enabled: false,
        },
      ],
    } as T;
  }
  if (
    /^\/v1\/workspace-environments\/(staging|production)\/assignments$/.test(
      url.pathname,
    )
  ) {
    return {
      items: url.pathname.includes("/staging/")
        ? [
            {
              id: "preview-owner",
              name: "Preview Owner",
              role: "owner",
              active: true,
            },
          ]
        : [],
      editing_enabled: false,
      switching_enabled: false,
    } as T;
  }
  if (["/v1/agent-runs","/v1/documents","/v1/retrieval-checks",
    "/v1/hybrid-search/history","/v1/ingestion-jobs"].includes(url.pathname)) {
    const base=working[url.pathname],offset=Number(url.searchParams.get("offset")||0),limit=Number(url.searchParams.get("limit")||20);
    return structuredClone({...base,items:base.items.slice(offset,offset+limit),next_offset:offset+limit<base.items.length?offset+limit:null}) as T;
  }
  if (url.pathname === "/v1/documents/search") {
    const terms=(url.searchParams.get("q")||"").toLowerCase().split(/\s+/).filter(Boolean);
    const matches=working["/v1/documents"].items.map((d:any)=>working["/v1/documents/"+d.id]).filter((d:any)=>terms.some(t=>d.content.toLowerCase().includes(t)));
    return {items:matches.map((d:any)=>({document_id:d.id,document_version:d.version,title:d.title,filename:d.filename,chunk:1,excerpt:d.content,sha256:d.content_hash,score:1,citation:d.id+":v"+d.version+":chunk1"})),method:"Synthetic fixture text match; the real backend supplies ACL-filtered lexical ranking.",provider_calls:0} as T;
  }
  if (url.pathname === "/v1/inference-calls") {
    const q = (url.searchParams.get("q") || "").toLowerCase(),
      status = url.searchParams.get("status") || "all",
      limit = Number(url.searchParams.get("limit") || 10),
      offset = Number(url.searchParams.get("cursor") || 0);
    const all = (working["/v1/runtime"].calls || []).filter(
      (r: any) =>
        (status === "all" || r.status === status) &&
        JSON.stringify([r.id, r.asset_id]).toLowerCase().includes(q),
    );
    return {
      items: all.slice(offset, offset + limit),
      has_more: offset + limit < all.length,
      next_cursor: offset + limit < all.length ? String(offset + limit) : null,
      limit,
    } as T;
  }
  if (url.pathname === "/v1/audit-page") {
    const q = (url.searchParams.get("q") || "").toLowerCase(),
      limit = Number(url.searchParams.get("limit") || 25),
      offset = Number(url.searchParams.get("cursor") || 0);
    const rows = (working["/v1/audit-events"] || []).filter((r: any) =>
      JSON.stringify(r).toLowerCase().includes(q),
    );
    return {
      items: rows.slice(offset, offset + limit),
      has_more: offset + limit < rows.length,
      next_cursor: offset + limit < rows.length ? String(offset + limit) : null,
    } as T;
  }
  const value = working[path];
  if (value === undefined)
    throw new Error("This view is unavailable in the synthetic UI preview.");
  return structuredClone(value) as T;
}
