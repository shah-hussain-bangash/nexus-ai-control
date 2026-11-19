import { test } from "node:test";
import assert from "node:assert/strict";
import {
  recoveryScope,
  readRecovery,
  writeRecovery,
  clearRecovery,
  prepareRecovery,
  requestFingerprint,
  legacyRecoveryScope,
  acknowledgeRecovery,
} from "../src/inferenceRecovery.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { recoveryPanelKey } from "../src/recoveryContext.ts";

function memory() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}
const record = {
  key: "original-request-123456",
  fingerprint: "a".repeat(64),
  created: 1000,
};
const kinds = [
  "run",
  "document",
  "document-update",
  "retrieval-check",
  "intake",
  "hybrid-search",
] as const;

test("runtime recovery never crosses workspace, user, environment or request kind", () => {
  const store = memory();
  for (const kind of kinds) {
    const scope = liveIntentScope(kind, "org", "user", "staging");
    writeRecovery(store, scope, record);
    assert.deepEqual(readRecovery(store, scope), record);
    for (const other of [
      liveIntentScope(kind, "other", "user", "staging"),
      liveIntentScope(kind, "org", "other", "staging"),
      liveIntentScope(kind, "org", "user", "production"),
    ])
      assert.equal(readRecovery(store, other), null);
  }
  assert.equal(
    new Set(
      kinds.map((kind) => liveIntentScope(kind, "org", "user", "staging")),
    ).size,
    kinds.length,
  );
  writeRecovery(store, recoveryScope("org", "user", "staging"), record);
  assert.equal(
    readRecovery(store, recoveryScope("org", "user", "production")),
    null,
  );
  assert.notEqual(
    recoveryScope("a:b", "c", "staging"),
    recoveryScope("a", "b:c", "staging"),
  );
});

test("legacy staging metadata stays recoverable without copying prompts or changing its key", () => {
  for (const scope of [
    recoveryScope("org", "user", "staging"),
    ...kinds.map((kind) => liveIntentScope(kind, "org", "user", "staging")),
    liveIntentScope("document-update", "org", "user", "staging") +
      ":document-123",
  ]) {
    const store = memory();
    const legacy = legacyRecoveryScope(scope)!;
    assert.ok(legacy);
    store.setItem(
      legacy,
      JSON.stringify({
        ...record,
        query: "Never copied",
        credential: "Never copied",
      }),
    );
    assert.deepEqual(readRecovery(store, scope), record);
    assert.equal(store.getItem(scope), null);
    const prepared = prepareRecovery(
      store,
      scope,
      record.fingerprint,
      null,
      () => {
        throw new Error("Must not replace a legacy key");
      },
    );
    assert.deepEqual(prepared, record);
    assert.doesNotMatch(store.getItem(scope)!, /query|credential|Never copied/);
    assert.ok(
      store.getItem(legacy),
      "Legacy receipt survives until acknowledgement",
    );
    clearRecovery(store, scope, record);
    assert.equal(store.getItem(scope), null);
    assert.equal(store.getItem(legacy), null);
  }
});

test("legacy staging receipts cannot be adopted into production or another resource", () => {
  const store = memory();
  store.setItem("nexus.inference.recovery.v1:org:user", JSON.stringify(record));
  assert.equal(
    readRecovery(store, recoveryScope("org", "user", "production")),
    null,
  );
  store.setItem(
    "nexus.live.document-update.v1:org:user:doc-1",
    JSON.stringify(record),
  );
  assert.deepEqual(
    readRecovery(
      store,
      liveIntentScope("document-update", "org", "user", "staging") + ":doc-1",
    ),
    record,
  );
  assert.equal(
    readRecovery(
      store,
      liveIntentScope("document-update", "org", "user", "staging") + ":doc-2",
    ),
    null,
  );
});

test("acknowledging v2 cannot delete a different pending v1 intent", () => {
  const store = memory(),
    scope = recoveryScope("org", "user", "staging"),
    legacy = legacyRecoveryScope(scope)!;
  store.setItem(legacy, JSON.stringify(record));
  const newer = {
    ...record,
    key: "another-request-123456",
    fingerprint: "b".repeat(64),
  };
  writeRecovery(store, scope, newer);
  assert.deepEqual(readRecovery(store, scope), newer);
  clearRecovery(store, scope, newer);
  assert.deepEqual(readRecovery(store, scope), record);
  clearRecovery(store, scope, newer);
  assert.deepEqual(
    readRecovery(store, scope),
    record,
    "Repeating old cleanup must not erase the remaining legacy receipt",
  );
  clearRecovery(store, scope, record);
  assert.equal(readRecovery(store, scope), null);
});

