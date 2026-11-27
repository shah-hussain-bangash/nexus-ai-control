import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { indexedReviewRequest } from "./indexedReviewRequest";
type Row = Record<string, any>;
export function IndexedSearchReview({
  me,
  run,
  documents,
}: {
  me: Row;
  run: Row | null;
  documents: Row[];
}) {
  const [expected, setExpected] = useState<string[]>([]),
    [negative, setNegative] = useState(false);
  const [language, setLanguage] = useState<
    "" | "English" | "Arabic" | "Bilingual"
  >("");
  const [precision, setPrecision] = useState<number | null>(null),
    [note, setNote] = useState("");
  const [reviews, setReviews] = useState<Row[]>([]),
    [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false),
    [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null);
  const scope = liveIntentScope(
    "indexed-review",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  const eligible =
    run?.status === "completed" &&
    run.parameters?.retrieval_mode === "local_indexed";
  useEffect(() => {
    setExpected([]);
    setNegative(false);
    setNote("");
  }, [run?.id]);
  async function refresh(at = 0) {
    const data = await api(`/v1/indexed-search-reviews?offset=${at}&limit=20`);
    setReviews(data.items);
    setOffset(at);
    setNext(data.next_offset);
  }
  useEffect(() => {
    void refresh().catch((e: Error) => setMessage(e.message));
  }, []);
  async function act(job: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const result = await job();
      setMessage(
        `Review ${result.status}${result.stale ? " · stale snapshot" : ""}. No model was called.`,
      );
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Review could not be saved.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="panel runtime-card"
      aria-label="Indexed search quality review"
    >
      <h3>Review saved indexed-search quality</h3>
      <p>
        Open a completed indexed search in Ranked evidence. Choose the complete
        expected-source list and save your review. Measurements use that saved
        result; no query is rerun and no model is called.
      </p>
      <p>
        Language labels come from you. A passing measurement is not independent
        model acceptance or generated-answer grading.
      </p>
      {message && <p role="status">{message}</p>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!run || !eligible) return;
          const body = indexedReviewRequest({
            searchId: run.id,
            expectation: negative ? "no_results" : "retrieve",
            expected,
            language,
            precision,
            note,
          });
          void act(() =>
            sendLiveIntent(sessionStorage, scope, body, (key) =>
              api("/v1/indexed-search-reviews", "POST", body, key),
            ),
          );
        }}
      >
        <p>
          {eligible
            ? `Saved search: ${run?.id}`
            : "Choose a completed stored-index search to begin."}
        </p>
        <label className="field">
          <span>Expected outcome</span>
          <select
            disabled={busy}
            value={negative ? "no_results" : "retrieve"}
            onChange={(e) => setNegative(e.target.value === "no_results")}
          >
            <option value="retrieve">Retrieve expected sources</option>
            <option value="no_results">Return no results</option>
          </select>
        </label>
        {!negative && (
          <>
            <label className="field">
              <span>Complete expected-source list (up to five)</span>
              <select
                multiple
                size={5}
                value={expected}
                disabled={busy}
                onChange={(e) =>
                  setExpected(
                    Array.from(e.target.selectedOptions, (o) => o.value),
                  )
                }
              >
                {documents.map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    {doc.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Minimum precision percent (optional)</span>
              <input
                type="number"
                min={0}
                max={100}
                step={1}
                value={precision ?? ""}
                onChange={(e) =>
                  setPrecision(
                    e.target.value === "" ? null : Number(e.target.value),
                  )
                }
              />
            </label>
          </>
        )}
        <label className="field">
          <span>Reviewer-assigned query language</span>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as typeof language)}
          >
            <option value="">Unlabelled</option>
            <option>English</option>
            <option>Arabic</option>
            <option>Bilingual</option>
          </select>
        </label>
        <label className="field">
          <span>Review note (avoid credentials or private query text)</span>
          <textarea
            required
            minLength={5}
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <div className="live-actions">
          <button
            className="btn btn-primary"
            disabled={
              busy ||
              !eligible ||
              !me.permissions?.includes("operate") ||
              note.trim().length < 5 ||
              (!negative && (!expected.length || expected.length > 5))
            }
          >
            Save quality review
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
                    "No unacknowledged review in this account and environment.",
                  );
                const result = await api(
                  "/v1/indexed-search-reviews/recover",
                  "POST",
                  { key: pending.key },
                );
                acknowledgeRecovery(sessionStorage, scope, pending, result);
                return result;
              })
            }
          >
            Recover review
          </button>
        </div>
      </form>
      <h4>Saved quality reviews</h4>
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void refresh(offset).catch((e: Error) => setMessage(e.message))
        }
      >
        Refresh reviews
      </button>
      {reviews.map((review) => (
        <article className="runtime-hit" key={review.id}>
          <h4>
            {review.status}
            {review.stale ? " · stale source or index snapshot" : ""}
          </h4>
          <p>
            {new Date(review.created * 1000).toLocaleString()} ·{" "}
            {review.labels.query_language || "Unlabelled"} · search{" "}
            {review.search_id}
          </p>
          <p>{review.labels.note}</p>
          <p>
            Expected outcome {review.labels.expectation} · expected documents{" "}
            {review.labels.expected_document_ids.length} · precision target{" "}
            {review.labels.minimum_precision_percent === undefined
              ? "not set"
              : `${review.labels.minimum_precision_percent}%`}
          </p>
          <p>
            Recall{" "}
            {review.measurements.document_recall_at_k ?? "not applicable"} ·
            precision{" "}
            {review.measurements.document_precision_at_k ?? "not applicable"} ·
            reciprocal rank {review.measurements.reciprocal_rank}
          </p>
          <p>
            Unexpected documents{" "}
            {review.measurements.unexpected_document_ids.length} · review model
            calls {review.review_provider_calls} · original search HTTP calls{" "}
            {review.original_search_provider_calls ?? "unconfirmed"}
          </p>
          <p>
            Original model {review.parameters.embedding_model} · top{" "}
            {review.parameters.top_k} · threshold {review.parameters.min_score}{" "}
            ·{" "}
            {review.parameters.one_per_document
              ? "one result per document"
              : "multiple passages allowed"}
          </p>
          <code className="live-hash">
            Model digest {review.parameters.embedding_digest}
          </code>
          <p>{review.boundary}</p>
        </article>
      ))}
      {!reviews.length && <p>No accessible saved reviews on this page.</p>}
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
          Previous reviews
        </button>
        <button
          className="btn"
          disabled={busy || next === null}
          onClick={() =>
            void refresh(next ?? 0).catch((e: Error) => setMessage(e.message))
          }
        >
          Next reviews
        </button>
      </div>
    </section>
  );
}
