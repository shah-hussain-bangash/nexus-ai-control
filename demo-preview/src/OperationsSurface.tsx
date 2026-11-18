import { useEffect, useRef, useState } from "react";
import { Plus, Search, X, Trash2, ArrowRight, FileText } from "lucide-react";
import type { InterfaceDraft, InterfaceModule } from "./interfaceDesign";
type PreviewRow = { id: string; state: string; values: Record<string, string> };
export function OperationsSurface({
  module,
  draft,
  disabled,
  onChange,
}: {
  module: InterfaceModule;
  draft: InterfaceDraft;
  disabled: boolean;
  onChange: (rows: PreviewRow[]) => void;
}) {
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [editor, setEditor] = useState<PreviewRow | null>(null),
    [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const rows = draft.config.surface_rows || [];
  const filtered = rows.filter(
    (r) =>
      (filter === "all" || r.state === filter) &&
      Object.values(r.values)
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  useEffect(() => {
    if (editor) dialog.current?.showModal();
    else dialog.current?.close();
  }, [Boolean(editor)]);
  function open(row?: PreviewRow) {
    setError("");
    setEditor(
      row
        ? structuredClone(row)
        : {
            id: crypto.randomUUID(),
            state: "draft",
            values: Object.fromEntries(
              module.record_columns.map((c) => [c.id, c.default]),
            ),
          },
    );
  }
  function apply(e: React.FormEvent) {
    e.preventDefault();
    if (!editor) return;
    for (const c of module.record_columns) {
      const value = editor.values[c.id];
      if (!value?.trim() || value.length > 250) {
        setError("Complete every preview field using at most 250 characters.");
        return;
      }
      if (
        c.type === "reference" &&
        !/^(env:[A-Z][A-Z0-9_]{2,70}|secret:\/\/[A-Za-z0-9/_-]{3,180})$/.test(
          value,
        )
      ) {
        setError("Enter a secret reference only; never paste a credential.");
        return;
      }
    }
    onChange(
      rows.some((r) => r.id === editor.id)
        ? rows.map((r) => (r.id === editor.id ? editor : r))
        : [...rows, editor],
    );
    setEditor(null);
  }
  return (
    <>
      <div className="studio-section-title">
        <div>
          <h3>Operational screen preview</h3>
          <p>{module.record_boundary}</p>
        </div>
        <button
          className="btn btn-primary"
          disabled={disabled || rows.length >= 30}
          onClick={() => open()}
        >
          <Plus size={16} /> Add preview record
        </button>
      </div>
      <div className="studio-surface-toolbar">
        <label className="studio-search">
          <Search size={16} />
          <input
            aria-label="Search operational preview records"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search preview metadata…"
          />
        </label>
        <select
          aria-label="Operational preview state"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All preview states</option>
          {module.record_states.map((s) => (
            <option key={s} value={s}>
              {s.replaceAll("_", " ")}
            </option>
          ))}
        </select>
        <span>{rows.length} preview records</span>
      </div>
      <div className="studio-surface-table">
        <table>
          <thead>
            <tr>
              {module.record_columns.map((c) => (
                <th key={c.id}>{c.label}</th>
              ))}
              <th>Preview state</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={module.record_columns.length + 2}>
                  <div className="studio-preview-empty">
                    <FileText size={28} />
                    <h3>
                      {rows.length
                        ? "No preview records match"
                        : "Design the list-to-detail journey"}
                    </h3>
                    <p>
                      Add a synthetic preview record to review filtering,
                      details, editing and state changes. Save the parent
                      interface plan to retain these examples.
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((row) => (
                <tr key={row.id}>
                  {module.record_columns.map((c) => (
                    <td key={c.id}>{row.values[c.id]}</td>
                  ))}
                  <td>
                    <span className="studio-boundary-badge">
                      {row.state.replaceAll("_", " ")} · UI example
                    </span>
                  </td>
                  <td>
                    <button className="text-btn" onClick={() => open(row)}>
                      Inspect <ArrowRight size={14} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <dialog
        ref={dialog}
        className="studio-dialog"
        aria-label="Operational preview record"
        onCancel={(e) => {
          e.preventDefault();
          setEditor(null);
        }}
      >
        {editor && (
          <>
            <header>
              <div>
                <span className="studio-overline">
                  UI RECORD / NO RUNTIME EFFECT
                </span>
                <h2>Operational preview record</h2>
              </div>
              <button
                className="icon-btn"
                onClick={() => setEditor(null)}
                aria-label="Close preview record"
              >
                <X size={20} />
              </button>
            </header>
            <form className="studio-dialog-body" onSubmit={apply}>
              <p>{module.record_boundary}</p>
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              <div className="studio-form-grid">
                {module.record_columns.map((c) => (
                  <label className="studio-field" key={c.id}>
                    {c.label}
                    <input
                      value={editor.values[c.id]}
                      required
                      maxLength={250}
                      disabled={disabled}
                      onChange={(e) =>
                        setEditor({
                          ...editor,
                          values: { ...editor.values, [c.id]: e.target.value },
                        })
                      }
                    />
                    {c.type === "reference" && (
                      <small>
                        Use env:VARIABLE_NAME or secret://reference only.
                      </small>
                    )}
                  </label>
                ))}
                <label className="studio-field studio-full">
                  Preview record state
                  <select
                    disabled={disabled}
                    value={editor.state}
                    onChange={(e) =>
                      setEditor({ ...editor, state: e.target.value })
                    }
                  >
                    {module.record_states.map((s) => (
                      <option key={s} value={s}>
                        {s.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="studio-inline-note">
                Applying changes updates this interface draft only. Use Save
                revision to persist the parent plan.
              </p>
              <div className="studio-dialog-actions">
                {rows.some((r) => r.id === editor.id) && (
                  <button
                    type="button"
                    className="text-btn studio-archive"
                    disabled={disabled}
                    onClick={() => {
                      onChange(rows.filter((r) => r.id !== editor.id));
                      setEditor(null);
                    }}
                  >
                    <Trash2 size={15} /> Remove preview record
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-outline"
                  onClick={() => setEditor(null)}
                >
                  Close
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={disabled}
                >
                  Apply to interface plan
                </button>
              </div>
            </form>
          </>
        )}
      </dialog>
    </>
  );
}
