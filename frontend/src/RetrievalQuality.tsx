import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Modal } from "./RuntimeDialog";
import { sendLiveIntent, liveIntentScope } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { registerNavigationGuard } from "./navigationGuard";
import { assertPrecisionTargets } from "./precisionTargets";
type Row = Record<string, any>;
type Case = {
  query: string;
  expectation: "retrieve" | "no_results";
  expected_document_ids: string[];
  query_language?: "English" | "Arabic" | "Bilingual";
  minimum_precision_percent?: number;
};
const emptyCase = (): Case => ({
  query: "",
  expectation: "retrieve",
  expected_document_ids: [],
});
function pending(scope: string) {
  try {
    return readRecovery(sessionStorage, scope);
  } catch {
    return null;
  }
}
export function RetrievalQuality({
  me,
  documents,
}: {
  me: Row;
  documents: Row[];
}) {
  const [records, setRecords] = useState<Row[]>([]),
    [selected, setSelected] = useState<Row | null>(null),
    [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [editing, setEditing] = useState(false),
    [name, setName] = useState("Retrieval regression suite"),
    [topK, setTopK] = useState(5),
    [cases, setCases] = useState<Case[]>([emptyCase()]),
    [removing, setRemoving] = useState<Row | null>(null),
    [note, setNote] = useState(""),
    [discard, setDiscard] = useState(false);
  const scope = liveIntentScope(
      "retrieval-check",
      me.user.org_id,
      me.user.id,
      me.environment,
    ),
    [intent, setIntent] = useState(() => pending(scope));
  const afterLeave = useRef<() => void>(() => {}),
    canRun = me.permissions?.includes("operate");
  const dirty =
    editing &&
    cases.some((c) => c.query.trim() || c.expected_document_ids.length);
  useEffect(() => {
    if (!dirty) return;
    const stop = registerNavigationGuard((next) => {
      afterLeave.current = next;
      setDiscard(true);
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
      const r = await api(
        "/v1/retrieval-checks?offset=" + offset + "&limit=20",
      );
      setRecords(r.items);
      setNext(r.next_offset);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
  }, [offset]);
  async function inspect(id: string) {
    try {
      setSelected(await api("/v1/retrieval-checks/" + id));
      setError("");
    } catch (e) {
      setSelected(null);
      setError((e as Error).message);
    }
  }
  function closeEditor() {
    if (busy) return;
    if (dirty) {
      afterLeave.current = () => setEditing(false);
      setDiscard(true);
    } else setEditing(false);
  }
  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      assertPrecisionTargets(cases);
      const body = { name, top_k: topK, cases };
      const r = await sendLiveIntent<Row & { id: string; status: string }>(
        sessionStorage,
        scope,
        body,
        (key) => api("/v1/retrieval-checks", "POST", body, key),
      );
      setIntent(null);
      setSelected(r);
      setEditing(false);
      setNotice(
        "Check persisted. Passing cases measure this suite only; production readiness is unchanged.",
      );
      setOffset(0);
      await load();
    } catch (e) {
      setIntent(pending(scope));
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recover() {
    if (!intent) return;
    setBusy(true);
    try {
      const r = await api("/v1/retrieval-checks/recover", "POST", {
        key: intent.key,
      });
      acknowledgeRecovery(sessionStorage, scope, intent, r);
      setIntent(null);
      setNotice("Original check recovered without rerunning retrieval.");
      await load();
      await inspect(r.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function change(i: number, value: Partial<Case>) {
    setCases(cases.map((c, j) => (j === i ? { ...c, ...value } : c)));
  }
  return (
    <section className="live-quality" aria-label="Retrieval quality checks">
      <header className="live-quality-header">
        <div>
          <small>MEASURED RETRIEVAL / SAVED EVIDENCE</small>
          <h2>Test what your sources return.</h2>
          <p>
            Save up to 20 positive or no-result queries. Measure document recall
            and first relevant chunk rank against the current authorized corpus.
            These checks measure document keyword retrieval. No model calls or
            answer grading.
          </p>
        </div>
        <button
          className="btn btn-primary"
          disabled={!canRun || busy}
          onClick={() => {
            setName("Retrieval regression suite");
            setTopK(5);
            setCases([emptyCase()]);
            setEditing(true);
            setError("");
          }}
        >
          New retrieval check
        </button>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="ops-alert" role="status">
          {notice}
        </p>
      )}
      {intent && (
        <div className="ops-alert">
          <p>
            An unacknowledged check intent remains in this tab. Queries are not
            saved in browser storage.
          </p>
          <button className="btn btn-outline" onClick={recover} disabled={busy}>
            Recover pending check
          </button>
        </div>
      )}
      <div className="live-grid">
        <section className="live-list" aria-label="Saved retrieval checks">
          {records.length ? (
            records.map((r) => (
              <button
                className={selected?.id === r.id ? "selected" : ""}
                key={r.id}
                onClick={() => inspect(r.id)}
              >
                <strong>{r.name}</strong>
                <small>
                  {r.passed_cases}/{r.case_count} cases passed · top {r.top_k}
                </small>
                <span
                  className={
                    "live-state " +
                    (r.status === "passed" ? "succeeded" : "failed")
                  }
                >
                  {r.status}
                </span>
                <small>{new Date(r.created * 1000).toLocaleString()}</small>
              </button>
            ))
          ) : (
            <p>No saved checks visible to this account.</p>
          )}
        </section>
        <article className="live-detail">
          {selected ? (
            <>
              <header>
                <h3>{selected.name}</h3>
                <span
                  className={
                    "live-state " +
                    (selected.stale
                      ? "waiting_review"
                      : selected.status === "passed"
                        ? "succeeded"
                        : "failed")
                  }
                >
                  {selected.stale
                    ? "Rerun to refresh evidence"
                    : selected.status}
                </span>
              </header>
              <p>
                Run by {selected.result.actor_role} ·{" "}
                {selected.result.authorized_corpus_count} authorized sources ·
                top {selected.config.top_k}
              </p>
              <div className="live-quality-metrics">
                <div>
                  <small>Mean document recall @ {selected.config.top_k}</small>
                  <strong>
                    {selected.result.mean_document_recall_at_k === null
                      ? "Not applicable"
                      : (
                          selected.result.mean_document_recall_at_k * 100
                        ).toFixed(1) + "%"}
                  </strong>
                </div>
                <div>
                  <small>
                    Mean document precision @ {selected.config.top_k}
                  </small>
                  <strong>
                    {selected.result.mean_document_precision_at_k === null
                      ? "Not applicable"
                      : (
                          selected.result.mean_document_precision_at_k * 100
                        ).toFixed(1) + "%"}
                  </strong>
                </div>
                <div>
                  <small>Mean reciprocal rank</small>
                  <strong>
                    {selected.result.mean_reciprocal_rank === null
                      ? "Not applicable"
                      : selected.result.mean_reciprocal_rank.toFixed(3)}
                  </strong>
                </div>
                <div>
                  <small>Cases passed</small>
                  <strong>
                    {selected.passed_cases}/{selected.case_count}
                  </strong>
                </div>
              </div>
              <p>
                Precision measures how many returned sources are in your
                expected list. Review unlisted sources; they may still be
                relevant. A configured minimum precision target is enforced for
                that case.
              </p>
              {selected.language_metrics?.length > 0 && (
                <section aria-label="Retrieval results by query language">
                  <h4>Results by query language</h4>
                  <p>
                    Labels are chosen by the reviewer. Unlabelled queries are
                    not classified automatically.
                  </p>
                  <div
                    className="live-quality-language-table"
                    role="region"
                    aria-label="Query-language comparison table"
                    tabIndex={0}
                  >
                    <table aria-label="Retrieval metrics by query language">
                      <thead>
                        <tr>
                          <th>Query language</th>
                          <th>Cases passed</th>
                          <th>Recall / precision</th>
                          <th>Reciprocal rank</th>
                          <th>No-result checks passed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.language_metrics.map((group: Row) => (
                          <tr key={group.language}>
                            <th scope="row">{group.language}</th>
                            <td>
                              {group.passed_cases}/{group.case_count}
                            </td>
                            <td>
                              <small>Recall</small>
                              {group.mean_document_recall_at_k === null
                                ? "Not applicable"
                                : (
                                    group.mean_document_recall_at_k * 100
                                  ).toFixed(1) + "%"}{" "}
                              <small>Precision</small>
                              {group.mean_document_precision_at_k === null
                                ? "Not applicable"
                                : (
                                    group.mean_document_precision_at_k * 100
                                  ).toFixed(1) + "%"}
                              <small>
                                ({group.retrieve_cases} retrieval cases)
                              </small>
                            </td>
                            <td>
                              {group.mean_reciprocal_rank === null
                                ? "Not applicable"
                                : group.mean_reciprocal_rank.toFixed(3)}
                            </td>
                            <td>
                              {group.no_results_pass_rate === null
                                ? "Not applicable"
                                : (group.no_results_pass_rate * 100).toFixed(
                                    1,
                                  ) + "%"}{" "}
                              <small>
                                ({group.no_results_cases} no-result cases)
                              </small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
              <div className="live-quality-cases">
                {selected.result.cases.map((c: Row, i: number) => (
                  <article key={i}>
                    <header>
                      <strong>
                        {i + 1}. {c.query}
                      </strong>
                      <span
                        className={
                          "live-state " + (c.passed ? "succeeded" : "failed")
                        }
                      >
                        {c.passed ? "passed" : "failed"}
                      </span>
                    </header>
                    <p>Query language: {c.query_language || "Unlabelled"}</p>
                    <p>
                      {c.expectation === "no_results"
                        ? "Expected no authorized matches"
                        : `Expected ${c.expected_document_ids.length} source(s); document recall ${(c.document_recall_at_k * 100).toFixed(1)}%`}
                    </p>
                    {c.expectation === "retrieve" && (
                      <p>
                        Document precision:{" "}
                        {(c.document_precision_at_k * 100).toFixed(1)}% ·{" "}
                        {c.retrieved_document_count
                          ? `${c.matched_expected_document_count}/${c.retrieved_document_count} returned sources are expected`
                          : "No sources returned"}
                      </p>
                    )}
                    {c.minimum_precision_percent !== undefined && (
                      <p>
                        Minimum precision: {c.minimum_precision_percent}% ·{" "}
                        {c.precision_threshold_passed
                          ? "Target met"
                          : "Below target"}
                      </p>
                    )}
                    {c.unexpected_document_ids?.length > 0 && (
                      <details>
                        <summary>
                          Unlisted returned sources (
                          {c.unexpected_document_ids.length})
                        </summary>
                        <p>
                          These sources were not in the expected list. Review
                          their relevance and your test expectations.
                        </p>
                        {c.unexpected_document_ids.map((identifier: string) => (
                          <code key={identifier}>{identifier}</code>
                        ))}
                      </details>
                    )}
                    <p>
                      {c.citations.length
                        ? c.citations.map((x: string) => (
                            <code key={x}>{x}</code>
                          ))
                        : "No retrieved chunks"}
                    </p>
                  </article>
                ))}
              </div>
              <p className="muted">
                Historical evidence; source permissions are checked again on
                inspection. Source or corpus changes require a new run. Checks
                do not approve deployment.
              </p>
              <code className="live-hash">
                Corpus SHA-256 {selected.result.corpus_fingerprint}
              </code>
              {canRun && (
                <div className="live-actions">
                  <button
                    className="btn btn-outline"
                    onClick={() => {
                      setName(selected.config.name);
                      setTopK(selected.config.top_k);
                      setCases(structuredClone(selected.config.cases));
                      setEditing(true);
                      setError("");
                    }}
                  >
                    Review and rerun suite
                  </button>
                  <button
                    className="btn btn-outline"
                    onClick={() => {
                      setRemoving(selected);
                      setNote("");
                    }}
                  >
                    Remove check evidence
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="ops-empty">
              <h3>Inspect recorded retrieval quality</h3>
              <p>
                Select a saved check to compare expected sources with actual
                citations.
              </p>
            </div>
          )}
        </article>
      </div>
      <footer className="ops-pagination">
        <span>Page {Math.floor(offset / 20) + 1}</span>
        <button
          className="btn btn-outline"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 20))}
        >
          Previous checks
        </button>
        <button
          className="btn btn-outline"
          disabled={next === null}
          onClick={() => setOffset(next!)}
        >
          Next checks
        </button>
      </footer>
      {editing && (
        <Modal title="Configure a retrieval check" onClose={closeEditor}>
          <form onSubmit={run}>
            <p>
              Queries and results will be persisted in your backend, visible to
              the author and owner/security administrators. Use approved test
              data.
            </p>
            <label>
              Check name
              <input
                required
                minLength={2}
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Top ranked chunks per query
              <input
                type="number"
                required
                min={1}
                max={10}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
              />
            </label>
            {cases.map((c, i) => (
              <fieldset className="live-check-case" key={i}>
                <legend>Case {i + 1}</legend>
                <label>
                  Test query
                  <textarea
                    required
                    minLength={2}
                    maxLength={300}
                    value={c.query}
                    onChange={(e) => change(i, { query: e.target.value })}
                  />
                </label>
                <label>
                  Query language (optional)
                  <select
                    value={c.query_language || ""}
                    onChange={(e) =>
                      change(i, {
                        query_language: (e.target.value ||
                          undefined) as Case["query_language"],
                      })
                    }
                  >
                    <option value="">Unlabelled</option>
                    <option value="English">English</option>
                    <option value="Arabic">Arabic</option>
                    <option value="Bilingual">Bilingual</option>
                  </select>
                </label>
                <label>
                  Expectation
                  <select
                    value={c.expectation}
                    onChange={(e) =>
                      change(i, {
                        expectation: e.target.value as Case["expectation"],
                        expected_document_ids: [],
                        minimum_precision_percent: undefined,
                      })
                    }
                  >
                    <option value="retrieve">Retrieve expected sources</option>
                    <option value="no_results">Return no results</option>
                  </select>
                </label>
                {c.expectation === "retrieve" && (
                  <>
                    <label className="live-check-precision-toggle">
                      <input
                        type="checkbox"
                        checked={c.minimum_precision_percent !== undefined}
                        onChange={(e) =>
                          change(i, {
                            minimum_precision_percent: e.target.checked
                              ? 100
                              : undefined,
                          })
                        }
                      />
                      Require a minimum document precision
                    </label>
                    {c.minimum_precision_percent !== undefined && (
                      <label>
                        Minimum document precision (%)
                        <input
                          type="number"
                          required
                          min={0}
                          max={100}
                          step={1}
                          value={
                            Number.isFinite(c.minimum_precision_percent)
                              ? c.minimum_precision_percent
                              : ""
                          }
                          onChange={(e) =>
                            change(i, {
                              minimum_precision_percent: e.target.valueAsNumber,
                            })
                          }
                        />
                      </label>
                    )}
                    <p>
                      Only returned sources in your expected list count toward
                      the target. Check that your expected-source list is
                      complete.
                    </p>
                  </>
                )}
                {c.expectation === "retrieve" && (
                  <label>
                    Expected document sources
                    <select
                      multiple
                      required
                      value={c.expected_document_ids}
                      onChange={(e) =>
                        change(i, {
                          expected_document_ids: Array.from(
                            e.target.selectedOptions,
                            (x) => x.value,
                          ).slice(0, 5),
                        })
                      }
                    >
                      {Array.from(
                        new Map([
                          ...documents.map((d) => [d.id, d.title] as const),
                          ...c.expected_document_ids.map(
                            (id) =>
                              [
                                id,
                                documents.find((d) => d.id === id)?.title || id,
                              ] as const,
                          ),
                        ]).entries(),
                      ).map(([id, title]) => (
                        <option key={id} value={id}>
                          {title}
                        </option>
                      ))}
                    </select>
                    <small>
                      Choose up to 5 sources from the current document page.
                      Existing saved source IDs remain visible when rerunning.
                    </small>
                  </label>
                )}
                {cases.length > 1 && (
                  <button
                    className="btn btn-outline"
                    type="button"
                    onClick={() => setCases(cases.filter((_, j) => i !== j))}
                  >
                    Remove case {i + 1}
                  </button>
                )}
              </fieldset>
            ))}
            <button
              className="btn btn-outline"
              type="button"
              disabled={cases.length >= 20}
              onClick={() => setCases([...cases, emptyCase()])}
            >
              Add test case
            </button>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <footer>
              <button className="btn btn-primary" disabled={busy}>
                {busy ? "Running authorized retrieval…" : "Run and save check"}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {discard && (
        <Modal
          title="Discard unsaved retrieval cases?"
          onClose={() => setDiscard(false)}
        >
          <p>
            Unsaved queries are held in this form only. An unacknowledged
            submitted intent remains recoverable.
          </p>
          <footer>
            <button
              className="btn btn-outline"
              onClick={() => setDiscard(false)}
            >
              Keep editing
            </button>
            <button
              className="btn btn-primary"
              onClick={() => {
                setDiscard(false);
                setEditing(false);
                afterLeave.current();
              }}
            >
              Discard draft
            </button>
          </footer>
        </Modal>
      )}
      {removing && (
        <Modal
          title="Remove saved retrieval evidence?"
          onClose={() => {
            if (!busy) setRemoving(null);
          }}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                await api("/v1/retrieval-checks/" + removing.id, "DELETE", {
                  note,
                });
                setSelected(null);
                setRemoving(null);
                await load();
                setNotice(
                  "Active check evidence removed. Audit/backup retention remains separate.",
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <p>
              This removes the saved queries and result record from the active
              database. It does not change source documents. Audit and backup
              retention remain separate.
            </p>
            <label>
              Removal note
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
              <button className="btn btn-primary" disabled={busy}>
                Remove saved evidence
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </section>
  );
}
