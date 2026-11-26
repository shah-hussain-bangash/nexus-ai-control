import test from "node:test";
import assert from "node:assert/strict";
import { RunListRequests } from "../src/runListRequests.ts";

test("slow response survives repeated poll ticks and can populate the list", async () => {
  const requests = new RunListRequests();
  let finish: (rows: string[]) => void = () => {};
  const response = new Promise<string[]>((resolve) => {
    finish = resolve;
  });
  const ticket = requests.start()!;
  let visible: string[] = [];
  const load = response.then((rows) => {
    if (requests.accepts(ticket)) visible = rows;
    requests.finish(ticket);
  });
  // Multiple timer ticks occur while the original response is still pending.
  for (let tick = 0; tick < 4; tick++)
    assert.equal(requests.start(false), null);
  finish(["original response"]);
  await load;
  assert.deepEqual(visible, ["original response"]);
  assert.notEqual(requests.start(false), null);
});

test("changing view rejects an old response without releasing a newer request", () => {
  const requests = new RunListRequests(),
    old = requests.start()!;
  requests.invalidate();
  const next = requests.start()!;
  assert.equal(requests.accepts(old), false);
  assert.equal(requests.finish(old), false);
  assert.equal(requests.start(false), null);
  assert.equal(requests.accepts(next), true);
  assert.equal(requests.finish(next), true);
});

test("explicit refresh replaces pending work and errors can release the next poll", () => {
  const requests = new RunListRequests(),
    first = requests.start()!;
  const refresh = requests.start(true)!;
  assert.equal(requests.accepts(first), false);
  assert.equal(requests.finish(first), false);
  assert.equal(requests.finish(refresh), true);
  assert.notEqual(requests.start(false), null);
});
