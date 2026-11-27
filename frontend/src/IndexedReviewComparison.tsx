import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { indexedComparisonRequest } from "./indexedComparisonRequest";
type Row = Record<string, any>;
export function IndexedReviewComparison({ reviews }: { reviews: Row[] }) {
  const [baseline, setBaseline] = useState(""),
    [candidate, setCandidate] = useState("");
  const [result, setResult] = useState<Row | null>(null),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inspection = useRef(0);
  useEffect(() => {
    inspection.current++;
    setResult(null);
    setError("");
    return () => {
      inspection.current++;
    };
  }, [baseline, candidate, reviews]);
  return (
    <section aria-label="Compare indexed-search quality reviews">
      <h4>Compare two saved reviews</h4>
      <p>
        Choose reviews on this page. The server requires the same original query
        and actor, expected sources, language label, precision target, and
        search controls. Model or source changes are reported separately.
      </p>
      <p>
        Older searches without a private query identity must be rerun before
        comparison. No query text is recovered, and no model is called.
      </p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          setResult(null);
          const active = inspection.current;
          try {
            const value = await api(
              "/v1/indexed-search-reviews/compare",
              "POST",
              indexedComparisonRequest(baseline, candidate),
            );
            if (active === inspection.current) setResult(value);
          } catch (e) {
            if (active === inspection.current)
              setError(e instanceof Error ? e.message : "Comparison failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          <span>Baseline review</span>
          <select
            disabled={busy}
            required
            value={baseline}
            onChange={(e) => setBaseline(e.target.value)}
          >
            <option value="">Choose baseline</option>
            {reviews.map((row) => (
              <option key={row.id} value={row.id}>
                {row.status} · {new Date(row.created * 1000).toLocaleString()} ·{" "}
                {row.id}
                {row.stale ? " · stale" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Candidate review</span>
          <select
            disabled={busy}
            required
            value={candidate}
            onChange={(e) => setCandidate(e.target.value)}
          >
            <option value="">Choose candidate</option>
            {reviews.map((row) => (
              <option key={row.id} value={row.id}>
                {row.status} · {new Date(row.created * 1000).toLocaleString()} ·{" "}
                {row.id}
                {row.stale ? " · stale" : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          className="btn"
          disabled={
            busy ||
            !reviews.some((r) => r.id === baseline) ||
            !reviews.some((r) => r.id === candidate) ||
            baseline === candidate
          }
        >
          Compare saved measurements
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <div aria-live="polite">
          <p>
            <strong>{result.change}</strong> · same query verified · model calls{" "}
            {result.provider_calls}
          </p>
          {result.stale && (
            <p role="status">
              Historical comparison: at least one source or index snapshot is
              stale.
            </p>
          )}
          <p>
            Model changed: {result.model_changed ? "yes" : "no"} · corpus
            changed: {result.corpus_changed ? "yes" : "no"} · index changed:{" "}
            {result.index_changed ? "yes" : "no"}
          </p>
          <p>
            Baseline model {result.baseline.parameters.embedding_model} ·
            candidate model {result.candidate.parameters.embedding_model} · top{" "}
            {result.baseline.parameters.top_k} · threshold{" "}
            {result.baseline.parameters.min_score}
          </p>
          <table>
            <caption>
              Saved retrieval measurements; delta is candidate minus baseline
            </caption>
            <thead>
              <tr>
                <th scope="col">Measurement</th>
                <th scope="col">Baseline</th>
                <th scope="col">Candidate</th>
                <th scope="col">Delta</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["document_recall_at_k", "Document recall"],
                  ["document_precision_at_k", "Document precision"],
                  ["reciprocal_rank", "Reciprocal rank"],
                  ["unexpected_document_count", "Unexpected documents"],
                ] as const
              ).map(([key, label]) => (
                <tr key={key}>
                  <th scope="row">{label}</th>
                  <td>{result.baseline.metrics[key] ?? "not applicable"}</td>
                  <td>{result.candidate.metrics[key] ?? "not applicable"}</td>
                  <td>{result.delta[key] ?? "not applicable"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>{result.boundary}</p>
        </div>
      )}
    </section>
  );
}
