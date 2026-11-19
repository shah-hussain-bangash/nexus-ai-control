import test from "node:test";
import assert from "node:assert/strict";
import {
  assignmentPayload,
  assignmentAcknowledged,
  canChangeAssignment,
} from "../src/environmentMembership.ts";
import type {
  AssignmentSnapshot,
  EnvironmentMember,
} from "../src/environmentMembership.ts";
const member: EnvironmentMember = {
  id: "member-1",
  name: "Test Member",
  role: "engineer",
  active: true,
  revision: "a".repeat(64),
};
const snapshot: AssignmentSnapshot = {
  items: [member],
  candidates: [],
  editing_enabled: true,
  environment: {
    key: "staging",
    name: "Staging",
    state: "active",
    version: 4,
    human_runtime_enabled: true,
  },
};

test("assignment confirmation pins both environment and member revisions", () => {
  const request = assignmentPayload(
    snapshot,
    member,
    "revoke",
    " Reviewed removal ",
    true,
  );
  assert.deepEqual(request, {
    user_id: member.id,
    command: "revoke",
    expected_version: 4,
    expected_member_revision: member.revision,
    note: "Reviewed removal",
    reviewed: true,
  });
  assert.throws(() =>
    assignmentPayload(snapshot, member, "revoke", "Reviewed removal", false),
  );
  assert.throws(() =>
    assignmentPayload(snapshot, member, "revoke", "\n ", true),
  );
  assert.equal(
    canChangeAssignment(
      snapshot,
      { ...member, revision: "b".repeat(64) },
      "revoke",
    ),
    false,
  );
  assert.equal(
    canChangeAssignment(snapshot, { ...member, id: "other-member" }, "revoke"),
    false,
  );
});

test("protected owners, archived environments and preview snapshots have no writes", () => {
  const owner = { ...member, role: "owner" };
  assert.equal(
    canChangeAssignment({ ...snapshot, items: [owner] }, owner, "revoke"),
    false,
  );
  assert.equal(
    canChangeAssignment(
      { ...snapshot, editing_enabled: false },
      member,
      "revoke",
    ),
    false,
  );
  assert.equal(
    canChangeAssignment(
      {
        ...snapshot,
        environment: { ...snapshot.environment!, state: "archived" },
      },
      member,
      "revoke",
    ),
    false,
  );
  assert.equal(
    canChangeAssignment(
      { items: [member], editing_enabled: false },
      member,
      "revoke",
    ),
    false,
  );
  assert.equal(
    canChangeAssignment(
      { ...snapshot, environment: { ...snapshot.environment!, version: 0 } },
      member,
      "revoke",
    ),
    false,
  );
});

test("only active reviewed candidates can be assigned, without activating a preparing environment", () => {
  const preparing = {
    ...snapshot,
    items: [],
    candidates: [member],
    environment: {
      ...snapshot.environment!,
      key: "production",
      state: "preparing",
      human_runtime_enabled: false,
    },
  };
  assert.equal(canChangeAssignment(preparing, member, "grant"), true);
  assert.equal(
    assignmentPayload(preparing, member, "grant", "Reviewed assignment", true)
      .command,
    "grant",
  );
  assert.equal(preparing.environment.human_runtime_enabled, false);
  assert.equal(
    canChangeAssignment(
      { ...preparing, candidates: [{ ...member, active: false }] },
      { ...member, active: false },
      "grant",
    ),
    false,
  );
  assert.equal(canChangeAssignment(snapshot, member, "grant"), false);
});

test("missing, mismatched or incomplete acknowledgements never count as a confirmed change", () => {
  const request = assignmentPayload(
    snapshot,
    member,
    "revoke",
    "Reviewed removal",
    true,
  );
  const receipt = {
    status: "removed",
    member_id: member.id,
    environment_key: "staging",
    version: 5,
    sessions_revoked: 2,
    switching_enabled: false,
  };
  assert.equal(assignmentAcknowledged(receipt, request, "staging"), true);
  for (const value of [
    null,
    {},
    { ...receipt, member_id: "other" },
    { ...receipt, environment_key: "production" },
    { ...receipt, version: 4 },
    { ...receipt, status: "assigned" },
    { ...receipt, sessions_revoked: -1 },
    { ...receipt, switching_enabled: true },
  ])
    assert.equal(assignmentAcknowledged(value, request, "staging"), false);
});
