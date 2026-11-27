import { test } from "node:test";
import assert from "node:assert/strict";
import {
  procurementRun,
  intakeMetadata,
  queuedFileMetadata,
  runControls,
} from "../src/liveRequests.ts";
import { sendLiveIntent, liveIntentScope } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";
function storage() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) || null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
  };
}
test("procurement requests preserve the independent gate and governed payload boundaries", () => {
  const r = procurementRun(
    "agent",
    "read-tool",
    "write-tool",
    "procurement",
    "SUP-DEMO-104",
    "12500.00",
    "Replacement equipment",
  );
  assert.deepEqual(
    r.steps.map((s) => s.kind),
    ["checkpoint", "governed_action", "approval", "governed_action", "output"],
  );
  assert.equal(r.steps[3].request.arguments.amount, "12500.00");
  assert.equal(r.steps[3].request.action, "purchase:create");
  assert.equal(
    procurementRun("a", "t", "", "lookup", "SUP-DEMO-104", "", "").steps.length,
    3,
  );
  assert.throws(() =>
    procurementRun(
      "a",
      "r",
      "w",
      "procurement",
      "SUP-DEMO-104",
      "12500",
      "Purpose",
    ),
  );
});
test("real document intake rejects PDF, path names and oversized files", () => {
  assert.equal(
    intakeMetadata({ name: "policy.txt", size: 10 }).filename,
    "policy.txt",
  );
  for (const f of [
    { name: "policy.pdf", size: 10 },
    { name: "../policy.txt", size: 10 },
    { name: "policy.txt", size: 32769 },
  ])
    assert.throws(() => intakeMetadata(f));
});
test("uncertain and terminal runs expose no blind retry", () => {
  assert.deepEqual(runControls({ status: "outcome_unknown" }), ["cancel"]);
  assert.deepEqual(runControls({ status: "succeeded" }), []);
  assert.deepEqual(runControls({ status: "failed", can_retry: true }), [
    "retry",
  ]);
  assert.deepEqual(runControls({ status: "paused" }), ["resume", "cancel"]);
});
test("reload recovery retains only a scoped key and fingerprint and reuses that key", async () => {
  const s = storage(),
    scope = liveIntentScope("run", "org", "user", "staging");
  const body = { agent: "a", purpose: "Private request text" };
  await assert.rejects(
    sendLiveIntent(
      s,
      scope,
      body,
      async () => {
        throw Error("connection lost");
      },
      () => "intent-key-0000001",
    ),
  );
  const prior = readRecovery(s, scope)!;
  assert.equal(prior.key, "intent-key-0000001");
  assert.ok(!s.getItem(scope)?.includes("Private request text"));
  let used = "";
  await sendLiveIntent(s, scope, body, async (key) => {
    used = key;
    return { id: "run", status: "queued" };
  });
  assert.equal(used, prior.key);
  assert.equal(readRecovery(s, scope), null);
});
test("a changed uncertain intent is blocked and definite input rejection clears it", async () => {
  const s = storage(),
    scope = liveIntentScope("document", "org", "user", "staging");
  await assert.rejects(
    sendLiveIntent(
      s,
      scope,
      { a: 1 },
      async () => {
        throw Error("timeout");
      },
      () => "intent-key-0000001",
    ),
  );
  await assert.rejects(
    sendLiveIntent(s, scope, { a: 2 }, async () => ({
      id: "wrong",
      status: "indexed",
    })),
  );
  await assert.rejects(
    sendLiveIntent(s, scope, { a: 1 }, async () => {
      throw Object.assign(Error("invalid input"), { status: 422 });
    }),
  );
  assert.equal(readRecovery(s, scope), null);
  assert.notEqual(scope, liveIntentScope("run", "org", "user", "staging"));
});

test("document updates and retrieval checks have isolated recovery scopes", () => {
  const scopes = ["run", "document", "document-update", "retrieval-check"].map(
    (kind) =>
      liveIntentScope(
        kind as "run" | "document" | "document-update" | "retrieval-check",
        "org",
        "user",
        "staging",
      ),
  );
  assert.equal(new Set(scopes).size, 4);
  assert.notEqual(scopes[2] + ":source-a", scopes[2] + ":source-b");
});
test("a stale revision rejection clears only the rejected update intent", async () => {
  const s = storage(),
    scope = liveIntentScope("document-update", "org", "user", "staging");
  await assert.rejects(
    sendLiveIntent(s, scope, { expected_version: 1 }, async () => {
      throw Object.assign(Error("source changed"), {
        status: 409,
        code: "STALE_VERSION",
      });
    }),
  );
  assert.equal(readRecovery(s, scope), null);
  await sendLiveIntent(s, scope, { expected_version: 2 }, async () => ({
    id: "source",
    status: "indexed",
  }));
});

