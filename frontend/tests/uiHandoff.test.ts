import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  HANDOFF_LIMIT,
  makeHandoff,
  parseHandoff,
  reviewComplete,
  reviewCriteria,
  readHandoff,
  assertHandoffScope,
} from "../src/uiHandoff.ts";
import { newUiRecord, previewTransition } from "../src/productExperience.ts";
const modules = JSON.parse(
  readFileSync(
    new URL("../../backend/nexus/interface_catalog.json", import.meta.url),
    "utf8",
  ),
).modules;
const scope = {
    organization: "review-org",
    user: "review-user",
    environment: "staging",
  },
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

test("new handoffs retain explicit environment scope in full and review-only exports", () => {
  const production = { ...scope, environment: "production" };
  for (const include of [true, false]) {
    const data = makeHandoff(
      modules,
      [newUiRecord(f, "UI-production")],
      [],
      {},
      production,
      include,
    );
    assert.equal(data.schema, 2);
    assert.equal(data.release, "0.16.2");
    assert.deepEqual(data.workspace_scope, production);
    assert.deepEqual(parse(data, production).scope, production);
    assert.equal(parse(data, production).environmentImplicit, false);
    assert.throws(() => parse(data, scope));
  }
});

test("older scoped files preserve staging review work without acquiring production scope", () => {
  for (const release of ["0.15.0", "0.16.0"]) {
    const data: any = makeHandoff(
      modules,
      [newUiRecord(f, "UI-old")],
      [f.id],
      { [f.id]: reviewCriteria.map((c) => c.id) },
      scope,
    );
    data.schema = 1;
    data.release = release;
    delete data.workspace_scope.environment;
    const restored = parse(data);
    assert.equal(restored.environmentImplicit, true);
    assert.equal(restored.legacy, false);
    assert.deepEqual(restored.reviewed, [f.id]);
    assert.equal(restored.records.length, 1);
    assert.throws(() => parse(data, { ...scope, environment: "production" }));
    assert.equal(
      makeHandoff(
        modules,
        restored.records,
        restored.reviewed,
        restored.checks,
        scope,
      ).workspace_scope.environment,
      "staging",
    );
  }
});

test("release or schema downgrades cannot smuggle another environment into staging", () => {
  const data: any = exported();
  for (const release of ["0.14.0", "0.15.0", "0.16.0"]) {
    const modified = structuredClone(data);
    modified.release = release;
    assert.throws(() => parse(modified));
    modified.schema = 1;
    modified.workspace_scope.environment = "production";
    assert.throws(() => parse(modified));
  }
});

test("unscoped legacy examples remain staging-only and never restore review attestations", () => {
  const data: any = exported();
  data.release = "0.14.0";
  delete data.workspace_scope;
  delete data.schema;
  delete data.format;
  data.modules[0].features[0].ui_reviewed = true;
  const restored = parse(data);
  assert.equal(restored.legacy, true);
  assert.deepEqual(restored.reviewed, []);
  assert.deepEqual(restored.checks, {});
  assert.throws(() => parse(data, { ...scope, environment: "production" }));
});

test("invalid target scope and missing new-file environment fail closed", () => {
  for (const change of [
    { environment: undefined },
    { environment: "Staging" },
    { environment: "../stage" },
    { organization: "" },
    { user: "line\nbreak" },
  ]) {
    assert.throws(() =>
      makeHandoff(modules, [], [], {}, { ...scope, ...change } as any),
    );
    assert.throws(() => parse(exported(), { ...scope, ...change } as any));
  }
  const data: any = exported();
  delete data.workspace_scope.environment;
  assert.throws(() => parse(data));
});

test("candidate application must match its original actor, workspace and environment", () => {
  const candidate = parse(exported());
  assertHandoffScope(candidate.scope, scope);
  for (const change of [
    { environment: "production" },
    { user: "another" },
    { organization: "another" },
  ])
    assert.throws(() =>
      assertHandoffScope(candidate.scope, { ...scope, ...change }),
    );
});

test("a file that finishes after the context changes cannot become an import candidate", async () => {
  let resolve!: (raw: string) => void;
  let current = true;
  const pending = readHandoff(
    new Promise<string>((r) => (resolve = r)),
    modules,
    scope,
    () => current,
  );
  current = false;
  resolve(JSON.stringify(exported()));
  await assert.rejects(pending, /context changed/);
});

test("a later file selection wins and the captured target scope cannot be relabelled", async () => {
  let resolve!: (raw: string) => void;
  let ticket = 1;
  const target = { ...scope };
  const older = readHandoff(
    new Promise<string>((r) => (resolve = r)),
    modules,
    target,
    () => ticket === 1,
  );
  ticket = 2;
  target.environment = "production";
  const newer = await readHandoff(
    Promise.resolve(JSON.stringify(exported())),
    modules,
    scope,
    () => ticket === 2,
  );
  resolve(JSON.stringify(exported()));
  await assert.rejects(older);
  assert.deepEqual(newer.scope, scope);
  const mutable = { ...scope };
  let finish!: (raw: string) => void;
  const captured = readHandoff(
    new Promise<string>((r) => (finish = r)),
    modules,
    mutable,
    () => true,
  );
  mutable.environment = "production";
  finish(JSON.stringify(exported()));
  assert.deepEqual((await captured).scope, scope);
});
