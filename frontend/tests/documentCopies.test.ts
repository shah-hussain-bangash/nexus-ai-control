import test from "node:test";
import assert from "node:assert/strict";
import { checkedCopies } from "../src/documentCopies.ts";
import type { SessionContext } from "../src/sessionContext.ts";
const context: SessionContext = {
  workspace_id: "northstar",
  user_id: "reader",
  environment: "staging",
  revision: 1,
  binding_id: "binding",
};
function reply() {
  return {
    scope: {
      workspace_id: "northstar",
      account_id: "reader",
      environment: "staging",
    },
    source: { id: "source", version: 2 },
    offset: 0,
    visible_count: 1,
    next_offset: null,
    items: [
      {
        id: "copy",
        title: "Visible copy",
        filename: "copy.txt",
        language: "English",
        version: 1,
        updated: 1234,
      },
    ],
  };
}
test("copy preview accepts the pinned authorized source and empty visible results", () => {
  assert.equal(
    checkedCopies(reply(), context, "source", 2, 0).items[0].id,
    "copy",
  );
  assert.equal(
    checkedCopies(
      { ...reply(), visible_count: 0, items: [] },
      context,
      "source",
      2,
      0,
    ).visible_count,
    0,
  );
});
test("copy preview rejects other account, workspace, environment and source versions", () => {
  for (const change of [
    { user_id: "other" },
    { workspace_id: "other" },
    { environment: "production" },
  ])
    assert.throws(() =>
      checkedCopies(reply(), { ...context, ...change }, "source", 2, 0),
    );
  assert.throws(() => checkedCopies(reply(), null, "source", 2, 0));
  assert.throws(() => checkedCopies(reply(), context, "source", 3, 0));
  assert.throws(() => checkedCopies(reply(), context, "other", 2, 0));
});
test("copy preview rejects mismatched pages and repeated source records", () => {
  assert.throws(() => checkedCopies(reply(), context, "source", 2, 20));
  assert.throws(() =>
    checkedCopies({ ...reply(), visible_count: 21 }, context, "source", 2, 0),
  );
  assert.throws(() =>
    checkedCopies(
      { ...reply(), items: [{ ...reply().items[0], id: "source" }] },
      context,
      "source",
      2,
      0,
    ),
  );
  assert.throws(() =>
    checkedCopies(
      {
        ...reply(),
        visible_count: 2,
        items: [reply().items[0], reply().items[0]],
      },
      context,
      "source",
      2,
      0,
    ),
  );
});
