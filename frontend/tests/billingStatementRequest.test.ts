import test from "node:test";
import assert from "node:assert/strict";
import {
  usdToMicros,
  billingStatementRequest,
} from "../src/billingStatementRequest.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";
test("USD conversion preserves integer micro-units without floating-point amount parsing", () => {
  assert.equal(usdToMicros("0.000001"), 1);
  assert.equal(usdToMicros("0.1"), 100000);
  assert.equal(usdToMicros("42.000003"), 42000003);
  assert.equal(usdToMicros("1000000"), 1000000000000);
  for (const input of [
    "-1",
    "1e3",
    "NaN",
    "0.0000001",
    "1000000.000001",
    "",
    "$1",
  ])
    assert.throws(() => usdToMicros(input));
});
test("statement request snapshots selected rows and omits unchecked optional fields", () => {
  const lines = [
    {
      line_ref: "line-1",
      call_id: "call",
      billed_usd: "0.000024",
      input_tokens: "",
      output_tokens: "4",
      provider_request_id: "",
    },
  ];
  const body = billingStatementRequest(
    " Statement ",
    "2026-11",
    " Reviewed evidence. ",
    lines,
  );
  lines[0].call_id = "changed";
  assert.deepEqual(body, {
    statement_ref: "Statement",
    period: "2026-11",
    currency: "USD",
    note: "Reviewed evidence.",
    lines: [
      {
        line_ref: "line-1",
        call_id: "call",
        billed_micro_usd: 24,
        output_tokens: 4,
      },
    ],
  });
});
test("lost billing replies preserve their own scoped intent without storing statement fields", async () => {
  const data = new Map<string, string>();
  const store = {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
  };
  const scope = liveIntentScope("billing-review", "org", "owner", "staging");
  const body = { statement_ref: "Private statement", lines: [] };
  let key = "";
  await assert.rejects(
    sendLiveIntent(store, scope, body, async (value) => {
      key = value;
      throw Error("Lost reply");
    }),
  );
  assert.ok(![...data.values()].join("").includes("Private statement"));
  for (const other of [
    liveIntentScope("billing-review", "org", "owner", "production"),
    liveIntentScope("billing-review", "other", "owner", "staging"),
    liveIntentScope("billing-review", "org", "other", "staging"),
    liveIntentScope("indexed-review", "org", "owner", "staging"),
  ])
    assert.equal(readRecovery(store, other), null);
  await sendLiveIntent(store, scope, body, async (value) => {
    assert.equal(value, key);
    return { id: "review", status: "matched" };
  });
  assert.equal(readRecovery(store, scope), null);
});