test("late cleanup and invalid recovery receipts preserve newer pending records", () => {
  const store = memory(),
    scope = recoveryScope("org", "user", "staging");
  const newer = {
    ...record,
    key: "newer-request-123456",
    fingerprint: "b".repeat(64),
  };
  writeRecovery(store, scope, newer);
  assert.throws(() => writeRecovery(store, scope, record), /Another request/);
  clearRecovery(store, scope, record);
  assert.deepEqual(readRecovery(store, scope), newer);
  for (const invalid of [
    {},
    { id: "receipt" },
    { id: 123, status: "queued" },
    { id: "receipt", status: {} },
  ])
    assert.throws(() => acknowledgeRecovery(store, scope, newer, invalid));
  assert.deepEqual(readRecovery(store, scope), newer);
  acknowledgeRecovery(store, scope, newer, {
    id: "original-result",
    status: "queued",
  });
  assert.equal(readRecovery(store, scope), null);
});

test("unknown and malformed acknowledgements retain the original key through a scope upgrade", async () => {
  for (const malformed of [false, true]) {
    const store = memory(),
      body = { synthetic: "original intent" },
      scope = liveIntentScope("run", "org", "user", "staging"),
      legacy = legacyRecoveryScope(scope)!;
    const original = { ...record, fingerprint: await requestFingerprint(body) };
    store.setItem(legacy, JSON.stringify(original));
    const keys: string[] = [];
    await assert.rejects(
      sendLiveIntent(store, scope, body, async (key) => {
        keys.push(key);
        if (malformed) return {} as any;
        throw new Error("Response lost after admission");
      }),
    );
    assert.deepEqual(readRecovery(store, scope), original);
    await sendLiveIntent(store, scope, body, async (key) => {
      keys.push(key);
      return { id: "same-original-run", status: "queued" };
    });
    assert.deepEqual(keys, [original.key, original.key]);
    assert.equal(readRecovery(store, scope), null);
    assert.equal(store.getItem(legacy), null);
  }
});

test("storage read/write failures block submission and preserve legacy recovery", async () => {
  const store = memory(),
    scope = liveIntentScope("intake", "org", "user", "staging"),
    legacy = legacyRecoveryScope(scope)!,
    body = { file: "metadata-only" };
  store.setItem(
    legacy,
    JSON.stringify({ ...record, fingerprint: await requestFingerprint(body) }),
  );
  let sent = false;
  for (const broken of [
    {
      ...store,
      getItem: () => {
        throw new Error("Unavailable");
      },
    },
    {
      ...store,
      setItem: () => {
        throw new Error("Quota");
      },
    },
  ])
    await assert.rejects(
      sendLiveIntent(broken, scope, body, async () => {
        sent = true;
        return { id: "unexpected", status: "queued" };
      }),
    );
  assert.equal(sent, false);
  assert.ok(store.getItem(legacy));
  assert.equal(store.getItem(scope), null);
});

test("workspace provisioning remains shared while managed runtime panels get distinct keys", () => {
  assert.equal(
    liveIntentScope("member", "org", "user", "staging"),
    "nexus.live.member.v1:org:user",
  );
  assert.equal(
    liveIntentScope("member", "org", "user", "production"),
    liveIntentScope("member", "org", "user", "staging"),
  );
  const me = { user: { id: "user", org_id: "org" }, environment: "staging" };
  assert.notEqual(
    recoveryPanelKey(me),
    recoveryPanelKey({ ...me, environment: "production" }),
  );
  assert.notEqual(
    recoveryPanelKey(me),
    recoveryPanelKey({ ...me, user: { ...me.user, id: "other" } }),
  );
  for (const invalid of [undefined, "", "../staging", "Staging"])
    assert.throws(() => recoveryPanelKey({ ...me, environment: invalid }));
  assert.throws(() => recoveryScope("", "user", "staging"));
});
