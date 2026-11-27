import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { rerankRequest } from "./rerankRequest";
type Row = Record<string, any>;
export function LocalReranking({
  me,
  run,
  onResult,
}: {
  me: Row;
  run: Row | null;
  onResult: (row: Row) => void;
}) {
  const [capability, setCapability] = useState<Row | null>(null),
    [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const scope = liveIntentScope(
    "local-rerank",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  useEffect(() => {
    void api("/v1/neural-reranking/capabilities")
      .then(setCapability)
      .catch((e: Error) => setMessage(e.message));
  }, []);
  useEffect(() => {
    setQuery("");
  }, [run?.id]);
  const eligible =
    run?.status === "completed" &&
    run.parameters?.retrieval_mode === "local_indexed" &&
    !run.parameters?.reranking &&
    run.items?.length >= 2 &&
    !run.withheld_stale_or_inaccessible;
  async function act(task: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const value = await task();
      onResult(value);
      setMessage(
        `Reranking ${value.status}. ${value.error_code || "Original scores are retained; the model changed only passage order."}`,
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Reranking failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="panel runtime-card"
      aria-label="Optional local passage reranking"
    >
      <h3>Optional local passage reranking</h3>
      <p>
        Open your original completed indexed search with at least two passages,
        then repeat its exact query. The local model orders those existing
        passages. It does not retrieve more sources, create an answer, or
        replace the original cosine scores.
      </p>
      <p>
        {capability?.enabled
          ? `Operator-pinned reranking model: ${capability.model}`
          : "Operator setup required. Local reranking is disabled until a separate installed model and digest are configured."}
      </p>
      <p>
        Only the original search author can submit this step. Older searches
        without a private query identity must be rerun first.
      </p>
      {message && <p role="status">{message}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!run || !eligible) return;
          const body = rerankRequest(run.id, query);
          void act(() =>
            sendLiveIntent(sessionStorage, scope, body, (key) =>
              api("/v1/neural-indexes/rerank", "POST", body, key),
            ),
          );
        }}
      >
        <label className="field">
          <span>Repeat the original query (processed transiently)</span>
          <textarea
            required
            maxLength={500}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="live-actions">
          <button
            className="btn btn-primary"
            disabled={
              busy || !capability?.enabled || !eligible || !query.trim()
            }
          >
            Rerank existing passages
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
                    "No unacknowledged reranking submission in this account and environment.",
                  );
                const value = await api("/v1/hybrid-search/recover", "POST", {
                  key: pending.key,
                });
                acknowledgeRecovery(sessionStorage, scope, pending, value);
                return value;
              })
            }
          >
            Recover reranking receipt
          </button>
        </div>
      </form>
      <p>
        Reranking can improve or worsen order. Saved reviews can compare it with
        the original search. Representative quality, prompt-injection resilience
        and model-context acceptance remain separate work.
      </p>
    </section>
  );
}
