import { test } from "node:test";
import assert from "node:assert/strict";
import { submitIntent, submissionMessage } from "../src/runIntent.ts";

const action = {id: "12345678-test", status: "awaiting_approval"};

test("a new acknowledged intent gets a fresh key even with identical fields", async () => {
  const keys = new Map<string, string>(); const sent: string[] = []; let n = 0;
  const send = async (key: string) => {sent.push(key); return action;};
  for (let i=0; i<2; i++) await submitIntent(keys, "same body", send, () => "new-intent-" + ++n);
  assert.deepEqual(sent, ["new-intent-1", "new-intent-2"]);
  assert.equal(keys.size, 0);
});

test("an uncertain response retains its key for a retry, including after commit", async () => {
  const keys = new Map<string, string>(); const persisted = new Map(); let effects = 0;
  const send = async (key: string) => {
    if (!persisted.has(key)) {persisted.set(key, action); effects++; throw new Error("response lost after commit");}
    return persisted.get(key);
  };
  await assert.rejects(submitIntent(keys, "body", send, () => "original-key"));
  assert.equal(keys.get("body"), "original-key");
  assert.equal(await submitIntent(keys, "body", send, () => "must-not-be-used"), action);
  assert.equal(effects, 1);
  assert.equal(keys.size, 0);
});

test("different payloads do not share an uncertain request key", async () => {
  const keys = new Map<string, string>(); let n=0;
  const send = async () => {throw new Error("unavailable");};
  await assert.rejects(submitIntent(keys,"read",send,()=>"key-" + ++n));
  await assert.rejects(submitIntent(keys,"purchase",send,()=>"key-" + ++n));
  assert.notEqual(keys.get("read"),keys.get("purchase"));
});

test("an incomplete acknowledgement must not retire the recovery key", async () => {
  const keys = new Map<string, string>();
  await assert.rejects(submitIntent(keys,"body",async()=>({} as typeof action),()=>"recovery-key"), /incomplete/);
  assert.equal(keys.get("body"),"recovery-key");
});

test("success feedback identifies the actual reference and independent review state", () => {
  assert.match(submissionMessage(action), /ACT-12345678: Awaiting approval/);
  assert.match(submissionMessage(action), /independent reviewer/);
  assert.match(submissionMessage({id:action.id,status:"queued"}), /Queued for the worker/);
  assert.match(submissionMessage({id:action.id,status:"denied"}), /Denied by policy.*No execution was queued/);
  assert.match(submissionMessage({id:action.id,status:"expired"}), /expired/);
});
