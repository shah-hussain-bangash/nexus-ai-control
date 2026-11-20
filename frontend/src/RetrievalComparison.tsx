import { useEffect, useRef, useState } from "react";
import { api } from "./api";

type Row = Record<string, any>;
const percent = (value: number | null) =>
  value === null ? "Not applicable" : `${(value * 100).toFixed(1)}%`;
const rank = (value: number | null) =>
  value === null ? "Not applicable" : value.toFixed(3);
const difference = (value: number | null, points = false) =>
  value === null
    ? "Not applicable"
    : `${value > 0 ? "+" : ""}${(value * (points ? 100 : 1)).toFixed(points ? 1 : 3)}${points ? " points" : ""}`;

export function RetrievalComparison({
  selected,
  records,
  userId,
}: {
  selected: Row;
  records: Row[];
  userId: string;
}) {
  const [baseline, setBaseline] = useState(""),
    [result, setResult] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const sequence = useRef(0);
  useEffect(
    () => () => {
      sequence.current++;
    },
    [],
  );
  if (selected.author_id !== userId) return null;
  const options = records.filter(
    (row) => row.author_id === userId && row.id !== selected.id,
  );
  async function compare() {
    const request = ++sequence.current,
      candidateId = selected.id,
      baselineId = baseline;
    setResult(null);
    setError("");
    setBusy(true);
    try {
      const response = await api("/v1/retrieval-checks/compare", "POST", {
        baseline_id: baselineId,
        candidate_id: candidateId,
      });
      if (request !== sequence.current) return;
      if (
        response.baseline?.id !== baselineId ||
        response.candidate?.id !== candidateId
      )
        throw new Error(
          "The comparison does not match the selected checks. Try again.",
        );
      setResult(response);
    } catch (e) {
      if (request === sequence.current) setError((e as Error).message);
    } finally {
      if (request === sequence.current) setBusy(false);
    }
  }
  return (
    <section
      className="live-retrieval-comparison"
      aria-label="Compare saved retrieval runs"
    >
      <h4>Compare saved runs</h4>
      <p>
        Choose one of your checks on this history page as the baseline. Both
        runs must use the same ordered cases, source expectations, top-k,
        language labels and precision targets, under your current role. Names
        may differ.
      </p>
      <label>
        Baseline saved check
        <select
          value={baseline}
          disabled={busy}
          onChange={(e) => {
            sequence.current++;
            setBaseline(e.target.value);
            setResult(null);
            setError("");
          }}
        >
          <option value="">Choose a baseline</option>
          {options.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} · {new Date(row.created * 1000).toLocaleString()}
            </option>
          ))}
        </select>
      </label>
      {!options.length && (
        <p>Save another run of this suite to compare results.</p>
      )}
      <button
        className="btn btn-outline"
        disabled={!baseline || busy}
        onClick={compare}
      >
        {busy ? "Comparing saved measurements…" : "Compare with selected run"}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div aria-live="polite">
          <h4>Baseline → selected run</h4>
          <p>
            {result.baseline.name} → {result.candidate.name}
          </p>
          <p>
            {Object.entries(result.case_changes)
              .map(([key, value]) => `${value} ${key}`)
              .join(" · ")}
          </p>
          {(result.corpus_changed ||
            result.normalization_changed ||
            result.baseline.stale ||
            result.candidate.stale) && (
            <p className="ops-alert">
              {result.corpus_changed &&
                "The authorized source corpus changed between runs. "}
              {result.normalization_changed &&
                "The search normalization method changed between runs. "}
              {result.baseline.stale &&
                "Baseline evidence is historical and needs a rerun for current results. "}
              {result.candidate.stale &&
                "Selected evidence also needs a rerun for current results. "}
              This comparison shows saved measurements and does not establish
              the cause of a change.
            </p>
          )}
          <div
            className="live-quality-language-table"
            role="region"
            aria-label="Saved-run metric comparison"
            tabIndex={0}
          >
            <table aria-label="Baseline and selected retrieval metrics">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Baseline</th>
                  <th>Selected</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Cases passed</th>
                  <td>
                    {result.baseline.passed_cases}/{result.baseline.case_count}
                  </td>
                  <td>
                    {result.candidate.passed_cases}/
                    {result.candidate.case_count}
                  </td>
                  <td>
                    {result.delta.passed_cases > 0 ? "+" : ""}
                    {result.delta.passed_cases}
                  </td>
                </tr>
                {[
                  ["Mean recall", "mean_document_recall_at_k"],
                  ["Mean precision", "mean_document_precision_at_k"],
                  ["Mean reciprocal rank", "mean_reciprocal_rank"],
                ].map(([label, key]) => (
                  <tr key={key}>
                    <th scope="row">{label}</th>
                    <td>
                      {key === "mean_reciprocal_rank"
                        ? rank(result.baseline[key])
                        : percent(result.baseline[key])}
                    </td>
                    <td>
                      {key === "mean_reciprocal_rank"
                        ? rank(result.candidate[key])
                        : percent(result.candidate[key])}
                    </td>
                    <td>
                      {difference(
                        result.delta[key],
                        key !== "mean_reciprocal_rank",
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="live-quality-cases">
            {result.cases.map((row: Row) => (
              <article key={row.index}>
                <header>
                  <strong>
                    {row.index + 1}. {selected.result.cases[row.index]?.query}
                  </strong>
                  <span
                    className={
                      "live-state " +
                      (row.change === "regressed"
                        ? "failed"
                        : row.change === "improved"
                          ? "succeeded"
                          : "waiting_review")
                    }
                  >
                    {row.change}
                  </span>
                </header>
                <p>
                  {row.baseline.passed ? "Passed" : "Failed"} →{" "}
                  {row.candidate.passed ? "passed" : "failed"}
                </p>
                <p>
                  Recall {percent(row.baseline.document_recall_at_k)} →{" "}
                  {percent(row.candidate.document_recall_at_k)} · Precision{" "}
                  {percent(row.baseline.document_precision_at_k)} →{" "}
                  {percent(row.candidate.document_precision_at_k)}
                </p>
                <p>
                  Reciprocal rank {rank(row.baseline.reciprocal_rank)} →{" "}
                  {rank(row.candidate.reciprocal_rank)} · Unlisted sources{" "}
                  {row.baseline.unexpected_document_count} →{" "}
                  {row.candidate.unexpected_document_count}
                </p>
                {row.returned_sources_changed && (
                  <p>Returned sources or their order changed.</p>
                )}
              </article>
            ))}
          </div>
          <p className="muted">
            A case improves when at least one measured value improves and none
            worsens; mixed means both directions changed. Unlisted sources may
            still be relevant. Improvement does not imply a passing case.{" "}
            {result.boundary}
          </p>
        </div>
      )}
    </section>
  );
}
