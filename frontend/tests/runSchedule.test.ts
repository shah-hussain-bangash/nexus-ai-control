import test from "node:test";
import assert from "node:assert/strict";
import { scheduleRun } from "../src/runSchedule.ts";

const current = new Date(2026, 10, 26, 12, 0).getTime();
test("immediate runs retain their exact request and scheduled local time becomes an absolute timestamp", () => {
  const body = { name: "run", steps: [{ kind: "checkpoint" }] };
  assert.equal(scheduleRun(body, "", current), body);
  const planned = scheduleRun(body, "2026-11-26T13:00", current);
  assert.equal(
    planned.start_at,
    new Date(2026, 10, 26, 13, 0).getTime() / 1000,
  );
  assert.equal("start_at" in body, false);
});
test("invalid dates, past and out-of-window starts are rejected", () => {
  for (const value of [
    "bad",
    "2026-02-30T13:00",
    "2026-11-26T12:00",
    "2026-11-25T13:00",
    "2026-12-04T13:00",
    "2026-11-26T13:00Z",
  ])
    assert.throws(() => scheduleRun({}, value, current));
  assert.equal(
    scheduleRun({}, "2026-12-03T12:00", current).start_at,
    new Date(2026, 11, 3, 12, 0).getTime() / 1000,
  );
});
