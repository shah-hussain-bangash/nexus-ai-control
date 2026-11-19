import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { Modal } from "./RuntimeDialog";
import type { EnvironmentRecord } from "./environmentSetup";
import {
  assignmentAcknowledged,
  assignmentPayload,
  canChangeAssignment,
} from "./environmentMembership";
import type {
  AssignmentCommand,
  AssignmentSnapshot,
  EnvironmentMember,
} from "./environmentMembership";

type Draft = {
  member: EnvironmentMember;
  command: AssignmentCommand;
  snapshot: AssignmentSnapshot;
};
const errorMessage = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "The request could not be completed.";
export function EnvironmentMembersDialog({
  environment,
  readOnly,
  onClose,
  onChanged,
}: {
  environment: EnvironmentRecord;
  readOnly: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [data, setData] = useState<AssignmentSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [chosen, setChosen] = useState("");
  const [note, setNote] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const path = `/v1/workspace-environments/${encodeURIComponent(environment.key)}/assignments`;
  useEffect(() => {
    let active = true;
    api<AssignmentSnapshot>(path)
      .then((result) => {
        if (active) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (active) {
          setError(errorMessage(e));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [path]);
  async function refresh() {
    setLoading(true);
    setError("");
    setDraft(null);
    setChosen("");
    try {
      setData(await api<AssignmentSnapshot>(path));
      setNeedsRefresh(false);
    } catch (e) {
      setError(errorMessage(e));
      setNeedsRefresh(true);
      throw e;
    } finally {
      setLoading(false);
    }
  }
  function confirm(member: EnvironmentMember, command: AssignmentCommand) {
    if (!data) return;
    setDraft({ member, command, snapshot: data });
    setNote("");
    setReviewed(false);
    setError("");
    setNotice("");
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft || busy || loading || needsRefresh || readOnly) return;
    let payload;
    try {
      payload = assignmentPayload(
        draft.snapshot,
        draft.member,
        draft.command,
        note,
        reviewed,
      );
    } catch (e) {
      setError(errorMessage(e));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api<unknown>(path + "/control", "POST", payload);
      if (!assignmentAcknowledged(result, payload, environment.key))
        throw new Error("Unconfirmed membership response.");
    } catch (e) {
      setNeedsRefresh(true);
      setError(
        e instanceof ApiError && e.status < 500
          ? errorMessage(e) + " Refresh before making another change."
          : "The result could not be confirmed. Refresh assignments and check the member before trying again.",
      );
      setBusy(false);
      return;
    }
    setDraft(null);
    setNotice(
      draft.command === "grant"
        ? `${draft.member.name} assigned. Existing sessions were signed out.`
        : `${draft.member.name} removed from this environment. Existing sessions were signed out.`,
    );
    onChanged();
    try {
      await refresh();
    } catch {
      setError(
        "The membership change was saved, but the list could not refresh. Refresh assignments or sign in again before continuing.",
      );
    } finally {
      setBusy(false);
    }
  }
  const locked =
    readOnly || busy || loading || needsRefresh || !data?.editing_enabled;
  const candidates =
    data?.candidates?.filter((member) =>
      canChangeAssignment(data, member, "grant"),
    ) || [];
  return (
    <Modal
      title={`Assignments · ${environment.name}`}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="runtime-form environment-members-dialog">
        <p>
          Membership changes sign the affected member out of all existing
          sessions. Roles and passwords are preserved. Removing staging access
          blocks their next sign-in and new work; it cannot undo work already
          dispatched.
        </p>
        <p>
          Preparing environments do not enable runtime access. Environment
          switching remains unavailable. Current owner access to staging is
          protected.
        </p>
        {(readOnly || (data && !data.editing_enabled)) && (
          <p>
            This assignment list is read-only.{" "}
            {readOnly
              ? "The synthetic preview cannot change access."
              : "This environment does not currently allow membership changes."}
          </p>
        )}
        {error && (
          <p className="ops-alert" role="alert">
            {error}
          </p>
        )}
        {notice && <p role="status">{notice}</p>}
        <div className="live-actions">
          <button
            className="btn"
            disabled={busy || loading}
            onClick={() => void refresh().catch(() => {})}
          >
            Refresh assignments
          </button>
          <button className="btn" disabled={busy} onClick={onClose}>
            Close assignments
          </button>
        </div>
        {loading ? (
          <p role="status">Loading assignments…</p>
        ) : (
          data && (
            <>
              {data.items.length === 0 ? (
                <p>No members are assigned to this environment.</p>
              ) : (
                <ul className="environment-members">
                  {data.items.map((member) => (
                    <li key={member.id}>
                      <strong>{member.name}</strong>
                      <span>{member.email || member.id}</span>
                      <span>
                        {member.role} · {member.active ? "Active" : "Inactive"}
                      </span>
                      {canChangeAssignment(data, member, "revoke") &&
                      !readOnly ? (
                        <button
                          className="btn"
                          disabled={locked || !!draft}
                          aria-label={`Remove ${member.name} (${member.email || member.id}) from ${environment.name}`}
                          onClick={() => confirm(member, "revoke")}
                        >
                          Remove assignment
                        </button>
                      ) : (
                        member.role === "owner" &&
                        environment.key === "staging" && (
                          <span>Owner access protected</span>
                        )
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {!readOnly && data.editing_enabled && !draft && (
                <div className="environment-assignment-add">
                  {candidates.length ? (
                    <>
                      <label className="field">
                        <span>Member to assign</span>
                        <select
                          value={chosen}
                          disabled={locked}
                          onChange={(e) => setChosen(e.target.value)}
                        >
                          <option value="">Choose a member</option>
                          {candidates.map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.name} · {member.email || member.id} ·{" "}
                              {member.role}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        className="btn"
                        disabled={locked || !chosen}
                        onClick={() => {
                          const member = candidates.find(
                            (row) => row.id === chosen,
                          );
                          if (member) confirm(member, "grant");
                        }}
                      >
                        Review assignment
                      </button>
                    </>
                  ) : (
                    <p>
                      No additional active members are eligible. Provision or
                      activate members in Workspace access first.
                    </p>
                  )}
                </div>
              )}
            </>
          )
        )}
        {draft && (
          <form
            className="environment-assignment-confirm"
            aria-labelledby="membership-change-heading"
            onSubmit={save}
          >
            <h3 id="membership-change-heading">
              {draft.command === "grant" ? "Assign" : "Remove"}{" "}
              {draft.member.name} · {environment.name}
            </h3>
            <p id="membership-change-summary">
              Account: {draft.member.email || draft.member.id}. Reviewed role:{" "}
              {draft.member.role}. This change will sign the member out of all
              existing sessions.{" "}
              {draft.command === "grant"
                ? "They must sign in again to use staging."
                : "Their other environment assignments are preserved."}
            </p>
            <label className="field">
              <span>Reason for membership change</span>
              <input
                autoFocus
                aria-describedby="membership-change-summary"
                required
                minLength={5}
                maxLength={500}
                value={note}
                onChange={(e) => {
                  setNote(e.target.value);
                  setReviewed(false);
                }}
                disabled={busy || needsRefresh}
              />
            </label>
            <label className="runtime-check">
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
                disabled={busy || needsRefresh}
              />
              I reviewed the member, environment and session sign-out effect.
            </label>
            <div className="live-actions">
              <button
                className="btn"
                type="button"
                disabled={busy}
                onClick={() => {
                  setDraft(null);
                  setError("");
                }}
              >
                Cancel change
              </button>
              <button
                className="btn btn-primary"
                disabled={busy || needsRefresh || !reviewed}
              >
                {busy
                  ? "Saving…"
                  : draft.command === "grant"
                    ? "Confirm assignment"
                    : "Confirm removal"}
              </button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}
