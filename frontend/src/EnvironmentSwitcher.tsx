import { useState } from "react";
import { api, ApiError, setCsrf } from "./api";
import { sessionContext } from "./sessionContext";
import { selectionPayload, type EnvironmentChoice } from "./environmentSwitch";
import { requestNavigationGuard } from "./navigationGuard";
import { Modal } from "./RuntimeDialog";
export function EnvironmentSwitcher({ me }: { me: Record<string, any> }) {
  const [open, setOpen] = useState(false),
    [choices, setChoices] = useState<EnvironmentChoice[]>([]),
    [selected, setSelected] = useState(""),
    [reviewed, setReviewed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function load() {
    setSelected("");
    setReviewed(false);
    setError("");
    try {
      const result = await api("/v1/session-context/choices");
      setChoices(result.items);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function show() {
    const next = () => {
      setOpen(true);
      void load();
    };
    if (!requestNavigationGuard(next)) next();
  }
  async function select() {
    const context = sessionContext.capture().context,
      choice = choices.find((c) => c.key === selected);
    if (!context || !choice || busy) return;
    setBusy(true);
    setError("");
    try {
      await api(
        "/v1/session-context/select",
        "POST",
        selectionPayload(context, choice, reviewed),
      );
      setCsrf("");
      sessionContext.clear();
    } catch (e) {
      if (!(e instanceof ApiError) || e.status >= 500) {
        setCsrf("");
        sessionContext.clear();
      } else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!me.runtime_context?.switching_enabled)
    return <span className="environment">{me.environment}</span>;
  return (
    <>
      <button
        className="btn environment"
        aria-label="Choose runtime environment"
        onClick={show}
      >
        {me.environment} · Switch
      </button>
      {open && (
        <Modal
          title="Choose local environment"
          onClose={() => {
            if (!busy) setOpen(false);
          }}
        >
          <p>
            Current forms and loaded views will reset. Export unsaved design
            work first. Background operations stay in their original
            environment.
          </p>
          <label className="field">
            <span>Active environment</span>
            <select
              value={selected}
              disabled={busy}
              onChange={(e) => {
                setSelected(e.target.value);
                setReviewed(false);
              }}
            >
              <option value="">Choose an assigned environment</option>
              {choices
                .filter((c) => c.key !== me.environment)
                .map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name} ({c.key})
                  </option>
                ))}
            </select>
          </label>
          {choices.filter((c) => c.key !== me.environment).length === 0 && (
            <p>
              No other active environments are assigned to you. An owner can
              prepare, assign and activate an empty local environment in
              Workspace settings.
            </p>
          )}
          <label className="product-check">
            <input
              type="checkbox"
              checked={reviewed}
              disabled={busy}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            I saved or exported my changes and reviewed the target environment.
          </label>
          {error && (
            <p role="alert" className="ops-alert">
              {error}
            </p>
          )}
          <div className="live-actions">
            <button className="btn" disabled={busy} onClick={() => void load()}>
              Refresh choices
            </button>
            <button
              className="btn btn-primary"
              disabled={busy || !selected || !reviewed}
              onClick={() => void select()}
            >
              {busy ? "Switching…" : "Switch environment"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
