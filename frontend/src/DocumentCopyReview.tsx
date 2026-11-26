import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { sessionContext } from "./sessionContext";
import { checkedCopies, type CopyReview } from "./documentCopies";

export function DocumentCopyReview({
  id,
  version,
  onOpen,
}: {
  id: string;
  version: number;
  onOpen: (id: string) => void;
}) {
  const [review, setReview] = useState<CopyReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ticket = useRef(0);
  useEffect(() => {
    const clear = () => {
      ticket.current++;
      setReview(null);
      setError("");
      setBusy(false);
    };
    clear();
    const unsubscribe = sessionContext.subscribe(clear);
    return () => {
      ticket.current++;
      unsubscribe();
    };
  }, [id, version]);
  async function load(offset = 0) {
    const current = ++ticket.current;
    const snapshot = sessionContext.capture();
    setReview(null);
    setBusy(true);
    setError("");
    try {
      const value = await api(
        `/v1/documents/${encodeURIComponent(id)}/copies?expected_version=${version}&offset=${offset}&limit=20`,
      );
      if (current === ticket.current && sessionContext.current(snapshot))
        setReview(checkedCopies(value, snapshot.context, id, version, offset));
    } catch (cause) {
      if (current === ticket.current && sessionContext.current(snapshot))
        setError(
          cause instanceof Error
            ? cause.message
            : "Copy review could not be loaded.",
        );
    } finally {
      if (current === ticket.current) setBusy(false);
    }
  }
  return (
    <section aria-label="Identical indexed-text copies" className="ops-alert">
      <strong>Identical indexed-text copies</strong>
      <p>
        Compare this version with other currently readable records in this
        workspace and environment. Exact indexed text only; original files and
        near copies are not compared. This review does not merge or delete
        documents.
      </p>
      <button
        className="btn btn-outline"
        disabled={busy}
        onClick={() => load()}
      >
        {busy ? "Checking readable copies…" : "Review identical text"}
      </button>
      {busy && <p role="status">Checking current source access and version…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {review && (
        <div aria-live="polite">
          <p>
            {review.visible_count} other readable{" "}
            {review.visible_count === 1 ? "record has" : "records have"}{" "}
            identical indexed text. This is a point-in-time preview; opening a
            source checks access again.
          </p>
          <ul>
            {review.items.map((copy) => (
              <li key={copy.id}>
                <button
                  className="btn btn-outline"
                  onClick={() => onOpen(copy.id)}
                >
                  {copy.title} · {copy.filename} · version {copy.version}
                </button>
              </li>
            ))}
          </ul>
          <div className="live-actions">
            <button
              className="btn btn-outline"
              disabled={review.offset === 0}
              onClick={() => load(Math.max(0, review.offset - 20))}
            >
              Previous copies
            </button>
            <button
              className="btn btn-outline"
              disabled={review.next_offset === null}
              onClick={() => load(review.next_offset!)}
            >
              Next copies
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
