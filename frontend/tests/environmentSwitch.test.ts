import test from "node:test";
import assert from "node:assert/strict";
import { activationPayload, canActivateEnvironment, selectionPayload } from "../src/environmentSwitch.ts";
import { api, setCsrf } from "../src/api.ts";
import { sessionContext } from "../src/sessionContext.ts";
const row = { key: "production", name: "Production", state: "preparing", version: 4, human_runtime_enabled: false, owner_assigned: true };
const context = { workspace_id: "northstar", user_id: "owner", environment: "staging", revision: 3, binding_id: "11111111-1111-4111-8111-111111111111" };
test("activation requires an assigned owner, local availability, an empty preparing namespace and review", () => {
  assert.deepEqual(activationPayload(row, "staging", true, "Reviewed local activation", true), { expected_version: 4, note: "Reviewed local activation", reviewed: true });
  for (const invalid of [{ ...row, owner_assigned: false }, { ...row, state: "active" }, { ...row, state: "archived" }, { ...row, key: "staging" }, { ...row, human_runtime_enabled: true }, { ...row, version: 0 }, { ...row, version: 1.2 }, { ...row, key: "../prod" }]) {
    assert.equal(canActivateEnvironment(invalid, "staging", true), false);
    assert.throws(() => activationPayload(invalid, "staging", true, "Reviewed activation", true));
  }
  assert.throws(() => activationPayload(row, "staging", false, "Reviewed activation", true));
  assert.throws(() => activationPayload(row, "staging", true, "Reviewed activation", false));
  assert.throws(() => activationPayload(row, "staging", true, "   ", true));
});
test("selection carries both reviewed revisions and the current session binding", () => {
  const choice = { key: "production", name: "Production", version: 5 };
  assert.deepEqual(selectionPayload(context, choice, true), { workspace_id: "northstar", environment: "production", expected_revision: 3, expected_binding_id: context.binding_id, expected_environment_version: 5, reviewed: true });
  assert.throws(() => selectionPayload(context, choice, false));
  for (const invalid of [{ ...choice, key: "staging" }, { ...choice, key: "../prod" }, { ...choice, version: 0 }, { ...choice, version: 1.2 }]) assert.throws(() => selectionPayload(context, invalid, true));
  for (const invalid of [{ ...context, revision: 0 }, { ...context, binding_id: "" }, { ...context, workspace_id: "" }]) assert.throws(() => selectionPayload(invalid, choice, true));
});
test("logout carries the selected environment and session revision after switching", async () => {
  const original = globalThis.fetch;
  sessionContext.adopt({ user: { id: "owner", org_id: "northstar" }, environment: "production", runtime_context: { ...context, environment: "production" } });
  setCsrf("selected-session-csrf");
  try {
    let captured: RequestInit | undefined;
    globalThis.fetch = async (_input, init) => { captured = init; return new Response(JSON.stringify({ ok: true })); };
    await api("/auth/logout", "POST", {});
    const h = captured!.headers as Record<string, string>;
    assert.equal(h["X-Nexus-Context-Revision"], "3");
    assert.equal(h["X-Nexus-Context-ID"], context.binding_id);
    assert.equal(h["X-Nexus-Environment"], "production");
    assert.equal(h["X-CSRF-Token"], "selected-session-csrf");
  } finally { globalThis.fetch = original; sessionContext.clear(); setCsrf(""); }
});
