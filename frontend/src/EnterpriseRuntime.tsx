import { IdentityBindingAdmin } from "./IdentityBindingAdmin";
import { useEffect, useState } from "react";
import { api } from "./api";
import { Modal } from "./RuntimeDialog";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { IndexedSearchReview } from "./IndexedSearchReview";
import { LocalReranking } from "./LocalReranking";
import { IndexCollections } from "./IndexCollections";
import { BackgroundIndexJobs } from "./BackgroundIndexJobs";
import { NeuralIndexPanel } from "./NeuralIndexPanel";
import { hybridSearchRequest } from "./hybridSearchRequest";
import "./live.css";
import "./enterpriseRuntime.css";
type Row = Record<string, any>;
const message = (e: unknown) =>
  e instanceof Error ? e.message : "The request could not be completed.";
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
function useIntent(me: Row, kind: "member" | "hybrid-search") {
  const scope = liveIntentScope(
    kind,
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  const recover = async (path: string) => {
    const pending = readRecovery(sessionStorage, scope);
    if (!pending)
      throw Error("There is no unacknowledged submission for this account.");
    const result = await api(path, "POST", { key: pending.key });
    acknowledgeRecovery(sessionStorage, scope, pending, result);
    return result;
  };
  return { scope, recover };
}
export function HybridRetrieval({ me }: { me: Row }) {
  const [docs, setDocs] = useState<Row[]>([]),
    [history, setHistory] = useState<Row[]>([]),
    [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [query, setQuery] = useState(""),
    [weight, setWeight] = useState(0.6),
    [dimensions, setDimensions] = useState(8),
    [threshold, setThreshold] = useState(0.15),
    [top, setTop] = useState(5),
    [onePerDocument, setOnePerDocument] = useState(false),
    [collectionChoice, setCollectionChoice] = useState<{
      ids: string[];
      nonce: number;
    }>({ ids: [], nonce: 0 }),
    [neural, setNeural] = useState(false),
    [neuralAvailable, setNeuralAvailable] = useState(false),
    [neuralModel, setNeuralModel] = useState(""),
    [neuralDigest, setNeuralDigest] = useState(""),
    [result, setResult] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const intent = useIntent(me, "hybrid-search");
  async function refresh(at = offset) {
    const [h] = await Promise.all([
      api(`/v1/hybrid-search/history?offset=${at}&limit=10`),
    ]);
    setHistory(h.items);
    setNext(h.next_offset);
    setOffset(at);
  }
  async function load() {
    try {
      const capabilities = await api("/v1/hybrid-search/capabilities");
      setNeuralAvailable(capabilities.neural_embeddings === true);
      setNeuralModel(capabilities.neural_model || "");
      setNeuralDigest(capabilities.neural_model_digest || "");
      if (capabilities.neural_embeddings !== true) setNeural(false);
      const all: Row[] = [];
      let at: number | null = 0;
      while (at !== null) {
        const d: Row = await api(`/v1/documents?offset=${at}&limit=50`);
        all.push(...d.items);
        at = d.next_offset ?? null;
        if (all.length >= 200) break;
      }
      setDocs(all);
      await refresh();
    } catch (e) {
      setError(message(e));
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function act(job: () => Promise<Row>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const r = await job();
      setResult(r);
      setNotice(
        r.status === "completed"
          ? "Search completed. Excerpts are checked against current source access."
          : `Search ${r.status}. ${r.error_code || "Refresh history to check progress."}`,
      );
      await refresh(0);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="live-workspace enterprise-runtime"
      aria-label="Live hybrid document retrieval"
    >
      <div className="live-hero">
        <div>
          <p className="eyebrow">CONNECTED RUNTIME</p>
          <h2>Find evidence across your documents</h2>
          <p>
            Choose default LSA/BM25 search or operator-enabled local neural
            similarity. Results are source excerpts with versioned citations.
          </p>
          <p>
            LSA/BM25 search normalizes common Arabic spelling variants. Neural
            language behavior depends on the selected model. Read the original
            excerpt.
          </p>
        </div>
      </div>
      <div className="ops-alert">
        Bounded local search: up to 20 documents. Default LSA supports 128
        chunks; opt-in neural search supports 32 passages and a pinned local
        model. Stored indexes are available below after operator setup. No
        generated answers. Scores are not confidence.
      </div>
      <Alerts error={error} notice={notice} />
      <div className="live-grid">
        <form
          className="panel runtime-card"
          onSubmit={(e) => {
            e.preventDefault();
            const body = hybridSearchRequest({
              neural,
              query,
              sources: docs
                .filter((d) => selected.includes(d.id))
                .map((d) => ({ id: d.id, version: d.version })),
              dimensions,
              weight,
              threshold,
              top,
              onePerDocument,
            });
            void act(() =>
              sendLiveIntent(sessionStorage, intent.scope, body, (key) =>
                api("/v1/hybrid-search", "POST", body, key),
              ),
            );
          }}
        >
          <h3>Search setup</h3>
          <label className="field">
            <span>Search method</span>
            <select
              value={neural ? "local_neural" : "local_lsa"}
              disabled={busy}
              onChange={(e) => setNeural(e.target.value === "local_neural")}
            >
              <option value="local_lsa">LSA and keyword ranking</option>
              <option value="local_neural" disabled={!neuralAvailable}>
                Local neural similarity
                {!neuralAvailable ? " — operator setup required" : ""}
              </option>
            </select>
          </label>
          {neural && (
            <p>
              Configured local model: {neuralModel}. This search sends
              authorized text to local Ollama; model quality has not been
              accepted.
            </p>
          )}
          <label className="runtime-check">
            <input
              type="checkbox"
              checked={onePerDocument}
              disabled={busy}
              onChange={(e) => setOnePerDocument(e.target.checked)}
            />
            <span>
              One result per document
              <small>
                Keep the highest-ranked qualifying chunk from each document.
                This can return fewer results than requested.
              </small>
            </span>
          </label>
          <label className="field">
            <span>Evidence question or search terms</span>
            <textarea
              required
              maxLength={500}
              value={query}
              disabled={busy}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Find supplier approval requirements"
            />
          </label>
          <fieldset disabled={busy}>
            <legend>Sources · {selected.length}/20 selected</legend>
            <p>
              Leave unselected to search all authorized indexed documents within
              the limits. The directory shows up to 200 visible records.
            </p>
            <div className="runtime-source-list">
              {docs.map((d) => (
                <label key={d.id} className="runtime-check">
                  <input
                    type="checkbox"
                    checked={selected.includes(d.id)}
                    disabled={
                      d.status !== "indexed" ||
                      (!selected.includes(d.id) && selected.length >= 20)
                    }
                    onChange={(e) =>
                      setSelected((s) =>
                        e.target.checked
                          ? [...s, d.id]
                          : s.filter((id) => id !== d.id),
                      )
                    }
                  />
                  <span>
                    {d.title}{" "}
                    <small>
                      v{d.version} · {d.status}
                    </small>
                  </span>
                </label>
              ))}
              {!docs.length && (
                <p>
                  No visible documents. Add indexed documents in Document
                  intelligence first.
                </p>
              )}
            </div>
          </fieldset>
          <div className="runtime-fields">
            <label className="field">
              <span>Latent dimensions (1–32)</span>
              <input
                type="number"
                min={1}
                max={32}
                required
                value={dimensions}
                disabled={neural}
                onChange={(e) => setDimensions(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>Semantic weight (0–1)</span>
              <input
                type="number"
                min={0}
                max={1}
                step="0.05"
                required
                value={weight}
                disabled={neural}
                onChange={(e) => setWeight(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>Minimum score (0–1)</span>
              <input
                type="number"
                min={0}
                max={1}
                step="0.05"
                required
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>Maximum results (1–10)</span>
              <input
                type="number"
                min={1}
                max={10}
                required
                value={top}
                onChange={(e) => setTop(Number(e.target.value))}
              />
            </label>
          </div>
          <div className="live-actions">
            <button
              className="btn btn-primary"
              disabled={busy || !query.trim()}
            >
              {busy ? "Searching…" : "Search evidence"}
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() =>
                void act(() => intent.recover("/v1/hybrid-search/recover"))
              }
            >
              Recover submission
            </button>
          </div>
          <p className="muted">
            The query is processed transiently and is not saved as text in
            search history. Source excerpts already belong to your document
            workspace.
          </p>
        </form>
        <section className="panel runtime-card" aria-live="polite">
          <h3>Ranked evidence</h3>
          {!result && <p>Run a search or open a saved receipt.</p>}
          {result && (
            <>
              <p>
                <strong>{result.status}</strong> · {result.duration_ms} ms ·{" "}
                {result.source_count} sources · {result.corpus_chunks} chunks ·{" "}
                {result.index_count ? `${result.index_count} indexes · ` : ""}
                {["local_neural", "local_indexed"].includes(
                  result.parameters?.retrieval_mode,
                )
                  ? "neural similarity"
                  : `rank ${result.rank}`}
              </p>
              {result.error_code && <p role="alert">{result.error_code}</p>}
              <p>{result.method}</p>
              {result.parameters?.reranking && (
                <p>
                  Passage order from {result.parameters.reranking.rerank_model}.
                  Original similarity scores are retained and may no longer
                  descend in this order. Reranking HTTP calls{" "}
                  {result.provider_calls ?? "unknown"}; original search HTTP
                  calls {result.parent_provider_calls ?? "unknown"}.
                  <code className="live-hash">
                    Reranking digest {result.parameters.reranking.rerank_digest}
                  </code>
                </p>
              )}
              {["local_neural", "local_indexed"].includes(
                result.parameters?.retrieval_mode,
              ) && (
                <p>
                  Model {result.parameters.embedding_model} ·{" "}
                  {result.embedding_dimensions} embedding dimensions · local
                  HTTP requests {result.provider_calls ?? "unconfirmed"}
                  <code className="live-hash">
                    Model digest {result.parameters.embedding_digest}
                  </code>
                </p>
              )}
              <p>
                {result.parameters?.one_per_document === true
                  ? "Recorded mode: one result per document."
                  : "Recorded mode: multiple chunks per document allowed."}
              </p>
              {result.normalization_current === false && (
                <p role="status">
                  This saved search used an earlier text-matching method. Run a
                  new search to use the current retrieval method.
                </p>
              )}
              {result.items?.map((hit: Row) => (
                <article className="runtime-hit" key={hit.citation}>
                  <h4>
                    {hit.rerank_position
                      ? `Model order ${hit.rerank_position}: `
                      : ""}
                    {hit.title}
                  </h4>
                  <p className="runtime-citation">{hit.citation}</p>
                  <p className="runtime-excerpt">{hit.excerpt}</p>
                  <dl>
                    <dt>
                      {["local_neural", "local_indexed"].includes(
                        result.parameters?.retrieval_mode,
                      )
                        ? "Neural similarity"
                        : "Combined score"}
                    </dt>
                    <dd>{hit.score.toFixed(3)}</dd>
                    <dt>Semantic similarity</dt>
                    <dd>{hit.semantic_score.toFixed(3)}</dd>
                    <dt>Keyword score</dt>
                    <dd>
                      {["local_neural", "local_indexed"].includes(
                        result.parameters?.retrieval_mode,
                      )
                        ? "Not used"
                        : hit.lexical_score.toFixed(3)}
                    </dd>
                  </dl>
                </article>
              ))}
              {result.status === "completed" && !result.items?.length && (
                <p>
                  No authorized evidence met the threshold. Try a narrower query
                  or lower minimum score.
                </p>
              )}
              {result.withheld_stale_or_inaccessible > 0 && (
                <p>
                  {result.withheld_stale_or_inaccessible} saved hits withheld
                  because source access or revision changed.
                </p>
              )}
            </>
          )}
        </section>
      </div>
      <IndexCollections
        me={me}
        sources={docs
          .filter((d) => selected.includes(d.id))
          .map((d) => ({ id: d.id, version: d.version }))}
        enabled={neuralAvailable}
        model={neuralModel}
        digest={neuralDigest}
        onSelect={(ids) =>
          setCollectionChoice((previous) => ({
            ids,
            nonce: previous.nonce + 1,
          }))
        }
      />
      <BackgroundIndexJobs
        me={me}
        sources={docs
          .filter((d) => selected.includes(d.id))
          .map((d) => ({ id: d.id, version: d.version }))}
        enabled={neuralAvailable}
      />
      <NeuralIndexPanel
        selection={collectionChoice}
        me={me}
        sources={docs
          .filter((d) => selected.includes(d.id))
          .map((d) => ({ id: d.id, version: d.version }))}
        enabled={neuralAvailable}
        model={neuralModel}
        digest={neuralDigest}
        onSearch={(row) => {
          setResult(row);
          void refresh(0).catch((e) => setError(message(e)));
        }}
      />
      <LocalReranking
        me={me}
        run={result}
        onResult={(row) => {
          setResult(row);
          void refresh(0).catch((e) => setError(message(e)));
        }}
      />
      <IndexedSearchReview me={me} run={result} documents={docs} />
      <section className="panel runtime-card">
        <div className="live-actions">
          <h3>Search receipts</h3>
          <button
            className="btn"
            disabled={busy}
            onClick={() => void refresh().catch((e) => setError(message(e)))}
          >
            Refresh history
          </button>
        </div>
        <div className="runtime-history">
          {history.map((h) => (
            <button
              className="btn"
              key={h.id}
              disabled={busy}
              onClick={() =>
                void act(() =>
                  api("/v1/hybrid-search/history/" + encodeURIComponent(h.id)),
                )
              }
            >
              {h.status} · {new Date(h.created * 1000).toLocaleString()} ·{" "}
              {h.items.length} visible hits
            </button>
          ))}
        </div>
        <div className="live-actions">
          <button
            className="btn"
            disabled={busy || offset === 0}
            onClick={() =>
              void refresh(Math.max(0, offset - 10)).catch((e) =>
                setError(message(e)),
              )
            }
          >
            Previous
          </button>
          <span>
            Receipts {history.length ? offset + 1 : 0}–{offset + history.length}
          </span>
          <button
            className="btn"
            disabled={busy || next === null}
            onClick={() =>
              void refresh(next!).catch((e) => setError(message(e)))
            }
          >
            Next
          </button>
        </div>
      </section>
    </section>
  );
}
export function MemberAdmin({ me }: { me: Row }) {
  const owner = me.user.role === "owner";
  const [directory, setDirectory] = useState<Row>({ items: [] }),
    [sessions, setSessions] = useState<Row[]>([]),
    [modal, setModal] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [note, setNote] = useState(""),
    [reviewed, setReviewed] = useState(false),
    [name, setName] = useState(""),
    [email, setEmail] = useState(""),
    [role, setRole] = useState("engineer"),
    [subject, setSubject] = useState("");
  const intent = useIntent(me, "member");
  async function refresh() {
    const s = await api("/v1/my-sessions");
    setSessions(s.items);
    if (owner) setDirectory(await api("/v1/member-admin"));
  }
  useEffect(() => {
    void refresh().catch((e) => setError(message(e)));
  }, []);
  function open(value: Row) {
    setModal(value);
    setNote("");
    setReviewed(false);
    setRole(value.member?.role || "engineer");
    setError("");
  }
  async function act(job: () => Promise<Row>) {
    setBusy(true);
    setError("");
    try {
      const r = await job();
      setNotice(
        r.status === "provisioned"
          ? "Member provisioned. No invitation or password was sent. In local mode, set the password privately using the backend CLI."
          : `Access updated. ${r.sessions_revoked ?? 0} sessions revoked.`,
      );
      setModal(null);
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  function submit() {
    if (!modal) return;
    if (modal.type === "provision") {
      const body = { name, email, role, oidc_subject: subject, note, reviewed };
      void act(() =>
        sendLiveIntent(sessionStorage, intent.scope, body, (key) =>
          api("/v1/member-admin", "POST", body, key),
        ),
      );
    } else if (modal.type === "sessions") {
      void act(() => api("/v1/my-sessions/revoke-others", "POST", { note }));
    } else {
      void act(() =>
        api(
          `/v1/member-admin/${encodeURIComponent(modal.member.id)}/change`,
          "POST",
          {
            command: modal.command,
            expected_revision: modal.member.revision,
            role,
            note,
            reviewed,
          },
        ),
      );
    }
  }
  return (
    <section
      className="enterprise-runtime live-workspace"
      aria-label="Account and session administration"
    >
      <Alerts error={!modal ? error : ""} notice={notice} />
      <IdentityBindingAdmin me={me} onChanged={refresh} />
      {owner && (
        <section className="panel runtime-card">
          <div className="live-actions">
            <div>
              <h2>Workspace access</h2>
              <p>
                Owner-controlled provisioning, roles and offboarding. Every
                access change revokes the target member’s sessions.
              </p>
            </div>
            <button
              className="btn btn-primary"
              disabled={busy}
              onClick={() => open({ type: "provision" })}
            >
              Provision member
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() =>
                void act(() =>
                  intent.recover("/v1/member-admin/provision/recover"),
                )
              }
            >
              Recover provisioning
            </button>
            <button
              className="btn"
              disabled={busy}
              onClick={() => void refresh().catch((e) => setError(message(e)))}
            >
              Refresh directory
            </button>
          </div>
          <div className="runtime-table">
            <table>
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Role / access</th>
                  <th>Sessions</th>
                  <th>Manage</th>
                </tr>
              </thead>
              <tbody>
                {directory.items.map((u: Row) => (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.name}</strong>
                      <br />
                      {u.email}
                    </td>
                    <td>
                      {u.role} · {u.active ? "Active" : "Inactive"}
                      <br />
                      {u.oidc_bound ? "IdP subject bound" : "Local identity"}
                    </td>
                    <td>{u.active_sessions}</td>
                    <td>
                      {u.id === me.user.id || u.role === "owner" ? (
                        <span>Owner protected</span>
                      ) : (
                        <div className="live-actions">
                          {[
                            ["set_role", "Change role"],
                            [
                              u.active ? "deactivate" : "activate",
                              u.active ? "Deactivate" : "Activate",
                            ],
                            ["revoke_sessions", "Revoke sessions"],
                          ].map(([command, label]) => (
                            <button
                              key={command}
                              className="btn"
                              disabled={busy}
                              onClick={() =>
                                open({
                                  type: "change",
                                  command,
                                  member: u,
                                  label,
                                })
                              }
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            Up to 200 members. No invitation delivery, SCIM provisioning, SAML
            or owner transfer. SSO accounts require an exact subject supplied by
            your trusted identity administrator.
          </p>
        </section>
      )}
      <section className="panel runtime-card">
        <div className="live-actions">
          <div>
            <h2>Your active sessions</h2>
            <p>
              Revocation keeps this browser signed in. Device and location data
              are not collected.
            </p>
          </div>
          <button
            className="btn"
            disabled={busy || !sessions.some((s) => !s.current)}
            onClick={() => open({ type: "sessions" })}
          >
            Sign out other sessions
          </button>
        </div>
        {sessions.map((s) => (
          <p key={s.handle}>
            <strong>{s.current ? "This browser" : "Other session"}</strong> ·
            Expires {new Date(s.expires * 1000).toLocaleString()} ·{" "}
            <code>{s.handle}</code>
          </p>
        ))}
      </section>
      {modal && (
        <Modal
          title={
            modal.type === "provision"
              ? "Provision workspace member"
              : modal.type === "sessions"
                ? "Revoke your other sessions"
                : modal.label
          }
          onClose={() => {
            if (!busy) setModal(null);
          }}
        >
          <Alerts error={error} notice="" />
          <form
            className="runtime-form"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <fieldset disabled={busy}>
              {modal.type === "provision" && (
                <>
                  <label className="field">
                    <span>Full name</span>
                    <input
                      required
                      minLength={2}
                      maxLength={100}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Account email</span>
                    <input
                      type="email"
                      required
                      maxLength={254}
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </label>
                  {directory.oidc_configured && (
                    <label className="field">
                      <span>Exact trusted IdP subject</span>
                      <input
                        required
                        maxLength={200}
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                      />
                    </label>
                  )}
                  <p>
                    No invitation email or password is issued. Local development
                    password setup:{" "}
                    <code>
                      python -m nexus.cli set-local-password --email
                      member@example.com
                    </code>{" "}
                    from the backend terminal. SSO accounts must exist at the
                    configured IdP.
                  </p>
                </>
              )}
              {(modal.type === "provision" || modal.command === "set_role") && (
                <label className="field">
                  <span>Role</span>
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                  >
                    {["engineer", "approver", "auditor", "security"].map(
                      (r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              )}
              {modal.member && (
                <p>
                  {modal.member.name} · {modal.member.email}. This change
                  invalidates all of this member’s sessions. A stale directory
                  revision is rejected.
                </p>
              )}
              <label className="field">
                <span>Decision note (5–500 characters)</span>
                <textarea
                  required
                  minLength={5}
                  maxLength={500}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <label className="runtime-check">
                <input
                  type="checkbox"
                  required
                  checked={reviewed}
                  onChange={(e) => setReviewed(e.target.checked)}
                />
                <span>
                  I reviewed the account, requested access and session impact.
                </span>
              </label>
              <button
                className="btn btn-primary"
                disabled={busy || !reviewed || note.trim().length < 5}
              >
                {busy ? "Saving…" : "Confirm reviewed change"}
              </button>
            </fieldset>
          </form>
        </Modal>
      )}
    </section>
  );
}
