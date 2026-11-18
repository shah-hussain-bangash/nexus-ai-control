import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  HANDOFF_LIMIT,
  makeHandoff,
  parseHandoff,
  reviewComplete,
  reviewCriteria,
} from "../src/uiHandoff.ts";
import { newUiRecord, previewTransition } from "../src/productExperience.ts";
const modules = JSON.parse(
  readFileSync(
    new URL("../../backend/nexus/interface_catalog.json", import.meta.url),
    "utf8",
  ),
).modules;
const scope = { organization: "review-org", user: "review-user" },
  f = modules[0].features[0];
function exported() {
  return makeHandoff(modules, [newUiRecord(f, "UI-example")], [], {}, scope);
}
function parse(value: any, s = scope) {
  return parseHandoff(JSON.stringify(value), modules, s);
}
test("UI handoff round-trip preserves bounded records and complete review checklists", () => {
  const checks = { [f.id]: reviewCriteria.map((c) => c.id) };
  assert.equal(reviewComplete(checks, f.id), true);
  const saved = makeHandoff(
    modules,
    [newUiRecord(f, "UI-example")],
    [f.id],
    checks,
    scope,
  );
  const restored = parse(saved);
  assert.equal(restored.records.length, 1);
  assert.deepEqual(restored.reviewed, [f.id]);
  assert.deepEqual(restored.checks, checks);
  assert.equal(restored.legacy, false);
  assert.equal(saved.backend_activated, false);
  assert.equal(saved.production_accepted, false);
});
test("handoffs cannot move between account or organization scopes", () => {
  const data = exported();
  for (const other of [
    { ...scope, user: "another" },
    { ...scope, organization: "another" },
  ])
    assert.throws(() => parse(data, other));
});
test("missing, duplicate and unknown catalog functions are rejected", () => {
  for (const mutate of [
    (d: any) => d.modules.pop(),
    (d: any) => d.modules[0].features.pop(),
    (d: any) => (d.modules[0].features[0].id = "unknown"),
    (d: any) => (d.modules[0].features[1] = d.modules[0].features[0]),
  ]) {
    const data = exported();
    mutate(data);
    assert.throws(() => parse(data));
  }
});
test("import does not trust file-defined field schemas or unsafe values", () => {
  const data: any = exported();
  data.modules[0].features[0].fields = [{ id: "attack", default: "x" }];
  data.records[0].values = { attack: "x" };
  assert.throws(() => parse(data));
  const bad: any = exported();
  bad.records[0].values[f.fields[0].id] = "";
  assert.throws(() => parse(bad));
  const refs = modules
    .flatMap((m: any) => m.features)
    .find((x: any) => x.fields.some((y: any) => y.type === "reference"));
  const r = newUiRecord(refs, "UI-secret");
  r.values[refs.fields.find((x: any) => x.type === "reference").id] =
    "actual-secret-value";
  assert.throws(() => makeHandoff(modules, [r], [], {}, scope));
});
test("unknown flags, malformed versions and oversized or unsafe JSON fail closed", () => {
  for (const mutation of [
    (d: any) => (d.backend_activated = true),
    (d: any) => (d.production_accepted = true),
    (d: any) => (d.schema = 99),
    (d: any) => (d.records[0].version = -1),
    (d: any) =>
      (d.records[0].events = [
        { at: "not-date", label: "approve", note: "Review note" },
      ]),
  ]) {
    const data = exported();
    mutation(data);
    assert.throws(() => parse(data));
  }
  assert.throws(() => parseHandoff('{"__proto__":{}}', modules, scope));
  assert.throws(() =>
    parseHandoff(" ".repeat(HANDOFF_LIMIT + 1), modules, scope),
  );
});
test("review markers require all criteria and legacy markers are not promoted automatically", () => {
  const data: any = exported();
  data.modules[0].features[0].ui_reviewed = true;
  assert.throws(() => parse(data));
  data.release = "0.14.0";
  delete data.format;
  delete data.schema;
  delete data.workspace_scope;
  const old = parse(data);
  assert.equal(old.legacy, true);
  assert.deepEqual(old.reviewed, []);
  assert.deepEqual(old.records.length, 1);
});
test("metadata-only export preserves UI reviews without retaining examples", () => {
  const checks = { [f.id]: reviewCriteria.map((c) => c.id) },
    data = makeHandoff(
      modules,
      [newUiRecord(f, "UI-example")],
      [f.id],
      checks,
      scope,
      false,
    );
  assert.deepEqual(data.records, []);
  assert.deepEqual(parse(data).reviewed, [f.id]);
});
test("duplicate examples and unbounded histories cannot be restored or extended", () => {
  const data: any = exported();
  data.records.push(data.records[0]);
  assert.throws(() => parse(data));
  const bounded = newUiRecord(f, "UI-example");
  bounded.events = Array.from({ length: 50 }, () => ({
    at: new Date().toISOString(),
    label: "submit",
    note: "Synthetic event note.",
  }));
  assert.throws(() =>
    previewTransition(
      bounded,
      "submit",
      "Operator",
      1,
      "Another event.",
      "ready",
    ),
  );
  bounded.events.push(bounded.events[0]);
  assert.throws(() => makeHandoff(modules, [bounded], [], {}, scope));
});

test("one example for every agreed function fits into a single resumable handoff", () => {
  const records = modules
    .flatMap((m: any) => m.features)
    .map((f: any, i: number) => newUiRecord(f, "UI-" + i));
  const data = makeHandoff(modules, records, [], {}, scope);
  assert.equal(parse(data).records.length, 216);
});
