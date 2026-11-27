import { useEffect, useState } from "react";
import { api } from "./api";
type Row = Record<string, any>;
export function SecretInputStatus({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const owner = me.permissions?.includes("members");
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setData(await api("/v1/secret-inputs"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (owner) void refresh();
  }, [owner]);
  if (!owner) return null;
  const label = (value: string) =>
    ({
      file: "Mounted file configured",
      environment: "Environment value configured",
      not_configured: "Not configured",
      supplied_at_startup: "Supplied at startup",
      ambiguous: "Conflicting inputs — blocked",
      not_used: "Not used",
    })[value] || value;
  return (
    <section className="panel settings-card">
      <h2>Secret input sources</h2>
      <p>
        Read-only configuration view. It never reads secret files or displays
        secret values or paths.
      </p>
      {error && <p role="alert">{error}</p>}
      <button className="btn" disabled={busy} onClick={() => void refresh()}>
        {busy ? "Refreshing…" : "Refresh input sources"}
      </button>
      {data && (
        <>
          <dl>
            {data.startup_inputs.map((row: Row) => (
              <div key={row.name}>
                <dt>{row.name}</dt>
                <dd>
                  {label(row.source)} · {row.reload}
                </dd>
              </div>
            ))}
          </dl>
          <h3>Provider credential namespace</h3>
          <p>
            {data.provider_input_counts.file} file inputs ·{" "}
            {data.provider_input_counts.environment} environment inputs ·{" "}
            {data.provider_input_counts.ambiguous} conflicting inputs
          </p>
          <p>
            Counts reflect configuration, not successful authentication or file
            readability. Variable names are hidden.
          </p>
          <p>Business credential: {label(data.business_input.source)}</p>
          <p>{data.boundary}</p>
        </>
      )}
    </section>
  );
}
