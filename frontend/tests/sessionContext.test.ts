import test from "node:test";
import assert from "node:assert/strict";
import { ContextStore, sessionContext } from "../src/sessionContext.ts";
import { api, setCsrf } from "../src/api.ts";
import { IntentKeyRegistry, submitIntent } from "../src/runIntent.ts";
const me = (changes: Record<string, unknown> = {}) => ({
  user: { org_id: "northstar", id: "owner" },
  environment: "staging",
  runtime_context: {
    workspace_id: "northstar",
    user_id: "owner",
    environment: "staging",
    revision: 1,
    binding_id: "11111111-1111-4111-8111-111111111111",
    ...changes,
  },
});

test("context changes invalidate old requests while repeated discovery preserves the epoch", () => {
  const store = new ContextStore();
  const initial = store.capture();
  let changes = 0;
  const unsubscribe = store.subscribe(() => changes++);
  store.adopt(me());
  assert.equal(store.current(initial), false);
  const first = store.capture();
  store.adopt(me());
  assert.equal(store.current(first), true);
  store.adopt(me({ revision: 2 }));
  assert.equal(store.current(first), false);
  assert.equal(changes, 2);
  unsubscribe();
  store.clear();
  assert.equal(changes, 2);
});
test("new sessions and identities reset the context; invalid discovery cannot replace it", () => {
  const store = new ContextStore();
  store.adopt(me());
  const first = store.capture();
  store.adopt(me({ binding_id: "22222222-2222-4222-8222-222222222222" }));
  assert.equal(store.current(first), false);
  const current = store.capture();
  for (const invalid of [
    { revision: 0 },
    { revision: 1.5 },
    { user_id: "another" },
    { environment: undefined },
    { binding_id: "-".repeat(36) },
  ])
    assert.throws(() => store.adopt(me(invalid)));
  assert.equal(store.current(current), true);
  assert.equal(Object.isFrozen(current.context), true);
});
test("API pins runtime requests, leaves discovery unpinned and rejects late responses", async () => {
  sessionContext.clear();
  sessionContext.adopt(me());
  setCsrf("private-test-csrf");
  const original = globalThis.fetch;
  try {
    let captured: RequestInit | undefined;
    globalThis.fetch = async (_input, init) => {
      captured = init;
      return new Response(JSON.stringify({ ok: true }));
    };
    await api("/v1/agents", "POST", {});
    assert.equal(
      (captured!.headers as Record<string, string>)["X-Nexus-Context-Revision"],
      "1",
    );
    assert.equal(
      (captured!.headers as Record<string, string>)["X-CSRF-Token"],
      "private-test-csrf",
    );
    await api("/v1/me");
    assert.equal(
      (captured!.headers as Record<string, string>)["X-Nexus-Context-ID"],
      undefined,
    );
    let resolve!: (value: Response) => void;
    globalThis.fetch = () => new Promise<Response>((r) => (resolve = r));
    const pending = api("/v1/agents");
    sessionContext.adopt(me({ revision: 2 }));
    resolve(new Response(JSON.stringify({ private: "old data" })));
    await assert.rejects(
      pending,
      (error: any) => error.code === "STALE_CONTEXT_RESPONSE",
    );
  } finally {
    globalThis.fetch = original;
    sessionContext.clear();
    setCsrf("");
  }
});
test("stale server context invalidates client memory", async () => {
  sessionContext.adopt(me());
  const old = sessionContext.capture();
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({
          error: { code: "STALE_SESSION_CONTEXT", message: "Refresh" },
        }),
        { status: 409 },
      );
    await assert.rejects(api("/v1/agents"));
    assert.equal(sessionContext.current(old), false);
    assert.equal(sessionContext.capture().context, null);
  } finally {
    globalThis.fetch = original;
    sessionContext.clear();
  }
});

test("view resets retain uncertain action keys only in their original actor context", async () => {
  const registry = new IntentKeyRegistry();
  const original = registry.forContext("northstar:owner:staging");
  await assert.rejects(
    submitIntent(
      original,
      "fingerprint",
      async () => {
        throw Error("unknown");
      },
      () => "original-key",
    ),
  );
  assert.equal(registry.forContext("northstar:owner:production").size, 0);
  assert.equal(registry.forContext("northstar:auditor:staging").size, 0);
  assert.equal(registry.forContext("another:owner:staging").size, 0);
  let sent = "";
  await submitIntent(
    registry.forContext("northstar:owner:staging"),
    "fingerprint",
    async (key) => {
      sent = key;
      return { id: "acknowledged", status: "queued" };
    },
  );
  assert.equal(sent, "original-key");
  assert.equal(original.size, 0);
});
