import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  availableCommands,
  capacityEstimate,
  costEstimate,
  emptyOperations,
  fileMetadata,
  transitionOperation,
  validateOperation,
  validateOperationalState,
  type OperationSpec,
  type OperationalState,
} from "../src/operationalModel.ts";
import {
  registerNavigationGuard,
  requestNavigationGuard,
} from "../src/navigationGuard.ts";
const modules = JSON.parse(
  readFileSync(
    new URL("../../backend/nexus/interface_catalog.json", import.meta.url),
    "utf8",
  ),
).modules;
const at = "2026-11-17T12:00:00Z";
function plan(spec: OperationSpec): OperationalState {
  return {
    records: [
      {
        id: "review-1",
        title: "Synthetic case",
        owner: "Review team",
        state: spec.initial_state,
        attributes: Object.fromEntries(
          spec.fields.map((f) => [f.id, f.default]),
        ),
      },
    ],
    events: [],
  };
}
test("all 18 dedicated operational experiences have valid defaults and executable transition graphs", () => {
  assert.equal(modules.length, 18);
  const kinds = new Set();
  for (const m of modules) {
    const s = m.operations as OperationSpec;
    kinds.add(s.kind);
    let state = plan(s);
    assert.deepEqual(validateOperation(s, state.records[0]), {});
    const first = availableCommands(s, state.records[0])[0];
    state = transitionOperation(
      s,
      state,
      "review-1",
      first.id,
      "happy_path",
      "Reviewed next transition",
      "event-1",
      at,
    );
    assert.equal(state.records[0].state, first.to_state);
    validateOperationalState(s, state);
  }
  assert.equal(kinds.size, 18);
});
test("run pause resume cancel retry and rollback follow valid states", () => {
  const s = modules.find((m: any) => m.id === "cloud_delivery").operations;
  let state = plan(s);
  for (const [i, cmd] of [
    "queue",
    "start",
    "pause",
    "resume",
    "cancel",
    "retry",
    "start",
    "complete",
    "rollback",
  ].entries()) {
    state = transitionOperation(
      s,
      state,
      "review-1",
      cmd,
      "happy_path",
      "Synthetic state transition",
      `event-${i}`,
      at,
    );
    validateOperationalState(s, state);
  }
  assert.equal(state.records[0].state, "rolled_back");
  assert.equal(state.events.length, 9);
});
test("denied, outage, uncertain and stale reviews preserve state without auto retry", () => {
  const s = modules[0].operations;
  for (const scenario of [
    "permission_denied",
    "dependency_unavailable",
    "timeout_unknown",
    "stale_revision",
  ]) {
    const initial = plan(s),
      state = transitionOperation(
        s,
        initial,
        "review-1",
        "request_review",
        scenario,
        "Observed failure safely",
        "event-1",
        at,
      );
    assert.equal(state.records[0].state, "draft");
    assert.equal(state.events[0].from_state, state.events[0].to_state);
    validateOperationalState(s, state);
    assert.equal(initial.events.length, 0);
  }
});
test("invalid transitions, role denial and malformed event chains fail", () => {
  const s = modules[0].operations,
    state = plan(s);
  assert.throws(() =>
    transitionOperation(
      s,
      state,
      "review-1",
      "activate_preview",
      "happy_path",
      "Reviewed",
      "e1",
      at,
    ),
  );
  assert.throws(() =>
    transitionOperation(
      s,
      state,
      "review-1",
      "request_review",
      "happy_path",
      "Reviewed",
      "e1",
      at,
      false,
    ),
  );
  assert.throws(() =>
    transitionOperation(
      s,
      state,
      "review-1",
      "request_review",
      "happy_path",
      "",
      "e1",
      at,
    ),
  );
  const forged = plan(s);
  forged.records[0].state = "active";
  assert.throws(() => validateOperationalState(s, forged));
});
test("numeric estimates use entered values and handle zero capacity", () => {
  assert.deepEqual(
    capacityEstimate({
      requests: "60",
      rate_limit: "30",
      concurrency: "4",
      duration: "10",
    }),
    { arrival: 60, admitted: 24, rejected: 36 },
  );
  assert.equal(
    capacityEstimate({
      requests: "10",
      rate_limit: "10",
      concurrency: "0",
      duration: "1",
    }).admitted,
    0,
  );
  assert.deepEqual(
    costEstimate({ budget: "100", estimated: "12.5", actual: "13.25" }),
    {
      budget: 100,
      estimated: 12.5,
      actual: 13.25,
      variance: 0.75,
      remaining: 86.75,
    },
  );
});
test("file intake accepts metadata only and rejects unsupported or oversized files atomically", () => {
  const s = modules.find((m: any) => m.id === "document_ingestion").operations;
  assert.deepEqual(fileMetadata(s, { name: "sample.PDF", size: 2048 }), {
    source: "sample.PDF",
    file_bytes: "2048",
  });
  assert.throws(() => fileMetadata(s, { name: "sample.exe", size: 1 }));
  assert.throws(() => fileMetadata(s, { name: "sample.pdf", size: 20971521 }));
});
test("schema, secret references and actual calendar dates validate before applying", () => {
  const s = modules[0].operations,
    p = plan(s).records[0];
  p.attributes.schema = "[]";
  p.attributes.secret_ref = "raw-token";
  p.attributes.endpoint = "https://token@example.invalid";
  const errors = validateOperation(s, p);
  assert.ok(errors.schema && errors.secret_ref && errors.endpoint);
  const ss = modules.find((m: any) => m.id === "identity_lifecycle").operations,
    r = plan(ss).records[0];
  r.attributes.expiry = "2026-02-31";
  assert.ok(validateOperation(ss, r).expiry);
});
test("navigation guard retains pending destination until user chooses to leave", () => {
  let changed = false,
    leave: (() => void) | undefined;
  assert.equal(
    requestNavigationGuard(() => {}),
    false,
  );
  const stop = registerNavigationGuard((next) => {
    leave = next;
  });
  assert.equal(
    requestNavigationGuard(() => {
      changed = true;
    }),
    true,
  );
  assert.equal(changed, false);
  leave?.();
  assert.equal(changed, true);
  stop();
  assert.equal(
    requestNavigationGuard(() => {}),
    false,
  );
});
test("stale cleanup cannot remove a newer active navigation guard", () => {
  const old = registerNavigationGuard(() => {});
  let blocked = false;
  const newer = registerNavigationGuard(() => {
    blocked = true;
  });
  old();
  assert.equal(
    requestNavigationGuard(() => {}),
    true,
  );
  assert.equal(blocked, true);
  newer();
});
