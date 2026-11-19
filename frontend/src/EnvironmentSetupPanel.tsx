import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { Modal } from "./RuntimeDialog";
import { EnvironmentMembersDialog } from "./EnvironmentMembersDialog";
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
import { activationPayload, canActivateEnvironment } from "./environmentSwitch";
import { EnvironmentAssetCopy } from "./EnvironmentAssetCopyPanel";
import {
  canControlRuntime,
  runtimeControlPayload,
  type RuntimeCommand,
} from "./environmentRuntime";

type Inventory = {
  workspace: { id: string; name: string };
  items: EnvironmentRecord[];
  current_environment: string;
  read_only?: boolean;
  activation_enabled?: boolean;
  runtime_control_enabled?: boolean;
};
type Editor =
  | { kind: "create" }
  | { kind: "control"; row: EnvironmentRecord; command: EnvironmentCommand }
  | { kind: "activate"; row: EnvironmentRecord }
  | { kind: "runtime"; row: EnvironmentRecord; command: RuntimeCommand };
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
  const [activationReviewed, setActivationReviewed] = useState(false);
  const [confirmationKey, setConfirmationKey] = useState("");
  const [formError, setFormError] = useState("");
  const [selected, setSelected] = useState<EnvironmentRecord | null>(null);
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
    setActivationReviewed(false);
    setConfirmationKey("");
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
          : editor.kind === "activate"
            ? activationPayload(
                editor.row,
                inventory.current_environment,
                !!inventory.activation_enabled,
                note,
                activationReviewed,
              )
            : editor.kind === "runtime"
              ? runtimeControlPayload(
                  editor.row,
                  inventory.current_environment,
                  !!inventory.runtime_control_enabled,
                  editor.command,
                  note,
                  activationReviewed,
                  confirmationKey,
                )
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
          : `/v1/workspace-environments/${encodeURIComponent(editor.row.key)}/${editor.kind === "activate" ? "activate" : editor.kind === "runtime" ? "runtime-control" : "control"}`,
        "POST",
        payload,
      );
    } catch (e) {
      if (
        e instanceof ApiError &&
        [
          "STALE_VERSION",
          "ENVIRONMENT_STATE",
          "STALE_RUNTIME_REVIEW",
          "ENVIRONMENT_BUSY",
        ].includes(e.code)
      ) {
        setEditor(null);
        setNeedsRefresh(true);
        setError(e.message + " Refresh the list before trying again.");
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
        ? "Environment prepared. Assign an owner before local activation."
        : editor.kind === "activate"
          ? "Local environment activated. No records were copied; purchasing starts disabled."
          : editor.kind === "runtime"
            ? editor.command === "pause"
              ? "Environment paused. Records are preserved and its selected sessions were signed out."
              : editor.command === "retire"
                ? "Environment retired. Records are retained, runtime access is permanently disabled and this key is reserved."
                : "Environment resumed. Existing configuration is available to assigned members; signed-out sessions stay signed out."
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
          environments stay in Preparing until reviewed local activation. Assign
          yourself as owner first. Records, workloads and credentials are never
          promoted automatically.
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
                    : row.state === "retired"
                      ? "Runtime permanently retired. Records and assignments are retained. This key is reserved and cannot be reactivated or reused."
                      : row.state === "suspended"
                        ? "Runtime paused. Records and assignments are preserved; access is blocked until reviewed resume."
                        : row.human_runtime_enabled
                          ? "Active local runtime. Assigned members can select it from the header."
                          : "Preparation only. No runtime access is enabled."}
              </p>
              {row.unfinished_work &&
                Object.values(row.unfinished_work).some(
                  (count) => count > 0,
                ) && (
                  <p>
                    Unfinished work:{" "}
                    {Object.entries(row.unfinished_work)
                      .filter(([, count]) => count > 0)
                      .map(
                        ([kind, count]) =>
                          `${kind.replaceAll("_", " ")}: ${count}`,
                      )
                      .join(", ")}
                    . Finish, cancel or reconcile it before pausing.
                  </p>
                )}
              <div className="live-actions">
                <button
                  className="btn"
                  disabled={busy || loading}
                  aria-label={`View assignments for ${row.name}`}
                  onClick={() => setSelected(row)}
                >
                  View assignments
                </button>
                {canActivateEnvironment(
                  row,
                  inventory.current_environment,
                  !!inventory.activation_enabled,
                ) && (
                  <button
                    className="btn btn-primary"
                    disabled={!!locked}
                    aria-label={`Activate ${row.name} locally`}
                    onClick={() => openEditor({ kind: "activate", row })}
                  >
                    Activate locally
                  </button>
                )}
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
                {(["pause", "resume", "retire"] as const)
                  .filter((command) =>
                    canControlRuntime(
                      row,
                      inventory.current_environment,
                      !!inventory.runtime_control_enabled,
                      command,
                    ),
                  )
                  .map((command) => (
                    <button
                      className="btn"
                      key={command}
                      disabled={!!locked}
                      aria-label={`${command === "pause" ? "Pause" : command === "retire" ? "Retire" : "Resume"} ${row.name} runtime`}
                      onClick={() =>
                        openEditor({ kind: "runtime", row, command })
                      }
                    >
                      {command === "pause"
                        ? "Pause runtime"
                        : command === "retire"
                          ? "Retire runtime"
                          : "Resume runtime"}
                    </button>
                  ))}
              </div>
            </article>
          ))}
        </div>
      </div>
      {inventory?.activation_enabled && !inventory.read_only && (
        <EnvironmentAssetCopy
          user={me.user}
          environment={inventory.current_environment}
        />
      )}
      {editor && (
        <Modal
          title={
            editor.kind === "create"
              ? "Prepare environment"
              : editor.kind === "activate"
                ? `Activate ${editor.row.name} locally?`
                : editor.kind === "runtime"
                  ? `${editor.command === "pause" ? "Pause" : editor.command === "retire" ? "Retire" : "Resume"} ${editor.row.name} runtime?`
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
                : editor.kind === "activate"
                  ? "This activates an empty local runtime for its assigned members. No records, agents, tools, grants or credentials are copied. Purchasing starts disabled. This does not deploy or certify production."
                  : editor.kind === "runtime"
                    ? editor.command === "pause"
                      ? `This blocks runtime access and signs out ${editor.row.selected_sessions} selected sessions. Records, assignments and configuration are preserved. Unfinished work blocks this change. Switch to staging before managing this environment.`
                      : editor.command === "retire"
                        ? "This permanently retires the paused local runtime. Records, assignments and configuration are retained. Runtime access cannot be resumed, the environment cannot be reactivated and its key cannot be reused. This does not delete data or revoke credentials at external providers."
                        : "This restores runtime access for assigned members using the existing policies, agents, grants and credentials. Review that configuration before resuming. Signed-out sessions are not restored and no work is replayed."
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
            {editor.kind === "runtime" && editor.command === "retire" && (
              <label className="field">
                <span>Type environment key {editor.row.key} to retire</span>
                <input
                  value={confirmationKey}
                  onChange={(event) => setConfirmationKey(event.target.value)}
                  disabled={busy}
                  required
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            )}
            {(editor.kind === "activate" || editor.kind === "runtime") && (
              <label className="product-check">
                <input
                  type="checkbox"
                  checked={activationReviewed}
                  disabled={busy}
                  onChange={(e) => setActivationReviewed(e.target.checked)}
                />
                {editor.kind === "runtime"
                  ? "I reviewed the environment, existing configuration and session sign-out effect."
                  : "I reviewed the assigned members and the empty local runtime boundary."}
              </label>
            )}
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
                disabled={
                  busy ||
                  needsRefresh ||
                  ((editor.kind === "activate" || editor.kind === "runtime") &&
                    !activationReviewed) ||
                  (editor.kind === "runtime" &&
                    editor.command === "retire" &&
                    confirmationKey !== editor.row.key)
                }
              >
                {busy
                  ? "Saving…"
                  : editor.kind === "create"
                    ? "Prepare environment"
                    : editor.kind === "activate"
                      ? "Confirm local activation"
                      : editor.kind === "runtime"
                        ? editor.command === "pause"
                          ? "Confirm pause"
                          : editor.command === "retire"
                            ? "Confirm permanent retirement"
                            : "Confirm resume"
                        : editor.command === "archive"
                          ? "Confirm archive"
                          : "Restore to Preparing"}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {selected && (
        <EnvironmentMembersDialog
          key={selected.key}
          environment={selected}
          readOnly={inventory?.read_only === true}
          onClose={() => setSelected(null)}
          onChanged={() => {
            void refresh().catch(() => setNeedsRefresh(true));
          }}
        />
      )}
    </section>
  );
}
