import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";

type Row = Record<string, any>;
export function NeuralIndexPanel({
  me,
  sources,
  enabled,
  model,
  digest,
  onSearch,
}: {
  me: Row;
  sources: { id: string; version: number }[];
  enabled: boolean;
  model: string;
  digest: string;
  onSearch: (result: Row) => void;
}) {
  const [indexes, setIndexes] = useState<Row[]>([]),
    [receipts, setReceipts] = useState<Row[]>([]);
  const [selected, setSelected] = useState(""),
    [name, setName] = useState("");
  const [query, setQuery] = useState(""),
    [note, setNote] = useState("");
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const buildScope = liveIntentScope(
    "neural-index-build",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  const queryScope = liveIntentScope(
    "indexed-search",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  const current = indexes.find((row) => row.id === selected);
  const ready =
    enabled &&
    current?.status === "ready" &&
    current.model === model &&
    current.model_digest === digest;
  const operate = me.permissions?.includes("operate");
  async function refresh() {
    const [list, history] = await Promise.all([
      api("/v1/neural-indexes"),
      api("/v1/neural-indexes/builds"),
    ]);
    setIndexes(list.items);
    setReceipts(history.items);
    setSelected((id) =>
      list.items.some((row: Row) => row.id === id) ? id : "",
    );
  }
  useEffect(() => {
    void refresh().catch((e: Error) => setMessage(e.message));
  }, []);
  async function act(job: () => Promise<Row>, search = false) {
    setBusy(true);
    setMessage("");
    try {
      const result = await job();
      setMessage(
        `${result.status}. ${result.error_code || result.boundary || ""}`,
      );
      if (search) onSearch(result);
      if (result.index_id) setSelected(result.index_id);
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }
  async function recover(scope: string, path: string) {
    const pending = readRecovery(sessionStorage, scope);
    if (!pending)
      throw Error(
        "No unacknowledged submission in this account and environment.",
      );
    const result = await api(path, "POST", { key: pending.key });
    acknowledgeRecovery(sessionStorage, scope, pending, result);
    return result;
  }
  return (
    <section className="panel runtime-card" aria-label="Stored neural indexes">
      <h3>Stored neural indexes</h3>
      <p>
        Build once from the documents selected above. Indexed searches send only
        your query to the pinned local model. Source access, revisions and
        snapshot integrity are checked again on every search.
      </p>
      <p>
        Up to 20 snapshots per environment, 32 passages per snapshot. Model
        execution requires operator setup. Build receipts remain after removal;
        recovering a receipt never rebuilds an index.
      </p>
      {!enabled && (
        <p role="status">
          Local embedding model setup is required before building or searching.
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const body = {
            name: name.trim(),
            sources: sources.map(({ id, version }) => ({ id, version })),
          };
          void act(() =>
            sendLiveIntent(sessionStorage, buildScope, body, (key) =>
              api("/v1/neural-indexes", "POST", body, key),
            ),
          );
        }}
      >
        <label className="field">
          <span>New index name</span>
          <input
            value={name}
            minLength={2}
            maxLength={120}
            required
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <p>
          {sources.length} selected source documents. Select at least one above;
          an empty selection never means all documents.
        </p>
        <div className="live-actions">
          <button
            className="btn btn-primary"
            disabled={
              busy ||
              !enabled ||
              !operate ||
              !sources.length ||
              name.trim().length < 2
            }
          >
            Build index
          </button>
          <button
            className="btn"
            type="button"
            disabled={busy}
            onClick={() =>
              void act(() => recover(buildScope, "/v1/neural-indexes/recover"))
            }
          >
            Recover build receipt
          </button>
        </div>
      </form>
      <label className="field">
        <span>Saved snapshot</span>
        <select
          value={selected}
          disabled={busy}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Choose a snapshot</option>
          {indexes.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} · {row.status} · {row.entry_count} passages
            </option>
          ))}
        </select>
      </label>
      {current && (
        <p>
          Version {current.version} · {current.model} · {current.dimensions}{" "}
          dimensions. Stored status is checked again when used.
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const body = {
            index_id: selected,
            query,
            top_k: 5,
            min_score: 0.15,
            one_per_document: true,
          };
          void act(
            () =>
              sendLiveIntent(sessionStorage, queryScope, body, (key) =>
                api("/v1/neural-indexes/search", "POST", body, key),
              ),
            true,
          );
        }}
      >
        <label className="field">
          <span>Query saved index</span>
          <textarea
            value={query}
            required
            maxLength={500}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <p>
          Shows up to five passages, one per document, with minimum similarity
          0.15. Results appear in Ranked evidence and search history. Query text
          and query vectors are not saved in receipts.
        </p>
        <div className="live-actions">
          <button
            className="btn btn-primary"
            disabled={busy || !ready || !query.trim()}
          >
            Search saved index
          </button>
          <button
            className="btn"
            type="button"
            disabled={busy}
            onClick={() =>
              void act(
                () => recover(queryScope, "/v1/hybrid-search/recover"),
                true,
              )
            }
          >
            Recover indexed search
          </button>
        </div>
      </form>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!current) return;
          void act(() =>
            api(
              "/v1/neural-indexes/" + encodeURIComponent(current.id),
              "DELETE",
              { expected_version: current.version, note },
            ),
          );
        }}
      >
        <label className="field">
          <span>Reason for removing selected snapshot</span>
          <input
            value={note}
            minLength={5}
            maxLength={500}
            required
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <button
          className="btn"
          disabled={busy || !operate || !current || note.trim().length < 5}
        >
          Remove selected snapshot
        </button>
      </form>
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void act(async () => {
            await refresh();
            return { status: "refreshed" };
          })
        }
      >
        Refresh indexes and receipts
      </button>
      <h4>Recent build receipts</h4>
      {receipts.map((row) => (
        <p key={row.id}>
          {new Date(row.created * 1000).toLocaleString()} · {row.status} ·
          snapshot {row.index_state || "unavailable"} ·{" "}
          {row.error_code || `${row.corpus_passages} passages`} · local HTTP
          calls {row.provider_calls ?? "unconfirmed"}
        </p>
      ))}
      <p>
        No generated answers or model-quality acceptance. Removing active
        vectors does not erase database backups.
      </p>
    </section>
  );
}
