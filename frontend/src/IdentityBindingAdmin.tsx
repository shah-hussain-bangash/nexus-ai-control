import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { identityBindingRequest } from "./identityBindingRequest";
type Row = Record<string, any>;
export function IdentityBindingAdmin({
  me,
  onChanged,
}: {
  me: Row;
  onChanged: () => Promise<void>;
}) {
  const [data, setData] = useState<Row | null>(null),
    [selected, setSelected] = useState(""),
    [command, setCommand] = useState<"bind" | "clear">("bind");
  const [subject, setSubject] = useState(""),
    [note, setNote] = useState(""),
    [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const owner = me.permissions?.includes("members"),
    scope = liveIntentScope(
      "member-identity",
      me.user.org_id,
      me.user.id,
      me.environment,
    );
  async function refresh() {
    setData(await api("/v1/member-admin"));
    setReviewed(false);
  }
  useEffect(() => {
    if (owner) void refresh().catch((e) => setMessage(e.message));
  }, [owner]);
  async function act(task?: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const row = task ? await task() : null;
      await refresh();
      await onChanged();
      if (row) {
        setSubject("");
        setSelected("");
        setNote("");
      }
      setMessage(
        row
          ? `Receipt ${row.id}: identity change recorded for ${row.member_id}; ${row.sessions_revoked} sessions revoked at that change. The target was deactivated. Current account state is shown in the refreshed directory; recovering an old receipt does not change it.`
          : "Current directory reloaded; no identity changed.",
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!owner) return null;
  const target = data?.items.find((row: Row) => row.id === selected);
  return (
    <details className="panel runtime-card">
      <summary>Reviewed SSO identity bindings</summary>
      <h3>Workspace-wide identity change</h3>
      <p>
        Binding or clearing an identity deactivates the member and revokes all
        of their sessions across environments. Review their access separately
        before using Activate in the directory. Owner and self changes remain
        protected.
      </p>
      <p>
        This records an owner-reviewed subject; it does not contact the identity
        provider or verify MFA. Pilot SSO requires an exact prebound subject.
        Local mode retains its existing first-login behavior for unbound active
        users.
      </p>
      {message && <p role="status">{message}</p>}
      <button className="btn" disabled={busy} onClick={() => void act()}>
        Reload directory and issuer
      </button>
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void act(async () => {
            const pending = readRecovery(sessionStorage, scope);
            if (!pending)
              throw Error(
                "No unacknowledged identity change for this account and workspace.",
              );
            const row = await api("/v1/member-identity/recover", "POST", {
              key: pending.key,
            });
            acknowledgeRecovery(sessionStorage, scope, pending, row);
            return row;
          })
        }
      >
        Recover identity-change receipt
      </button>
      {data && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!target) return;
            void act(() => {
              const body = identityBindingRequest(
                target,
                me.user.id,
                data.oidc_issuer,
                command,
                subject,
                note,
                reviewed,
              );
              return sendLiveIntent(
                sessionStorage,
                scope,
                { member_id: target.id, ...body },
                (key) =>
                  api(
                    `/v1/member-identity/${encodeURIComponent(target.id)}`,
                    "POST",
                    body,
                    key,
                  ),
              );
            });
          }}
        >
          <fieldset disabled={busy}>
            <legend>Review existing account</legend>
            <p>
              Configured issuer: {data.oidc_issuer || "Not configured"} ·
              applies to the whole workspace
            </p>
            <label className="field">
              <span>Target non-owner member</span>
              <select
                required
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setSubject("");
                  setReviewed(false);
                }}
              >
                <option value="">Choose a member</option>
                {data.items
                  .filter(
                    (row: Row) => row.role !== "owner" && row.id !== me.user.id,
                  )
                  .map((row: Row) => (
                    <option key={row.id} value={row.id}>
                      {row.name} · {row.email} ·{" "}
                      {row.active ? "active" : "inactive"}
                    </option>
                  ))}
              </select>
            </label>
            {target && (
              <p>
                {target.oidc_bound
                  ? "An identity is already bound; binding replaces it."
                  : "No identity is bound."}{" "}
                Current sessions: {target.active_sessions}. Role and environment
                assignments will be preserved.
              </p>
            )}
            <label className="field">
              <span>Change</span>
              <select
                value={command}
                onChange={(e) => {
                  setCommand(e.target.value as "bind" | "clear");
                  setSubject("");
                  setReviewed(false);
                }}
              >
                <option value="bind">Bind or replace trusted subject</option>
                <option value="clear">Clear identity binding</option>
              </select>
            </label>
            {command === "bind" && (
              <label className="field">
                <span>
                  Exact subject from your trusted identity administrator (not an
                  email or token)
                </span>
                <input
                  required
                  maxLength={200}
                  autoComplete="off"
                  value={subject}
                  onChange={(e) => {
                    setSubject(e.target.value);
                    setReviewed(false);
                  }}
                />
              </label>
            )}
            <label className="field">
              <span>Reason (10–500 visible characters, no secrets)</span>
              <input
                required
                minLength={10}
                maxLength={500}
                value={note}
                onChange={(e) => {
                  setNote(e.target.value);
                  setReviewed(false);
                }}
              />
            </label>
            <label>
              <input
                type="checkbox"
                required
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
              />
              I reviewed the target and identity. This deactivates the member
              and signs out all of their sessions.
            </label>
            <button
              className="btn btn-primary"
              disabled={
                !target ||
                !reviewed ||
                note.trim().length < 10 ||
                (command === "bind" && (!data.oidc_issuer || !subject))
              }
            >
              Record reviewed identity change and deactivate
            </button>
          </fieldset>
        </form>
      )}
    </details>
  );
}
