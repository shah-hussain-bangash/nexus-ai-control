import test from "node:test";
import assert from "node:assert/strict";
import { identityBindingRequest } from "../src/identityBindingRequest.ts";
import { liveIntentScope, sendLiveIntent } from "../src/liveIntent.ts";
import { readRecovery } from "../src/inferenceRecovery.ts";
const member = { id: "target", role: "engineer", revision: "a".repeat(64) };
const issuer = "https://identity.test.invalid/realm",
  note = "Reviewed synthetic identity change.";
test("identity review pins member revision and trusted issuer without activation", () => {
  const body = identityBindingRequest(
    member,
    "owner",
    issuer,
    "bind",
    "exact-subject",
    note,
    true,
  );
  assert.deepEqual(body, {
    expected_revision: member.revision,
    expected_issuer: issuer,
    command: "bind",
    subject: "exact-subject",
    note,
    reviewed: true,
  });
  assert.equal("activate" in body, false);
  assert.equal(
    identityBindingRequest(member, "owner", "", "clear", "", note, true)
      .subject,
    "",
  );
  assert.throws(() =>
    identityBindingRequest(
      member,
      "owner",
      issuer,
      "bind",
      " padded ",
      note,
      true,
    ),
  );
  assert.throws(() =>
    identityBindingRequest(member, "owner", "", "bind", "subject", note, true),
  );
  assert.throws(() =>
    identityBindingRequest(
      member,
      "owner",
      issuer,
      "clear",
      "subject",
      note,
      true,
    ),
  );
  assert.throws(() =>
    identityBindingRequest(
      member,
      "owner",
      issuer,
      "bind",
      "subject",
      note,
      false,
    ),
  );
  assert.throws(() =>
    identityBindingRequest(
      { ...member, role: "owner" },
      "other",
      issuer,
      "bind",
      "subject",
      note,
      true,
    ),
  );
  assert.throws(() =>
    identityBindingRequest(
      member,
      "target",
      issuer,
      "bind",
      "subject",
      note,
      true,
    ),
  );
});
test("identity recovery is workspace wide but separated by actor and operation kind", () => {
  const scope = liveIntentScope("member-identity", "org", "owner", "staging");
  assert.equal(
    scope,
    liveIntentScope("member-identity", "org", "owner", "development"),
  );
  assert.notEqual(
    scope,
    liveIntentScope("member-identity", "org", "other", "staging"),
  );
  assert.notEqual(scope, liveIntentScope("member", "org", "owner", "staging"));
});
test("lost binding response retains recovery key without subject or note", async () => {
  const values = new Map<string, string>(),
    storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
      removeItem: (key: string) => {
        values.delete(key);
      },
    };
  const scope = liveIntentScope("member-identity", "org", "owner", "staging");
  const body = identityBindingRequest(
    member,
    "owner",
    issuer,
    "bind",
    "private-subject",
    note,
    true,
  );
  await assert.rejects(
    sendLiveIntent(
      storage,
      scope,
      body,
      async () => {
        throw Error("lost response");
      },
      () => "identity-binding-intent-0001",
    ),
  );
  assert.equal(
    readRecovery(storage, scope)?.key,
    "identity-binding-intent-0001",
  );
  assert.ok(![...values.values()].join("").includes("private-subject"));
  assert.ok(![...values.values()].join("").includes(note));
});
