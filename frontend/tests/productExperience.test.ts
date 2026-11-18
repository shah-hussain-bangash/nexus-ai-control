import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  newUiRecord,
  previewTransition,
  uiInputs,
  phases,
  phaseFor,
  journeys,
  screenStates,
  detailTabs,
} from "../src/productExperience.ts";
const modules = JSON.parse(
  readFileSync(
    new URL("../../backend/nexus/interface_catalog.json", import.meta.url),
    "utf8",
  ),
).modules;
const all = modules.flatMap((m: any) => m.features);
const first = all[0];
test("the product baseline covers each catalog area once and every journey target exists", () => {
  assert.equal(modules.length, 18);
  assert.equal(all.length, 216);
  const phaseModules = phases.flatMap((p) => [...p.modules]);
  assert.equal(new Set(phaseModules).size, 18);
  assert.equal(phaseModules.length, 18);
  for (const m of modules) assert.ok(phaseFor(m.id));
  assert.equal(journeys.length, 6);
  for (const j of journeys) {
    assert.equal(j.steps.length, 5);
    for (const id of j.steps)
      assert.ok(
        all.some((f: any) => f.id === id),
        id,
      );
  }
  assert.equal(screenStates.length, 8);
  assert.equal(detailTabs.length, 6);
});
test("all catalog functions support valid examples while refusing malformed numeric, reference and choice inputs", () => {
  for (const f of all) {
    const row = newUiRecord(f, "example");
    assert.deepEqual(uiInputs(f, row), {});
    for (const field of f.fields) {
      if (["number", "reference", "select"].includes(field.type)) {
        const bad = {
          ...row,
          values: { ...row.values, [field.id]: "not-a-valid-value" },
        };
        assert.ok(uiInputs(f, bad)[field.id], f.id + ":" + field.id);
      }
    }
  }
});
test("the review journey separates submit and decision personas and retains a versioned event trail", () => {
  const draft = newUiRecord(first, "record");
  const requested = previewTransition(
    draft,
    "submit",
    "Operator",
    1,
    "Prepared this synthetic scope.",
    "ready",
  );
  assert.equal(draft.status, "draft");
  assert.equal(requested.status, "in_review");
  assert.equal(requested.version, 2);
  assert.throws(() =>
    previewTransition(
      requested,
      "approve",
      "Operator",
      2,
      "Review complete.",
      "ready",
    ),
  );
  const rework = previewTransition(
    requested,
    "rework",
    "Reviewer",
    2,
    "Revise the synthetic mapping.",
    "ready",
  );
  assert.equal(rework.status, "changes_requested");
  const submitted = previewTransition(
    rework,
    "submit",
    "Operator",
    3,
    "Updated the synthetic mapping.",
    "ready",
  );
  const approved = previewTransition(
    submitted,
    "approve",
    "Reviewer",
    4,
    "Reviewed values and effect.",
    "ready",
  );
  assert.equal(approved.status, "approved");
  assert.equal(approved.events.length, 4);
  assert.throws(() =>
    previewTransition(
      approved,
      "approve",
      "Reviewer",
      5,
      "Duplicate decision.",
      "ready",
    ),
  );
});
test("auditors, denied access, stale versions, empty notes and unavailable services cannot mutate examples", () => {
  const draft = newUiRecord(first, "record");
  for (const state of [
    "empty",
    "loading",
    "permission_denied",
    "validation_error",
    "dependency_unavailable",
    "stale_revision",
  ] as const)
    assert.throws(() =>
      previewTransition(
        draft,
        "submit",
        "Operator",
        1,
        "Prepared a request.",
        state,
      ),
    );
  assert.throws(() =>
    previewTransition(
      draft,
      "submit",
      "Auditor",
      1,
      "Prepared a request.",
      "ready",
    ),
  );
  assert.throws(() =>
    previewTransition(
      draft,
      "submit",
      "Operator",
      0,
      "Prepared a request.",
      "ready",
    ),
  );
  assert.throws(() =>
    previewTransition(draft, "submit", "Operator", 1, "  ", "ready"),
  );
  assert.equal(draft.version, 1);
  assert.equal(draft.events.length, 0);
});
test("uncertain outcomes expose reconciliation rather than resubmission", () => {
  const draft = newUiRecord(first, "record");
  const unknown = previewTransition(
    draft,
    "submit",
    "Operator",
    1,
    "Connection interrupted in this rehearsal.",
    "timeout_unknown",
  );
  assert.equal(unknown.status, "outcome_unknown");
  assert.throws(() =>
    previewTransition(
      unknown,
      "submit",
      "Operator",
      2,
      "Attempt a duplicate.",
      "ready",
    ),
  );
  const reconciled = previewTransition(
    unknown,
    "reconcile",
    "Reviewer",
    2,
    "Inspected the existing preview request.",
    "ready",
  );
  assert.equal(reconciled.status, "in_review");
  assert.equal(reconciled.version, 3);
});