test("customer supplier references are bounded and never become URL paths", () => {
  const r = procurementRun(
    "agent",
    "supplier-tool",
    "purchase-tool",
    "lookup",
    "ERP:VENDOR-105",
    "12500.00",
    "Customer contract test",
  );
  assert.equal(r.steps[1].request.arguments.supplier_id, "ERP:VENDOR-105");
  assert.throws(() =>
    procurementRun(
      "agent",
      "supplier-tool",
      "purchase-tool",
      "lookup",
      "../unsafe",
      "12500.00",
      "Customer contract test",
    ),
  );
});

test("queued binary intake accepts only bounded plain supported files", () => {
  for (const name of [
    "source.pdf",
    "source.docx",
    "scan.png",
    "photo.JPG",
    "photo.jpeg",
  ])
    assert.equal(queuedFileMetadata({ name, size: 1048576 }).filename, name);
  for (const f of [
    { name: "../source.pdf", size: 1 },
    { name: "source.exe", size: 100 },
    { name: "source.pdf", size: 0 },
    { name: "source.pdf", size: 1048577 },
    { name: "a".repeat(120) + ".pdf", size: 1 },
  ])
    assert.throws(() => queuedFileMetadata(f));
});
test("queued intake recovery is isolated by request kind, organization and author", () => {
  const scopes = [
    liveIntentScope("intake", "org", "owner", "staging"),
    liveIntentScope("document", "org", "owner", "staging"),
    liveIntentScope("intake", "other", "owner", "staging"),
    liveIntentScope("intake", "org", "reviewer", "staging"),
  ];
  assert.equal(new Set(scopes).size, 4);
});

test("Search and member recovery stay scoped; definitive pre-admission conflicts allow revised intent", async () => {
  const s = storage();
  for (const kind of [
    "hybrid-search",
    "member",
    "neural-index-build",
    "indexed-search",
  ] as const) {
    const scope = liveIntentScope(kind, "org", "owner", "staging");
    assert.notEqual(scope, liveIntentScope(kind, "other", "owner", "staging"));
    assert.notEqual(scope, liveIntentScope(kind, "org", "reviewer", "staging"));
    await assert.rejects(
      sendLiveIntent(s, scope, { revision: 1 }, async () => {
        throw Object.assign(new Error("Changed source"), {
          status: 409,
          code: kind === "member" ? "ACCOUNT_UNAVAILABLE" : "SOURCE_CHANGED",
        });
      }),
    );
    const result = await sendLiveIntent(
      s,
      scope,
      { revision: 2 },
      async () => ({ id: "accepted", status: "completed" }),
    );
    assert.equal(result.id, "accepted");
  }
});

test("stored-index preflight conflicts retire only their own recovery key", async () => {
  const s = storage();
  const build = liveIntentScope(
    "neural-index-build",
    "org",
    "owner",
    "staging",
  );
  const query = liveIntentScope("indexed-search", "org", "owner", "staging");
  await assert.rejects(
    sendLiveIntent(s, build, { name: "index" }, async () => {
      throw Error("Lost reply");
    }),
  );
  for (const code of [
    "INDEX_INVALIDATED",
    "INDEX_SOURCE_CHANGED",
    "INDEX_MODEL_CHANGED",
    "INDEX_INTEGRITY_FAILED",
  ]) {
    await assert.rejects(
      sendLiveIntent(s, query, { index_id: "old" }, async () => {
        throw Object.assign(Error(code), { status: 409, code });
      }),
    );
    assert.equal(readRecovery(s, query), null);
    assert.ok(readRecovery(s, build));
  }
  for (const scope of [
    liveIntentScope("indexed-search", "org", "owner", "production"),
    liveIntentScope("indexed-search", "org", "another", "staging"),
    liveIntentScope("indexed-search", "other", "owner", "staging"),
  ])
    assert.equal(readRecovery(s, scope), null);
});
