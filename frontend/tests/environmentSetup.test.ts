import test from "node:test";
import assert from "node:assert/strict";
import {
  canControlEnvironment,
  environmentControlPayload,
  environmentCreatePayload,
  environmentStateLabel,
} from "../src/environmentSetup.ts";
import type { EnvironmentRecord } from "../src/environmentSetup.ts";
const row: EnvironmentRecord = {
  key: "production",
  name: "Production",
  state: "preparing",
  version: 3,
  human_runtime_enabled: false,
};

test("preparation validates keys and audit reasons before sending a request", () => {
  assert.deepEqual(
    environmentCreatePayload(
      " production ",
      " Production ",
      " Reviewed setup ",
    ),
    { key: "production", name: "Production", note: "Reviewed setup" },
  );
  for (const key of [
    "a",
    "A-test",
    "../production",
    "two words",
    "a".repeat(33),
  ])
    assert.throws(() =>
      environmentCreatePayload(key, "Production", "Reviewed setup"),
    );
  for (const note of [
    "    ",
    "tiny",
    "a".repeat(501),
    "review\nagain",
    "review\u007fagain",
  ])
    assert.throws(() =>
      environmentCreatePayload("production", "Production", note),
    );
  assert.throws(() =>
    environmentCreatePayload("production", "\t\t", "Reviewed setup"),
  );
});

test("archive and restore preserve the reviewed version", () => {
  assert.deepEqual(
    environmentControlPayload(row, "staging", "archive", "Setup paused"),
    { command: "archive", expected_version: 3, note: "Setup paused" },
  );
  const archived = { ...row, state: "archived", version: 4 };
  assert.equal(canControlEnvironment(archived, "staging", "archive"), false);
  assert.equal(canControlEnvironment(archived, "staging", "restore"), true);
  assert.equal(
    environmentControlPayload(archived, "staging", "restore", "Resume setup")
      .expected_version,
    4,
  );
});

test("current, runtime enabled, unknown and malformed records offer no lifecycle controls", () => {
  for (const protectedRow of [
    { ...row, key: "staging" },
    { ...row, human_runtime_enabled: true },
    { ...row, state: "active" },
    { ...row, state: "unexpected" },
    { ...row, version: 0 },
    { ...row, version: 1.5 },
    { ...row, key: "../invalid" },
  ]) {
    for (const command of ["archive", "restore"] as const) {
      assert.equal(
        canControlEnvironment(protectedRow, "staging", command),
        false,
      );
      assert.throws(() =>
        environmentControlPayload(
          protectedRow,
          "staging",
          command,
          "Reviewed setup",
        ),
      );
    }
  }
  assert.equal(canControlEnvironment(row, "production", "archive"), false);
  assert.equal(
    environmentStateLabel(
      { ...row, key: "staging", state: "active", human_runtime_enabled: true },
      "staging",
    ),
    "Current",
  );
  assert.equal(environmentStateLabel(row, "staging"), "Preparing");
  assert.equal(
    environmentStateLabel({ ...row, state: "archived" }, "staging"),
    "Archived",
  );
  assert.equal(
    environmentStateLabel({ ...row, state: "active" }, "staging"),
    "Unavailable",
  );
});
