import test from "node:test";
import assert from "node:assert/strict";
import {
  supplierCheckPayload,
  supplierCheckOutcome,
  supplierCheckLabel,
  type SupplierCheck,
} from "../src/connectorCheck.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery, acknowledgeRecovery } from "../src/inferenceRecovery.ts";
const profile = {
  mode: "synthetic",
  destination: "mock-business-v1",
  configured_host: "",
  contract: "nexus-business-v1",
};
const route = {
  grant_id: "grant-id",
  agent_id: "agent-id",
  agent_name: "Supplier Scout",
  agent_generation: 3,
  tool_id: "tool-id",
  tool_name: "Supplier lookup",
  tool_version: "1.0",
};
const check: SupplierCheck = {
  id: "check-id",
  status: "verified",
  reason: "SCOPED_READ",
  supplier_id: "SUP-DEMO-104",
  connector_mode: "synthetic",
  verified: true,
  external_ref: "SUP-TEST",
  trace_id: "trace-id",
  updated: 1,
};
test("supplier review pins the connector and granted route without accepting operation or URL fields", () => {
  const body = supplierCheckPayload(
    profile,
    route,
    " SUP-DEMO-104 ",
    " Reviewed supplier lookup ",
    true,
  );
  assert.deepEqual(body, {
    agent_id: "agent-id",
    tool_id: "tool-id",
    expected_grant_id: "grant-id",
    expected_agent_generation: 3,
    expected_tool_version: "1.0",
    expected_destination: "mock-business-v1",
    supplier_id: "SUP-DEMO-104",
    note: "Reviewed supplier lookup",
    reviewed: true,
  });
  assert.throws(() =>
    supplierCheckPayload(profile, route, "bad/path", "Reviewed lookup", true),
  );
  assert.throws(() =>
    supplierCheckPayload(profile, route, "SUP-104", "Reviewed lookup", false),
  );
  assert.throws(() =>
    supplierCheckPayload(
      { ...profile, destination: "unreviewed" },
      route,
      "SUP-104",
      "Reviewed lookup",
      true,
    ),
  );
  assert.throws(() =>
    supplierCheckPayload(
      profile,
      { ...route, agent_generation: 0 },
      "SUP-104",
      "Reviewed lookup",
      true,
    ),
  );
});
test("synthetic verification and uncertain results never imply customer acceptance", () => {
  assert.equal(supplierCheckLabel(check), "Verified synthetic lookup");
  assert.equal(
    supplierCheckLabel({ ...check, connector_mode: "http" }),
    "Verified supplier lookup",
  );
  assert.match(
    supplierCheckLabel({
      ...check,
      status: "outcome_unknown",
      verified: false,
    }),
    /uncertain/,
  );
  assert.match(
    supplierCheckLabel({ ...check, status: "future_state", verified: false }),
    /investigation/,
  );
  const submitted = { id: "a".repeat(64), status: "submitted", check };
  assert.equal(supplierCheckOutcome(submitted).check?.id, "check-id");
  assert.throws(() => supplierCheckOutcome({ ...submitted, check: null }));
  assert.throws(() =>
    supplierCheckOutcome({
      ...submitted,
      status: "cancelled-without-receipt",
      check: null,
    }),
  );
});
test("interrupted intake retains an actor/environment key until cancellation is acknowledged", async () => {
  const values = new Map<string, string>(),
    storage = {
      getItem: (key: string) => values.get(key) || null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    };
  const scope = liveIntentScope(
    "connector-check",
    "workspace",
    "owner",
    "staging",
  );
  const body = supplierCheckPayload(
    profile,
    route,
    "SUP-104",
    "Reviewed lookup",
    true,
  );
  await assert.rejects(
    sendLiveIntent(
      storage,
      scope,
      body,
      async () => {
        throw Error("Interrupted");
      },
      () => "retained-supplier-key-001",
    ),
  );
  const pending = readRecovery(storage, scope)!;
  await assert.rejects(
    sendLiveIntent(
      storage,
      scope,
      { ...body, supplier_id: "different" },
      async () => ({ id: "a".repeat(64), status: "submitted", check }),
    ),
  );
  assert.equal(
    readRecovery(
      storage,
      liveIntentScope("connector-check", "workspace", "owner", "production"),
    ),
    null,
  );
  assert.equal(
    readRecovery(
      storage,
      liveIntentScope("connector-check", "workspace", "another", "staging"),
    ),
    null,
  );
  acknowledgeRecovery(
    storage,
    scope,
    pending,
    supplierCheckOutcome({ id: "b".repeat(64), status: "cancelled" }),
  );
  assert.equal(readRecovery(storage, scope), null);
});
