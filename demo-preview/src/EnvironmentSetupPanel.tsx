import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { Modal } from "./RuntimeDialog";
import {
  canControlEnvironment,
  environmentControlPayload,
  environmentCreatePayload,
  environmentStateLabel,
} from "./environmentSetup";
import type { EnvironmentCommand, EnvironmentRecord } from "./environmentSetup";
import "./live.css";
import "./enterpriseRuntime.css";
import "./environmentSetup.css";

type Inventory = {
  workspace: { id: string; name: string };
  items: EnvironmentRecord[];
  current_environment: string;
  read_only?: boolean;
};
type Member = { id: string; name: string; role: string; active: boolean };
type Editor =
  | { kind: "create" }
  | { kind: "control"; row: EnvironmentRecord; command: EnvironmentCommand };
const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "The request could not be completed.";

export function EnvironmentSetup({
  me,
}: {
  me: { user: { id: string; org_id: string; role: string } };
}) {
  const owner = me.user.role === "owner";
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState("");
  const [selected, setSelected] = useState<EnvironmentRecord | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [memberError, setMemberError] = useState("");
  useEffect(() => {
    if (!owner) return;
    let active = true;
    api<Inventory>("/v1/workspace-environments")
      .then((data) => {
        if (active) {
          setInventory(data);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (active) {
          setError(message(e));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [owner, me.user.id, me.user.org_id]);
  useEffect(() => {
    if (!selected || !owner) return;
    let active = true;
    setMembers(null);
    setMemberError("");
    api<{ items: Member[] }>(
      `/v1/workspace-environments/${encodeURIComponent(selected.key)}/assignments`,
    )
      .then((data) => {
        if (active) setMembers(data.items);
      })
      .catch((e) => {
        if (active) setMemberError(message(e));
      });
    return () => {
      active = false;
    };
  }, [selected, owner]);
  if (!owner) return null;

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setInventory(await api<Inventory>("/v1/workspace-environments"));
      setNeedsRefresh(false);
    } catch (e) {
      setError(message(e));
      throw e;
    } finally {
      setLoading(false);
    }
  }
  function openEditor(value: Editor) {
    setEditor(value);
    setNote("");
    setFormError("");
    setNotice("");
    if (value.kind === "create") {
      setKey("");
      setName("");
    }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (
      !editor ||
      !inventory ||
      busy ||
      loading ||
      needsRefresh ||
      inventory.read_only
    )
      return;
    let payload;
    try {
      payload =
        editor.kind === "create"
          ? environmentCreatePayload(key, name, note)
          : environmentControlPayload(
              editor.row,
              inventory.current_environment,
              editor.command,
              note,
            );
      if (
        editor.kind === "create" &&
        inventory.items.some((row) => row.key === key.trim())
      )
        throw new Error("This key already exists. Choose another key.");
    } catch (e) {
      setFormError(message(e));
      return;
    }
    setBusy(true);
    setFormError("");
    setError("");
    try {
      await api(
        editor.kind === "create"
          ? "/v1/workspace-environments"
          : `/v1/workspace-environments/${encodeURIComponent(editor.row.key)}/control`,
        "POST",
        payload,
      );
    } catch (e) {
      if (
        e instanceof ApiError &&
        ["STALE_VERSION", "ENVIRONMENT_STATE"].includes(e.code)
      ) {
        setEditor(null);
        setNeedsRefresh(true);
        setError(
          "This environment changed. Refresh the list before trying again.",
        );
      } else if (!(e instanceof ApiError) || e.status >= 500) {
        setNeedsRefresh(true);
        setFormError(
          "The result could not be confirmed. Close this dialog and refresh the list before trying again.",
        );
      } else setFormError(message(e));
      setBusy(false);
      return;
    }
    setEditor(null);
    setNotice(
      editor.kind === "create"
        ? "Environment prepared. Runtime switching remains unavailable."
        : editor.command === "archive"
          ? "Environment archived."
          : "Environment restored to Preparing.",
    );
    try {
      await refresh();
    } catch {
      setNeedsRefresh(true);
      setError(
        "Your change was saved, but the list could not be refreshed. Refresh before making another change.",
      );
    } finally {
      setBusy(false);
    }
  }
  const locked =
    busy || loading || needsRefresh || !inventory || inventory.read_only;
  return (
    <section
      className="enterprise-runtime environment-setup"
      aria-labelledby="environment-heading"
    >
      <div className="panel runtime-card">
        <div className="environment-heading">
          <div>
            <h2 id="environment-heading">Environment setup</h2>
            <p>
              Prepare environments for{" "}
              {inventory?.workspace.name || "your workspace"}.
            </p>
          </div>
          <div className="live-actions">
            <button
              className="btn"
              disabled={loading || busy}
              onClick={() => void refresh().catch(() => {})}
            >
              Refresh environments
            </button>
            <button
              className="btn btn-primary"
              disabled={!!locked || (inventory?.items.length || 0) >= 20}
              onClick={() => openEditor({ kind: "create" })}
            >
              Prepare environment
            </button>
          </div>
        </div>
        <p className="environment-boundary">
          Current environment:{" "}
          <strong>{inventory?.current_environment || "staging"}</strong>. New
          environments stay in Preparing. Switching, promotion and assignment
          editing are not available yet.
        </p>
        {inventory?.read_only && (
          <p>
            This preview is read-only. Use the full local app to prepare
            environments.
          </p>
        )}
        {error && (
          <p className="ops-alert" role="alert">
            {error}
          </p>
        )}
        {notice && <p role="status">{notice}</p>}
        {loading && <p role="status">Loading environments…</p>}
        {!loading && inventory?.items.length === 0 && (
          <p>No environments are registered.</p>
        )}
        {(inventory?.items.length || 0) >= 20 && (
          <p>
            The workspace has reached its limit of 20 environment records,
            including archived environments.
          </p>
        )}
        <div className="environment-grid">
          {inventory?.items.map((row) => (
            <article className="environment-card" key={row.key}>
              <div className="environment-heading">
                <h3>{row.name}</h3>
                <span className="environment-status">
                  {environmentStateLabel(row, inventory.current_environment)}
                </span>
              </div>
              <p>
                <code>{row.key}</code>
              </p>
              <p>
                {row.key === inventory.current_environment
                  ? "Your current runtime environment is protected."
                  : row.state === "archived"
                    ? "Archived setup record. Restore it to continue preparation."
                    : "Preparation only. No runtime access is enabled."}
              </p>
              <div className="live-actions">
                <button
                  className="btn"
                  disabled={busy || loading}
                  aria-label={`View assignments for ${row.name}`}
                  onClick={() => setSelected(row)}
                >
                  View assignments
                </button>
                {(["archive", "restore"] as const)
                  .filter((command) =>
                    canControlEnvironment(
                      row,
                      inventory.current_environment,
                      command,
                    ),
                  )
                  .map((command) => (
                    <button
                      className="btn"
                      key={command}
                      disabled={!!locked}
                      aria-label={`${command === "archive" ? "Archive" : "Restore"} ${row.name}`}
                      onClick={() =>
                        openEditor({ kind: "control", row, command })
                      }
                    >
                      {command === "archive" ? "Archive" : "Restore"}
                    </button>
                  ))}
              </div>
            </article>
          ))}
        </div>
      </div>
      {editor && (
        <Modal
          title={
            editor.kind === "create"
              ? "Prepare environment"
              : `${editor.command === "archive" ? "Archive" : "Restore"} ${editor.row.name}`
          }
          onClose={() => {
            if (!busy) setEditor(null);
          }}
        >
          <form className="runtime-form" onSubmit={save}>
            <p>
              {editor.kind === "create"
                ? "This creates a Preparing record. It does not enable runtime access."
                : editor.command === "archive"
                  ? "Archive this preparation record? Environments containing existing records cannot be archived."
                  : "Restore this record to Preparing? Runtime access will remain unavailable."}
            </p>
            {editor.kind === "create" && (
              <>
                <label className="field">
                  <span>Environment name</span>
                  <input
                    autoFocus
                    required
                    minLength={2}
                    maxLength={80}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={busy}
                  />
                </label>
                <label className="field">
                  <span>Environment key</span>
                  <input
                    required
                    minLength={2}
                    maxLength={32}
                    pattern="[a-z][a-z0-9-]{1,31}"
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    disabled={busy}
                    aria-describedby="environment-key-help"
                  />
                </label>
                <p id="environment-key-help">
                  2–32 lowercase letters, numbers or hyphens; start with a
                  letter. The key cannot be changed later.
                </p>
              </>
            )}
            <label className="field">
              <span>Reason for this change</span>
              <input
                required
                minLength={5}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                disabled={busy}
              />
            </label>
            {formError && (
              <p className="ops-alert" role="alert">
                {formError}
              </p>
            )}
            <div className="live-actions">
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => setEditor(null)}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                disabled={busy || needsRefresh}
              >
                {busy
                  ? "Saving…"
                  : editor.kind === "create"
                    ? "Prepare environment"
                    : editor.command === "archive"
                      ? "Confirm archive"
                      : "Restore to Preparing"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal
          title={`Assignments · ${selected.name}`}
          onClose={() => setSelected(null)}
        >
          <div className="runtime-form">
            <p>
              Assignments are read-only. Assignment editing and runtime
              switching are not available yet.
            </p>
            {memberError ? (
              <p className="ops-alert" role="alert">
                {memberError}
              </p>
            ) : members === null ? (
              <p role="status">Loading assignments…</p>
            ) : members.length === 0 ? (
              <p>No members are assigned to this environment.</p>
            ) : (
              <ul className="environment-members">
                {members.map((member) => (
                  <li key={member.id}>
                    <strong>{member.name}</strong>
                    <span>
                      {member.role} · {member.active ? "Active" : "Inactive"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <button className="btn" onClick={() => setSelected(null)}>
              Close assignments
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}
