import test from "node:test";
import assert from "node:assert/strict";
import {
  canControlRuntime,
  runtimeControlPayload,
} from "../src/environmentRuntime.ts";
import { environmentStateLabel } from "../src/environmentSetup.ts";
const row = {
  key: "production",
  name: "Production",
  version: 3,
  state: "active",
  human_runtime_enabled: true,
  owner_assigned: true,
  selected_sessions: 2,
  unfinished_work: {
    actions: 0,
    durable_runs: 0,
    ingestion_jobs: 0,
    inference_calls: 0,
  },
};
test("reviewed runtime control pins the environment version and selected-session count", () => {
  assert.deepEqual(
    runtimeControlPayload(
      row,
      "staging",
      true,
      "pause",
      "Reviewed local pause",
      true,
    ),
    {
      command: "pause",
      expected_version: 3,
      expected_selected_sessions: 2,
      note: "Reviewed local pause",
      reviewed: true,
    },
  );
  const paused = {
    ...row,
    state: "suspended",
    human_runtime_enabled: false,
    selected_sessions: 0,
    version: 4,
  };
  assert.equal(canControlRuntime(paused, "staging", true, "resume"), true);
  assert.equal(canControlRuntime(paused, "staging", true, "pause"), false);
  assert.equal(environmentStateLabel(paused, "staging"), "Paused");
});
test("runtime control rejects current, staging, busy, incomplete, nonlocal and unreviewed snapshots", () => {
  for (const invalid of [
    { ...row, key: "staging" },
    { ...row, owner_assigned: false },
    { ...row, version: 1.5 },
    { ...row, selected_sessions: -1 },
    { ...row, unfinished_work: undefined },
    { ...row, unfinished_work: { actions: 0 } },
    { ...row, unfinished_work: { ...row.unfinished_work, inference_calls: 1 } },
    { ...row, unfinished_work: { ...row.unfinished_work, future_jobs: 1 } },
  ]) {
    assert.equal(canControlRuntime(invalid, "staging", true, "pause"), false);
    assert.throws(() =>
      runtimeControlPayload(
        invalid,
        "staging",
        true,
        "pause",
        "Reviewed pause",
        true,
      ),
    );
  }
  assert.equal(canControlRuntime(row, "production", true, "pause"), false);
  assert.equal(canControlRuntime(row, "staging", false, "pause"), false);
  assert.throws(() =>
    runtimeControlPayload(
      row,
      "staging",
      true,
      "pause",
      "Reviewed pause",
      false,
    ),
  );
  assert.throws(() =>
    runtimeControlPayload(row, "staging", true, "pause", "   ", true),
  );
});
