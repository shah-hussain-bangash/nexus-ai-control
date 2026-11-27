import { useEffect, useRef, useState, useId } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import {
  billingStatementRequest,
  type BillingLine,
} from "./billingStatementRequest";
import "./live.css";
import "./enterpriseRuntime.css";
type Row = Record<string, any>;
const emptyLine = (ref: string): BillingLine => ({
  line_ref: ref,
  call_id: "",
  billed_usd: "",
  input_tokens: "",
  output_tokens: "",
  provider_request_id: "",
});
const usd = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 6,
  }).format(value / 1000000);
export function BillingStatementReviews({
  me,
  calls,
}: {
  me: Row;
  calls: Row[];
}) {
  const [reference, setReference] = useState(""),
    [period, setPeriod] = useState(new Date().toISOString().slice(0, 7)),
    [note, setNote] = useState("");
  const [lines, setLines] = useState<BillingLine[]>([emptyLine("line-1")]),
    [reviews, setReviews] = useState<Row[]>([]),
    [selected, setSelected] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null);
  const nextLine = useRef(2),
    optionsId = useId(),
    inspection = useRef(0);
  const canRead = me.permissions?.includes("export"),
    canCreate = me.permissions?.includes("members");
  const scope = liveIntentScope(
    "billing-review",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  async function refresh(at = offset) {
    const data = await api(`/v1/billing-reviews?offset=${at}&limit=20`);
    setReviews(data.items);
    setOffset(at);
    setNext(data.next_offset);
  }
  useEffect(() => {
    if (canRead) void refresh(0).catch((e: Error) => setMessage(e.message));
    return () => {
      inspection.current++;
    };
  }, [canRead]);
  async function act(task: () => Promise<Row>) {
    const active = ++inspection.current;
    setBusy(true);
    setMessage("");
    try {
      const row = await task();
      if (active !== inspection.current) return;
      setSelected(row);
      setMessage(
        `Saved comparison: ${row.status}. Budgets and charges are unchanged.`,
      );
      await refresh(0);
    } catch (e) {
      if (active === inspection.current)
        setMessage(e instanceof Error ? e.message : "Billing review failed.");
    } finally {
      if (active === inspection.current) setBusy(false);
    }
  }
  const update = (index: number, key: keyof BillingLine, value: string) =>
    setLines((rows) =>
      rows.map((line, i) => (i === index ? { ...line, [key]: value } : line)),
    );
  if (!canRead) return null;
  return (
    <details className="panel runtime-card">
      <summary>Compare a billing statement</summary>
      <h3>Selected-call billing comparison</h3>
      <p>
        Enter nonnegative USD charges from a statement and map each line to one
        local inference call. Up to 50 lines. This compares entered fields only;
        it does not verify the provider statement, adjust charges, settle
        unknown calls, or release held budget.
      </p>
      <p>
        Scope: current workspace and environment. Accounting month uses the call
        ledger's UTC month. Credits, tax, discounts and complete
        provider-account totals are outside this comparison.
      </p>
      {message && <p role="status">{message}</p>}
      {canCreate && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            try {
              const body = billingStatementRequest(
                reference,
                period,
                note,
                lines,
              );
              void act(() =>
                sendLiveIntent(sessionStorage, scope, body, (key) =>
                  api("/v1/billing-reviews", "POST", body, key),
                ),
              );
            } catch (e) {
              setMessage(
                e instanceof Error ? e.message : "Check statement fields.",
              );
            }
          }}
        >
          <label className="field">
            <span>Statement reference</span>
            <input
              required
              minLength={2}
              maxLength={120}
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Accounting month (UTC ledger)</span>
            <input
              required
              type="month"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            />
          </label>
          <datalist id={optionsId}>
            {calls.map((call) => (
              <option key={call.id} value={call.id}>
                {call.period} · {call.status}
              </option>
            ))}
          </datalist>
          {lines.map((line, index) => (
            <fieldset key={index}>
              <legend>Statement line {index + 1}</legend>
              <label className="field">
                <span>Line reference</span>
                <input
                  required
                  pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,63}"
                  value={line.line_ref}
                  onChange={(e) => update(index, "line_ref", e.target.value)}
                />
              </label>
              <label className="field">
                <span>Local call ID (from inference history)</span>
                <input
                  required
                  maxLength={64}
                  list={optionsId}
                  value={line.call_id}
                  onChange={(e) => update(index, "call_id", e.target.value)}
                />
              </label>
              <label className="field">
                <span>Statement charge in USD</span>
                <input
                  required
                  inputMode="decimal"
                  placeholder="0.000024"
                  value={line.billed_usd}
                  onChange={(e) => update(index, "billed_usd", e.target.value)}
                />
              </label>
              <label className="field">
                <span>Statement input tokens (optional)</span>
                <input
                  inputMode="numeric"
                  value={line.input_tokens}
                  onChange={(e) =>
                    update(index, "input_tokens", e.target.value)
                  }
                />
              </label>
              <label className="field">
                <span>Statement output tokens (optional)</span>
                <input
                  inputMode="numeric"
                  value={line.output_tokens}
                  onChange={(e) =>
                    update(index, "output_tokens", e.target.value)
                  }
                />
              </label>
              <label className="field">
                <span>Provider request ID (optional; never an API key)</span>
                <input
                  maxLength={200}
                  value={line.provider_request_id}
                  onChange={(e) =>
                    update(index, "provider_request_id", e.target.value)
                  }
                />
              </label>
              <button
                className="btn"
                type="button"
                disabled={busy || lines.length === 1}
                onClick={() =>
                  setLines((rows) => rows.filter((_, i) => i !== index))
                }
              >
                Remove line
              </button>
            </fieldset>
          ))}
          <button
            className="btn"
            type="button"
            disabled={busy || lines.length >= 50}
            onClick={() =>
              setLines((rows) => [
                ...rows,
                emptyLine(`line-${nextLine.current++}`),
              ])
            }
          >
            Add statement line
          </button>
          <label className="field">
            <span>Evidence note (avoid credentials or prompt text)</span>
            <textarea
              required
              minLength={10}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button
            className="btn btn-primary"
            disabled={busy || !reference.trim() || note.trim().length < 10}
          >
            Save selected-call comparison
          </button>
        </form>
      )}
      <div className="live-actions">
        <button
          className="btn"
          disabled={busy}
          onClick={() =>
            void refresh().catch((e: Error) => setMessage(e.message))
          }
        >
          Refresh saved reviews
        </button>
        <button
          className="btn"
          disabled={busy}
          onClick={() =>
            void act(async () => {
              const pending = readRecovery(sessionStorage, scope);
              if (!pending)
                throw Error(
                  "No unacknowledged billing review in this account and environment.",
                );
              const row = await api("/v1/billing-reviews/recover", "POST", {
                key: pending.key,
              });
              acknowledgeRecovery(sessionStorage, scope, pending, row);
              return row;
            })
          }
        >
          Recover submitted review
        </button>
      </div>
      <p>
        Recorded outcomes below reflect their saved snapshot. Open a review to
        check whether local usage has since changed. Separate reviews are not
        additive account totals.
      </p>
      {reviews.map((row) => (
        <button
          className="btn"
          key={row.id}
          disabled={busy}
          onClick={() =>
            void act(() =>
              api("/v1/billing-reviews/" + encodeURIComponent(row.id)),
            )
          }
        >
          {row.statement_ref} · {row.period} · {row.status} · {row.line_count}{" "}
          lines
        </button>
      ))}
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
      {selected && (
        <article aria-live="polite">
          <h4>
            {selected.statement_ref}:{" "}
            {selected.status === "matched"
              ? "Checked fields match"
              : "Review required"}
          </h4>
          {selected.stale && (
            <p role="status">
              Local call data changed after this snapshot. This saved review
              remains historical; submit a new review to compare current data.
            </p>
          )}
          <p>
            Selected statement lines: {usd(selected.billed_total_micro_usd)} ·
            recorded settled calls:{" "}
            {usd(selected.recorded_settled_total_micro_usd)} · statement amount
            for those settled calls:{" "}
            {usd(selected.compared_billed_total_micro_usd)}
          </p>
          <p>
            Settled-call amount difference (statement minus recorded):{" "}
            {usd(selected.settled_amount_delta_micro_usd)} · matched{" "}
            {selected.matched_lines} · discrepancies{" "}
            {selected.discrepancy_lines} · unresolved{" "}
            {selected.unresolved_lines}
          </p>
          <p>{selected.note}</p>
          {selected.items.map((item: Row) => (
            <div className="runtime-hit" key={item.line.line_ref}>
              <h4>
                {item.line.line_ref}: {item.status}
              </h4>
              <code>{item.line.call_id}</code>
              <p>
                Statement {usd(item.line.billed_micro_usd)} · recorded{" "}
                {item.local.charged_micro_usd === null
                  ? "unresolved"
                  : usd(item.local.charged_micro_usd)}{" "}
                · difference{" "}
                {item.amount_delta_micro_usd === null
                  ? "not compared"
                  : usd(item.amount_delta_micro_usd)}
              </p>
              <p>
                Checked fields:{" "}
                {item.checked_fields.join(", ") ||
                  "none; local call unresolved"}
                . Input-token difference{" "}
                {item.input_token_delta ?? "not checked"}; output-token
                difference {item.output_token_delta ?? "not checked"}; provider
                request ID{" "}
                {item.provider_request_id_match === null
                  ? "not checked"
                  : item.provider_request_id_match
                    ? "matches"
                    : "does not match"}
                .
              </p>
            </div>
          ))}
          <p>{selected.boundary}</p>
        </article>
      )}
    </details>
  );
}
