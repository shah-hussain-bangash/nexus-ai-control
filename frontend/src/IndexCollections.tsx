import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { indexJobRequest } from "./indexJobRequest";
import { collectionSelection } from "./collectionSelection";
type Row = Record<string, any>;
export function IndexCollections({
  me,
  sources,
  enabled,
  model,
  digest,
  onSelect,
}: {
  me: Row;
  sources: { id: string; version: number }[];
  enabled: boolean;
  model: string;
  digest: string;
  onSelect: (ids: string[]) => void;
}) {
  const [name, setName] = useState(""),
    [items, setItems] = useState<Row[]>([]),
    [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [note, setNote] = useState("");
  const [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null);
  const scope = liveIntentScope(
    "index-collection",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  const current = items.find((row) => row.id === selected),
    operate = me.permissions?.includes("operate");
  async function refresh(at = offset) {
    const value = await api(
      `/v1/neural-index-collections?offset=${at}&limit=20`,
    );
    setItems(value.items);
    setOffset(at);
    setNext(value.next_offset);
  }
  useEffect(() => {
    void refresh(0).catch((e: Error) => setMessage(e.message));
  }, []);
  async function act(task: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const row = await task();
      setSelected(row.id);
      setMessage(`Collection ${row.status}.`);
      await refresh(0);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Collection request failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="panel runtime-card"
      aria-label="Larger index collections"
    >
      <h3>Larger index collections</h3>
      <p>
        Build up to 256 current passages from up to 20 selected documents. The
        server splits the complete selection into at most eight snapshots of 32
        passages and queues existing checkpoint workers. It reserves the whole
        set before returning; no selected sources are silently dropped.
      </p>
      <p>
        Each child snapshot publishes independently. The full collection can be
        selected for search only after all children are ready. The normal
        execution worker must be running; submission and recovery do not call
        the model.
      </p>
      {message && <p role="status">{message}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const body = indexJobRequest(name, sources);
          void act(() =>
            sendLiveIntent(sessionStorage, scope, body, (key) =>
              api("/v1/neural-index-collections", "POST", body, key),
            ),
          );
        }}
      >
        <label className="field">
          <span>Collection name</span>
          <input
            value={name}
            required
            minLength={2}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <p>{sources.length} pinned source documents selected above.</p>
        <div className="live-actions">
          <button
            className="btn btn-primary"
            disabled={
              busy ||
              !enabled ||
              !operate ||
              !sources.length ||
              sources.length > 20 ||
              name.trim().length < 2
            }
          >
            Queue complete collection
          </button>
          <button
            className="btn"
            type="button"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const pending = readRecovery(sessionStorage, scope);
                if (!pending)
                  throw Error(
                    "No unacknowledged collection submission in this account and environment.",
                  );
                const row = await api(
                  "/v1/neural-index-collections/recover",
                  "POST",
                  { key: pending.key },
                );
                acknowledgeRecovery(sessionStorage, scope, pending, row);
                return row;
              })
            }
          >
            Recover collection submission
          </button>
        </div>
      </form>
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void refresh().catch((e: Error) => setMessage(e.message))
        }
      >
        Refresh collection progress
      </button>
      <label className="field">
        <span>Saved collection</span>
        <select
          value={selected}
          disabled={busy}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Choose a collection</option>
          {items.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} · {row.status} · {row.snapshot_count} snapshots
            </option>
          ))}
        </select>
      </label>
      {current && (
        <>
          <p>
            <strong>{current.status}</strong> · checkpointed passages{" "}
            {current.completed_passages}/{current.total_passages} · confirmed
            local HTTP calls {current.confirmed_http_calls} · total{" "}
            {current.provider_calls ?? "unknown"}
          </p>
          <progress
            value={current.completed_passages}
            max={current.total_passages}
            aria-label="Collection checkpointed passages"
          />
          <ul>
            {current.children.map((job: Row) => (
              <li key={job.id}>
                {job.name}: {job.status} · {job.completed_passages}/
                {job.total_passages} passages · snapshot{" "}
                {job.index?.status || "removed"}
              </li>
            ))}
          </ul>
          <p>
            Manage pause/resume or uncertain-batch acknowledgement for
            individual children in Background index builds below. Cancelling the
            unfinished children keeps completed snapshots and all receipts.
          </p>
          <button
            className="btn btn-primary"
            disabled={
              busy ||
              !enabled ||
              !current.searchable ||
              current.model !== model ||
              current.model_digest !== digest
            }
            onClick={() => {
              try {
                onSelect(collectionSelection(current as any, model, digest));
                setMessage(
                  "The complete collection is selected in Stored neural indexes below. Enter a query there to search it.",
                );
              } catch (e) {
                setMessage(
                  e instanceof Error ? e.message : "Collection is unavailable.",
                );
              }
            }}
          >
            Select complete collection for search
          </button>
          <label className="field">
            <span>Reason for cancelling unfinished children</span>
            <input
              value={note}
              minLength={5}
              maxLength={500}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button
            className="btn"
            disabled={
              busy ||
              !operate ||
              note.trim().length < 5 ||
              !current.children.some((job: Row) =>
                ["queued", "processing", "paused", "interrupted"].includes(
                  job.status,
                ),
              )
            }
            onClick={() =>
              void act(() =>
                api(
                  `/v1/neural-index-collections/${encodeURIComponent(current.id)}/cancel`,
                  "POST",
                  { expected_token: current.control_token, note },
                ),
              )
            }
          >
            Cancel unfinished collection builds
          </button>
          <p>{current.boundary}</p>
        </>
      )}
      <div className="live-actions">
        <button
          className="btn"
          disabled={busy || offset === 0}
          onClick={() =>
            void refresh(Math.max(0, offset - 20)).catch((e: Error) =>
              setMessage(e.message),
            )
          }
        >
          Previous collections
        </button>
        <button
          className="btn"
          disabled={busy || next === null}
          onClick={() =>
            void refresh(next ?? 0).catch((e: Error) => setMessage(e.message))
          }
        >
          Next collections
        </button>
      </div>
    </section>
  );
}
