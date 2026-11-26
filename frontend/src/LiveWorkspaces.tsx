import { useEffect, useRef, useState, lazy, Suspense } from "react";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileText,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api } from "./api";
import { sendLiveIntent, liveIntentScope } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { procurementRun, intakeMetadata, runControls } from "./liveRequests";
import { registerNavigationGuard } from "./navigationGuard";
import "./live.css";
import { Modal } from "./RuntimeDialog";
const RetrievalQuality = lazy(() =>
  import("./RetrievalQuality").then((m) => ({ default: m.RetrievalQuality })),
);
const IntakeQueue = lazy(() =>
  import("./IntakeQueue").then((m) => ({ default: m.IntakeQueue })),
);
type Row = Record<string, any>;
function pendingIntent(scope: string) {
  try {
    return readRecovery(sessionStorage, scope);
  } catch {
    return null;
  }
}
function State({ value }: { value: string }) {
  return (
    <span className={"live-state " + value}>{value.replaceAll("_", " ")}</span>
  );
}
function Alerts({ error, notice }: { error: string; notice: string }) {
  return (
    <>
      {error && (
        <div className="ops-alert error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="ops-alert success" role="status">
          {notice}
        </div>
      )}
    </>
  );
}
export function DurableExecution({
  me,
  data,
  onNavigate,
}: {
  me: Row;
  data: Row;
  onNavigate: (page: string) => void;
}) {
  const [rows, setRows] = useState<Row[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState(""),
    [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null),
    [creating, setCreating] = useState(false),
    [command, setCommand] = useState(""),
    [note, setNote] = useState(""),
    [agent, setAgent] = useState(""),
    [mode, setMode] = useState("lookup"),
    [supplier, setSupplier] = useState(me.synthetic ? "SUP-DEMO-104" : ""),
    [amount, setAmount] = useState(me.synthetic ? "12500.00" : ""),
    [purpose, setPurpose] = useState(
      me.synthetic ? "Synthetic replacement equipment" : "",
    );
  const scope = liveIntentScope("run", me.user.org_id, me.user.id, me.environment);
  const [pendingRun, setPendingRun] = useState(() => pendingIntent(scope));
  const canEdit = me.permissions?.includes("operate"),
    canReview = me.permissions?.includes("approve"),
    run = rows.find((r) => r.id === selected) || rows[0],
    agents = (data.agents || []).filter((a: Row) => a.status === "active");
  useEffect(() => {
    if (!agent && agents.length) setAgent(agents[0].id);
  }, [data.agents, agent]);
  async function load() {
    try {
      const r = await api("/v1/agent-runs?offset=" + offset + "&limit=20");
      const items = r.items;
      if (selected && !items.some((x: Row) => x.id === selected)) {
        try {
          items.unshift(await api("/v1/agent-runs/" + selected));
        } catch {}
      }
      setRows(items);
      setNext(r.next_offset);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [offset, selected]);
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const lookup = data.tools.find(
          (t: Row) => t.kind === "supplier" && t.status === "validated",
        ),
        purchase = data.tools.find(
          (t: Row) => t.kind === "purchase" && t.status === "validated",
        );
      const body = procurementRun(
        agent,
        lookup?.id,
        purchase?.id,
        mode,
        supplier,
        amount,
        purpose,
      );
      const result = await sendLiveIntent<Row & { id: string; status: string }>(
        sessionStorage,
        scope,
        body,
        (key) => api("/v1/agent-runs", "POST", body, key),
      );
      setPendingRun(null);
      setSelected(result.id);
      setCreating(false);
      setOffset(0);
      setNotice(
        "Run saved and queued. The worker will advance each persisted checkpoint.",
      );
      await load();
    } catch (e) {
      setPendingRun(pendingIntent(scope));
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recover() {
    if (!pendingRun) return;
    setBusy(true);
    try {
      const r = await api("/v1/agent-runs/recover", "POST", {
        key: pendingRun.key,
      });
      acknowledgeRecovery(sessionStorage, scope, pendingRun, r);
      setPendingRun(null);
      setSelected(r.id);
      setNotice("Original run recovered without dispatching it again.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function act(e: React.FormEvent) {
    e.preventDefault();
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const review = ["approve", "reject"].includes(command);
      const result = await api(
        "/v1/agent-runs/" + run.id + (review ? "/decision" : "/control"),
        "POST",
        {
          expected_version: run.version,
          ...(review ? { decision: command } : { command }),
          note,
        },
      );
      setRows((items) => items.map((x) => (x.id === run.id ? result : x)));
      setCommand("");
      setNotice(
        "Run updated. Existing in-flight effects retain their dispatch boundary.",
      );
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="live-workspace ops-console"
      aria-label="Durable execution workspace"
    >
      <div className="live-hero">
        <div>
          <small>PERSISTENT EXECUTION / CONNECTED TO THE BACKEND</small>
          <h2>Run. Review. Recover.</h2>
          <p>
            Database-backed checkpoints and governed actions.{" "}
            {me.synthetic
              ? "Business tools use the local synthetic connector."
              : "Approved requests use the configured customer HTTP adapter and may create external records."}{" "}
            Autonomous model planning remains disabled.
          </p>
        </div>
        <div>
          <button
            className="btn btn-outline"
            onClick={() => {
              setError("");
              load();
            }}
          >
            <RefreshCw size={16} /> Refresh runs
          </button>
          <button
            className="btn btn-primary"
            disabled={!canEdit || busy}
            onClick={() => setCreating(true)}
          >
            <Play size={16} /> Start durable run
          </button>
        </div>
      </div>
      <Alerts error={error} notice={notice} />
      {pendingRun && (
        <div className="ops-alert" role="status">
          <p>
            An unacknowledged run intent is saved in this tab. Recover it before
            submitting different inputs.
          </p>
          <button className="btn btn-outline" disabled={busy} onClick={recover}>
            Recover pending run
          </button>
        </div>
      )}
      {loading ? (
        <p role="status">Loading persisted agent runs…</p>
      ) : !rows.length ? (
        <div className="ops-empty">
          <Play size={28} />
          <h3>No runs on this page</h3>
          <p>
            Create a supplier lookup or supervised procurement run. Keep the
            execution worker running.
          </p>
        </div>
      ) : (
        <div className="live-grid">
          <section className="live-list" aria-label="Persisted runs">
            {rows.map((r) => (
              <button
                key={r.id}
                className={run?.id === r.id ? "selected" : ""}
                onClick={() => setSelected(r.id)}
              >
                <strong>{r.name}</strong>
                <State value={r.status} />
                <small>
                  {r.cursor} / {r.steps.length} checkpoints · version{" "}
                  {r.version}
                </small>
                <small>{new Date(r.created * 1000).toLocaleString()}</small>
              </button>
            ))}
          </section>
          <article className="live-detail">
            <header>
              <div>
                <small>RUN-{run.id.slice(0, 8).toUpperCase()}</small>
                <h3>{run.name}</h3>
              </div>
              <State value={run.status} />
            </header>
            <p>
              Checkpoint {Math.min(run.cursor + 1, run.steps.length)} of{" "}
              {run.steps.length} · lease recoveries {run.recoveries}
            </p>
            {run.error && (
              <p className="ops-alert error">
                Run stopped: {run.error}. Inspect the affected step before
                retrying.
              </p>
            )}
            <ol className="live-steps">
              {run.steps.map((step: Row, i: number) => (
                <li
                  key={step.id}
                  className={step.status === "completed" ? "done" : ""}
                >
                  <span>
                    {step.status === "completed" ? (
                      <CheckCircle2 size={20} />
                    ) : (
                      i + 1
                    )}
                  </span>
                  <div>
                    <strong>{step.label}</strong>
                    <State value={step.status} />
                    <small>{step.kind.replaceAll("_", " ")}</small>
                    {step.action_id && (
                      <>
                        <p>
                          Action: {step.action_id.slice(0, 8).toUpperCase()}
                        </p>
                        <button
                          className="btn btn-outline"
                          onClick={() =>
                            onNavigate(
                              step.result?.status === "awaiting_approval"
                                ? "approvals"
                                : "executions",
                            )
                          }
                        >
                          Inspect governed action <ArrowRight size={14} />
                        </button>
                      </>
                    )}
                    {step.result?.external_ref && (
                      <p>
                        Verified external reference: {step.result.external_ref}
                      </p>
                    )}
                    {step.result?.note && <p>{step.result.note}</p>}
                  </div>
                </li>
              ))}
            </ol>
            <div className="live-actions">
              {runControls({
                status: run.status,
                can_retry: run.can_retry,
              }).map((c) => (
                <button
                  className="btn btn-outline"
                  key={c}
                  disabled={!canEdit || busy}
                  onClick={() => {
                    setCommand(c);
                    setNote("");
                    setError("");
                  }}
                >
                  {c === "retry"
                    ? "Retry unsubmitted step"
                    : c[0].toUpperCase() + c.slice(1)}
                </button>
              ))}
              {run.status === "waiting_review" &&
                canReview &&
                run.author_id !== me.user.id &&
                ["approve", "reject"].map((c) => (
                  <button
                    key={c}
                    className="btn btn-primary"
                    onClick={() => {
                      setCommand(c);
                      setNote("");
                    }}
                  >
                    {c === "approve"
                      ? "Approve checkpoint"
                      : "Reject checkpoint"}
                  </button>
                ))}
            </div>
            {run.status === "waiting_review" && (
              <p>
                Independent review expires{" "}
                {new Date(run.review_until * 1000).toLocaleString()}. Sign in as
                the reviewer to decide this checkpoint. A purchase may require a
                second policy approval in Human approvals.
              </p>
            )}
            {run.status === "outcome_unknown" && (
              <p className="ops-permission">
                Do not replay this effect. Open Execution ledger and reconcile
                the original action; the run will continue only after a verified
                result.
              </p>
            )}
            {run.status === "paused" && (
              <p>
                Pause stops future checkpoints. An already queued or dispatched
                business action can still finish.
              </p>
            )}
            {run.cancel_requested === 1 && (
              <p>
                Cancellation requested. Dispatched or uncertain effects must
                finish or be reconciled; cancellation cannot undo them.
              </p>
            )}
          </article>
        </div>
      )}
      <footer className="ops-pagination">
        <span>Page {Math.floor(offset / 20) + 1}</span>
        <button
          className="btn btn-outline"
          disabled={offset === 0}
          onClick={() => {
            setOffset(Math.max(0, offset - 20));
            setSelected("");
          }}
        >
          Previous runs
        </button>
        <button
          className="btn btn-outline"
          disabled={next === null}
          onClick={() => {
            setOffset(next!);
            setSelected("");
          }}
        >
          Next runs
        </button>
      </footer>
      {creating && (
        <Modal
          title="Start a persisted agent run"
          onClose={() => {
            if (!busy) setCreating(false);
          }}
        >
          <form onSubmit={create}>
            <p>
              This creates real database records and sends authorized work to
              {me.synthetic
                ? "the synthetic business connector"
                : "the configured customer HTTP adapter"}
              . It is separate from design studio rehearsals.{" "}
              {me.synthetic
                ? ""
                : "Approved actions can have real external effects."}
            </p>
            <label>
              Workflow
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="lookup">Supplier lookup</option>
                <option value="procurement">Supervised procurement</option>
              </select>
            </label>
            <label>
              Active requesting agent
              <select
                required
                value={agent}
                onChange={(e) => setAgent(e.target.value)}
              >
                <option value="">Select agent</option>
                {agents.map((a: Row) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Supplier reference
              {me.synthetic ? (
                <select
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                >
                  <option>SUP-DEMO-104</option>
                  <option>SUP-DEMO-205</option>
                </select>
              ) : (
                <input
                  required
                  maxLength={64}
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                  placeholder="Customer supplier reference"
                />
              )}
            </label>
            {mode === "procurement" && (
              <>
                <label>
                  Amount USD
                  <input
                    required
                    inputMode="decimal"
                    pattern="[0-9]+\.[0-9]{2}"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </label>
                <label>
                  Purchase purpose
                  <textarea
                    required
                    minLength={3}
                    maxLength={300}
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                  />
                </label>
                <p>
                  Supplier lookup → independent workflow review → purchase
                  policy evaluation → execution verification. The requester
                  cannot approve their own checkpoints.
                </p>
              </>
            )}
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <footer>
              <button
                className="btn btn-outline"
                type="button"
                disabled={busy}
                onClick={() => setCreating(false)}
              >
                Cancel
              </button>
              <button className="btn btn-primary" disabled={busy || !agent}>
                {busy ? "Saving run…" : "Create and queue run"}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {command && run && (
        <Modal
          title={command + " · " + run.name}
          onClose={() => {
            if (!busy) setCommand("");
          }}
        >
          <form onSubmit={act}>
            <p>
              Current state: {run.status.replaceAll("_", " ")} · version{" "}
              {run.version}. A stale request will be rejected.
            </p>
            <p>
              {command === "cancel"
                ? "Cancel future checkpoints. Queued work is cancelled where possible; dispatched or uncertain effects are preserved for reconciliation."
                : command === "pause"
                  ? "Stop future checkpoints. This does not retract a business action already dispatched."
                  : "Review the run and its current checkpoint before continuing."}
            </p>
            <label>
              Operator / decision note
              <textarea
                required
                minLength={5}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <footer>
              <button
                className="btn btn-outline"
                type="button"
                disabled={busy}
                onClick={() => setCommand("")}
              >
                Keep current state
              </button>
              <button className="btn btn-primary" disabled={busy}>
                Confirm {command}
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </section>
  );
}

export function DocumentLibrary({ me }: { me: Row }) {
  const [rows, setRows] = useState<Row[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [detail, setDetail] = useState<Row | null>(null),
    [query, setQuery] = useState(""),
    [onePerDocument, setOnePerDocument] = useState(false),
    [searchMethod, setSearchMethod] = useState(
      "ACL-filtered BM25-style lexical ranking",
    ),
    [results, setResults] = useState<Row[] | null>(null),
    [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null),
    [uploading, setUploading] = useState(false),
    [replacing, setReplacing] = useState<Row | null>(null),
    [updateIntent, setUpdateIntent] =
      useState<ReturnType<typeof pendingIntent>>(null),
    [filename, setFilename] = useState(""),
    [title, setTitle] = useState(""),
    [content, setContent] = useState(""),
    [language, setLanguage] = useState("English"),
    [roles, setRoles] = useState<string[]>([]),
    [managing, setManaging] = useState(""),
    [note, setNote] = useState(""),
    [leave, setLeave] = useState(false);
  const scope = liveIntentScope("document", me.user.org_id, me.user.id, me.environment);
  const [pendingUpload, setPendingUpload] = useState(() =>
    pendingIntent(scope),
  );
  const pending = useRef<() => void>(() => {}),
    canEdit = me.permissions?.includes("operate");
  const updateScope =
    liveIntentScope("document-update", me.user.org_id, me.user.id, me.environment) +
    ":" +
    (detail?.id || "none");
  useEffect(() => {
    setUpdateIntent(pendingIntent(updateScope));
  }, [updateScope]);
  const dirty = uploading && Boolean(content);
  useEffect(() => {
    if (!dirty) return;
    const stop = registerNavigationGuard((next) => {
      pending.current = next;
      setLeave(true);
    });
    const unload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", unload);
    return () => {
      stop();
      window.removeEventListener("beforeunload", unload);
    };
  }, [dirty]);
  async function load() {
    try {
      const r = await api("/v1/documents?offset=" + offset + "&limit=20");
      setRows(r.items);
      setNext(r.next_offset);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, [offset]);
  async function choose(file?: File) {
    if (!file) return;
    try {
      intakeMetadata(file);
      const bytes = new Uint8Array(await file.arrayBuffer());
      new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      let binary = "";
      for (const b of bytes) binary += String.fromCharCode(b);
      setContent(btoa(binary));
      setFilename(file.name);
      setTitle(file.name.replace(/\.[^.]+$/, ""));
      setError("");
    } catch (e) {
      setContent("");
      setError((e as Error).message);
    }
  }
  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!content) return;
    setBusy(true);
    setError("");
    try {
      const body = replacing
        ? {
            title,
            filename,
            content_base64: content,
            language,
            expected_version: replacing.version,
            note,
          }
        : {
            title,
            filename,
            content_base64: content,
            language,
            allowed_roles: roles,
            allowed_users: [],
          };
      const created = await sendLiveIntent<
        Row & { id: string; status: string }
      >(sessionStorage, replacing ? updateScope : scope, body, (key) =>
        api(
          replacing
            ? "/v1/documents/" + replacing.id + "/content"
            : "/v1/documents",
          replacing ? "PUT" : "POST",
          body,
          key,
        ),
      );
      if (replacing) setUpdateIntent(null);
      else setPendingUpload(null);
      setUploading(false);
      setReplacing(null);
      setResults(null);
      setContent("");
      setNotice(
        replacing
          ? "Source replaced and reindexed. Access grants preserved; prior citations require a fresh search."
          : "Document persisted, chunked and indexed for authorized lexical retrieval.",
      );
      setOffset(0);
      await load();
      await inspect(created.id);
    } catch (e) {
      if (replacing) setUpdateIntent(pendingIntent(updateScope));
      else setPendingUpload(pendingIntent(scope));
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recover() {
    if (!pendingUpload) return;
    setBusy(true);
    try {
      const d = await api("/v1/documents/recover", "POST", {
        key: pendingUpload.key,
      });
      acknowledgeRecovery(sessionStorage, scope, pendingUpload, d);
      setPendingUpload(null);
      setNotice("Original upload recovered; current state: " + d.status + ".");
      await load();
      if (d.status === "indexed") await inspect(d.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recoverUpdate() {
    if (!detail || !updateIntent) return;
    setBusy(true);
    try {
      const receipt = await api(
        "/v1/documents/" + detail.id + "/updates/recover",
        "POST",
        { key: updateIntent.key },
      );
      acknowledgeRecovery(sessionStorage, updateScope, updateIntent, receipt);
      setUpdateIntent(null);
      setNotice(
        "Update acknowledged at version " +
          receipt.version +
          "; current source version " +
          receipt.current_version +
          ". No content was submitted again.",
      );
      await inspect(detail.id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function verifyCitation(citation: Row) {
    try {
      await api(
        "/v1/documents/" +
          citation.document_id +
          "/citations/" +
          citation.document_version +
          "/" +
          citation.chunk,
      );
      const source = await inspect(citation.document_id);
      if (source && source.version === citation.document_version)
        setNotice(
          "Citation verified against the current source version and your current access.",
        );
      else {
        setResults(null);
        setNotice("");
        if (source)
          setError(
            "The source changed during inspection. Search again for a current citation.",
          );
      }
    } catch (e) {
      setError((e as Error).message);
      setDetail(null);
      setResults(null);
    }
  }
  async function inspect(id: string) {
    try {
      const source = await api("/v1/documents/" + id);
      setDetail(source);
      setError("");
      return source;
    } catch (e) {
      setError((e as Error).message);
      setDetail(null);
    }
  }
  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api(
        "/v1/documents/search?q=" +
          encodeURIComponent(query) +
          "&top_k=10" +
          (onePerDocument ? "&one_per_document=true" : ""),
      );
      setResults(r.items);
      setSearchMethod(r.method || "ACL-filtered lexical ranking");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function manage(e: React.FormEvent) {
    e.preventDefault();
    if (!detail) return;
    setBusy(true);
    setError("");
    try {
      if (managing === "delete") {
        await api("/v1/documents/" + detail.id, "DELETE", {
          expected_version: detail.version,
          note,
        });
        setDetail(null);
        setResults(null);
        setNotice(
          "Document content and chunks were removed from active retrieval.",
        );
      } else {
        await api("/v1/documents/" + detail.id + "/access", "PUT", {
          expected_version: detail.version,
          allowed_roles: roles,
          allowed_users: detail.allowed_users,
          note,
        });
        setResults(null);
        setNotice(
          "Document access updated. New searches use the current ACL; prior citations are stale.",
        );
        await inspect(detail.id);
      }
      setManaging("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function rolePicker() {
    return (
      <fieldset className="live-role-options">
        <legend>Additional reader roles</legend>
        {["engineer", "approver", "auditor"].map((role) => (
          <label key={role}>
            <input
              type="checkbox"
              checked={roles.includes(role)}
              onChange={(e) =>
                setRoles(
                  e.target.checked
                    ? [...roles, role]
                    : roles.filter((r) => r !== role),
                )
              }
            />
            {role}
          </label>
        ))}
        <p>
          The author and organization owner/security administrators retain
          access. Others require an explicit role or user grant.
        </p>
      </fieldset>
    );
  }
  return (
    <section
      className="live-workspace ops-console"
      aria-label="Document library workspace"
    >
      <div className="live-hero">
        <div>
          <small>PERSISTED DOCUMENTS / ACCESS-CONTROLLED RETRIEVAL</small>
          <h2>Knowledge with an access boundary.</h2>
          <p>
            Upload text directly, or use the file queue below for PDF, DOCX and
            configured image OCR. Review extracted evidence before publication.
            Search authorized chunks with citations; semantic search and
            generated answers remain separate work.
          </p>
        </div>
        <button
          className="btn btn-primary"
          disabled={!canEdit || busy}
          onClick={() => {
            setReplacing(null);
            setUploading(true);
            setContent("");
            setFilename("");
            setTitle("");
            setRoles([]);
            setError("");
          }}
        >
          <Upload size={16} /> Upload text document
        </button>
      </div>
      <Alerts error={error} notice={notice} />
      {pendingUpload && (
        <div className="ops-alert" role="status">
          <p>
            An unacknowledged upload intent is saved in this tab. File contents
            were not stored in browser storage.
          </p>
          <button className="btn btn-outline" disabled={busy} onClick={recover}>
            Recover pending upload
          </button>
        </div>
      )}
      <Suspense fallback={<p role="status">Loading document intake…</p>}>
        <IntakeQueue
          me={me}
          onPublished={(id) => {
            inspect(id);
            load();
          }}
        />
      </Suspense>
      <form className="live-search" onSubmit={search}>
        <label className="ops-search">
          <Search size={18} />
          <input
            required
            minLength={2}
            maxLength={1000}
            aria-label="Search authorized document text"
            placeholder="Search your authorized evidence…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="live-search-diversity">
          <input
            type="checkbox"
            checked={onePerDocument}
            disabled={busy}
            onChange={(e) => setOnePerDocument(e.target.checked)}
          />
          One result per document
        </label>
        <button className="btn btn-primary" disabled={busy}>
          Search documents
        </button>
        <button
          className="btn btn-outline"
          type="button"
          onClick={() => {
            setResults(null);
            setQuery("");
          }}
        >
          Clear results
        </button>
      </form>
      {results !== null && (
        <section aria-label="Authorized search results">
          <h3>{results.length} matching chunks</h3>
          <p>{searchMethod} · no provider request.</p>
          {!results.length ? (
            <div className="ops-empty">
              No authorized text matched this query.
            </div>
          ) : (
            results.map((r: Row) => (
              <article className="live-citation" key={r.citation}>
                <header>
                  <strong>{r.title}</strong>
                  <small>
                    Score {r.score} · version {r.document_version}
                  </small>
                </header>
                <p>{r.excerpt}</p>
                <code>{r.citation}</code>
                <button
                  className="btn btn-outline"
                  onClick={() => verifyCitation(r)}
                >
                  Verify citation and inspect <ArrowRight size={15} />
                </button>
              </article>
            ))
          )}
        </section>
      )}
      <div className="live-grid">
        <section className="live-list" aria-label="Authorized documents">
          {loading ? (
            <p role="status">Loading authorized documents…</p>
          ) : !rows.length ? (
            <div className="ops-empty">
              <BookOpen size={28} />
              <h3>No documents in this view</h3>
              <p>Upload evidence or ask its owner for access.</p>
            </div>
          ) : (
            rows.map((d) => (
              <button
                key={d.id}
                className={detail?.id === d.id ? "selected" : ""}
                onClick={() => inspect(d.id)}
              >
                <strong>{d.title}</strong>
                <small>
                  {d.filename} · {d.byte_count.toLocaleString()} bytes ·{" "}
                  {d.language}
                </small>
                <small>
                  Version {d.version} ·{" "}
                  {d.allowed_roles.length
                    ? "Shared roles: " + d.allowed_roles.join(", ")
                    : "Author and administrators only"}
                </small>
              </button>
            ))
          )}
        </section>
        <article className="live-detail">
          {detail ? (
            <>
              <header>
                <div>
                  <small>AUTHORIZED SOURCE</small>
                  <h3>{detail.title}</h3>
                </div>
                <State value={detail.status} />
              </header>
              <p>
                {detail.filename} · {detail.byte_count.toLocaleString()} bytes ·
                version {detail.version}
              </p>
              <code className="live-hash">SHA-256 {detail.content_hash}</code>
              {detail.provenance && (
                <div className="ops-alert">
                  <strong>Reviewed file extraction</strong>
                  <p>
                    {detail.provenance.original_filename} ·{" "}
                    {detail.provenance.extraction.method} · original bytes{" "}
                    {detail.provenance.original_bytes} · published version{" "}
                    {detail.provenance.published_version}
                  </p>
                  <code className="live-hash">
                    Original SHA-256 {detail.provenance.original_sha256}
                  </code>
                  {!detail.provenance.current_version_matches && (
                    <p>
                      The current content or permissions changed after this
                      initial publication.
                    </p>
                  )}
                </div>
              )}
              {updateIntent && (
                <div className="ops-alert">
                  <p>
                    An unacknowledged content update is saved for this source.
                    Recover it before replacing it again.
                  </p>
                  <button
                    className="btn btn-outline"
                    disabled={busy}
                    onClick={recoverUpdate}
                  >
                    Recover pending update
                  </button>
                </div>
              )}
              <pre className="live-document">{detail.content}</pre>
              <div className="live-actions">
                {canEdit && detail.can_manage && (
                  <>
                    <button
                      className="btn btn-outline"
                      onClick={() => {
                        setRoles(detail.allowed_roles);
                        setManaging("access");
                        setNote("");
                      }}
                    >
                      <ShieldCheck size={16} /> Manage access
                    </button>
                    <button
                      className="btn btn-outline"
                      onClick={() => {
                        setReplacing(detail);
                        setUploading(true);
                        setContent("");
                        setFilename("");
                        setTitle(detail.title);
                        setLanguage(detail.language);
                        setNote("");
                        setError("");
                      }}
                    >
                      Replace content
                    </button>
                    <button
                      className="btn btn-outline"
                      onClick={() => {
                        setManaging("delete");
                        setNote("");
                      }}
                    >
                      Delete document
                    </button>
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="ops-empty">
              <FileText size={30} />
              <h3>Inspect an authorized source</h3>
              <p>
                Choose a document or citation to read its stored content and
                version.
              </p>
            </div>
          )}
        </article>
      </div>
      <footer className="ops-pagination">
        <span>Page {Math.floor(offset / 20) + 1}</span>
        <button
          className="btn btn-outline"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 20))}
        >
          Previous documents
        </button>
        <button
          className="btn btn-outline"
          disabled={next === null}
          onClick={() => setOffset(next!)}
        >
          Next documents
        </button>
      </footer>
      <Suspense
        fallback={<p role="status">Loading retrieval quality tools…</p>}
      >
        <RetrievalQuality me={me} documents={rows} />
      </Suspense>
      {uploading && (
        <Modal
          title={
            replacing
              ? "Replace and reindex source content"
              : "Upload and index a UTF-8 document"
          }
          onClose={() => {
            if (!busy) {
              if (content) {
                pending.current = () => {
                  setUploading(false);
                  setContent("");
                };
                setLeave(true);
              } else setUploading(false);
            }
          }}
        >
          <form onSubmit={upload}>
            <label>
              Document file
              <input
                type="file"
                accept=".txt,.md,.csv,.json"
                onChange={(e) => choose(e.target.files?.[0])}
              />
            </label>
            <label>
              Document title
              <input
                required
                minLength={2}
                maxLength={120}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              Language
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option>English</option>
                <option>Arabic</option>
                <option>Bilingual</option>
              </select>
            </label>
            {replacing ? (
              <>
                <p>
                  Replacing version {replacing.version}. Existing reader
                  permissions are preserved. Old chunks are replaced atomically;
                  previous content is not retained as a readable version.
                </p>
                <label>
                  Content update note
                  <textarea
                    required
                    minLength={5}
                    maxLength={500}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
              </>
            ) : (
              rolePicker()
            )}
            <p>
              {filename || "No file selected"}. File content is submitted to
              your configured backend and stored in its database. Keep
              confidential data within your approved deployment.
            </p>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <footer>
              <button className="btn btn-primary" disabled={busy || !content}>
                {busy
                  ? "Indexing document…"
                  : replacing
                    ? "Replace and reindex document"
                    : "Upload and index document"}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {managing && detail && (
        <Modal
          title={
            managing === "delete"
              ? "Delete this document?"
              : "Manage document readers"
          }
          onClose={() => {
            if (!busy) setManaging("");
          }}
        >
          <form onSubmit={manage}>
            {managing === "access" ? (
              rolePicker()
            ) : (
              <p>
                Content and chunks will be removed from active storage and
                search. Metadata and audit evidence remain. Backup/WAL erasure
                is a deployment responsibility.
              </p>
            )}
            <label>
              Access / deletion note
              <textarea
                required
                minLength={5}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <footer>
              <button
                className="btn btn-outline"
                type="button"
                disabled={busy}
                onClick={() => setManaging("")}
              >
                Cancel
              </button>
              <button className="btn btn-primary" disabled={busy}>
                Confirm {managing === "delete" ? "deletion" : "access change"}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {leave && (
        <Modal
          title="Discard the selected document draft?"
          onClose={() => setLeave(false)}
        >
          <p>
            The file has not been uploaded. Keep editing or discard the draft
            before leaving.
          </p>
          <footer>
            <button className="btn btn-outline" onClick={() => setLeave(false)}>
              Keep editing
            </button>
            <button
              className="btn btn-primary"
              onClick={() => {
                setLeave(false);
                pending.current();
              }}
            >
              Discard draft and continue
            </button>
          </footer>
        </Modal>
      )}
    </section>
  );
}
