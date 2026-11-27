import { useEffect, useState } from "react";
import { api } from "./api";
import { sendLiveIntent, liveIntentScope } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
type Row = Record<string, any>;
function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function SignedAuditEvidence({ me }: { me: Row }) {
  const [data, setData] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [note, setNote] = useState(""),
    [limit, setLimit] = useState(200);
  const allowed = me.permissions?.includes("export");
  const scope = liveIntentScope(
    "signed-audit",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  async function refresh() {
    setData(await api("/v1/signed-audit-evidence"));
  }
  useEffect(() => {
    if (allowed) void refresh().catch((e) => setMessage(e.message));
  }, [allowed]);
  async function act(task?: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const receipt = task ? await task() : null;
      await refresh();
      setMessage(
        receipt
          ? `Snapshot ${receipt.id}: ${receipt.status}. Download it below; verify against a separately trusted public key.`
          : "Signing status reloaded.",
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!allowed) return null;
  return (
    <details className="panel runtime-card">
      <summary>Signed audit metadata snapshots</summary>
      <p>
        Optional Ed25519 signatures authenticate a bounded metadata snapshot.
        They do not establish log completeness, immutable storage or production
        readiness. Event details and request payloads are excluded.
      </p>
      {message && <p role="status">{message}</p>}
      <button className="btn" disabled={busy} onClick={() => void act()}>
        Reload signing status
      </button>
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void act(async () => {
            const pending = readRecovery(sessionStorage, scope);
            if (!pending)
              throw Error(
                "No unacknowledged snapshot for this account and environment.",
              );
            const row = await api("/v1/signed-audit-evidence/recover", "POST", {
              key: pending.key,
            });
            acknowledgeRecovery(sessionStorage, scope, pending, row);
            return row;
          })
        }
      >
        Recover snapshot receipt
      </button>
      {data && (
        <>
          <p>
            Signing:{" "}
            {data.available
              ? "available"
              : data.enabled
                ? "configured key unavailable"
                : "disabled"}{" "}
            · environment {me.environment}
          </p>
          {!data.available && (
            <p>
              An operator must configure a dedicated private signing key on the
              server. No key is created here.
            </p>
          )}
          {data.available && (
            <>
              <p>
                Current signing key fingerprint: <code>{data.key_id}</code>
              </p>
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  download(
                    `nexus-audit-${data.key_id}.pub.pem`,
                    data.public_key_pem,
                    "application/x-pem-file",
                  )
                }
              >
                Download current public key
              </button>
              <p>
                Confirm this fingerprint through a trusted operator before
                accepting the downloaded public key. After rotation, older
                snapshots require the previously trusted public key.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(() => {
                    const body = { expected_key_id: data.key_id, limit, note };
                    return sendLiveIntent(sessionStorage, scope, body, (key) =>
                      api("/v1/signed-audit-evidence", "POST", body, key),
                    );
                  });
                }}
              >
                <label className="field">
                  <span>Latest event metadata to include (1–1000)</span>
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    step={1}
                    required
                    value={Number.isNaN(limit) ? "" : limit}
                    onChange={(e) => setLimit(e.target.valueAsNumber)}
                  />
                </label>
                <label className="field">
                  <span>Snapshot note (10–500 characters, no secrets)</span>
                  <input
                    required
                    minLength={10}
                    maxLength={500}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
                <button
                  className="btn btn-primary"
                  disabled={
                    busy || note.trim().length < 10 || !Number.isInteger(limit)
                  }
                >
                  Create signed metadata snapshot
                </button>
              </form>
            </>
          )}
          <h4>Your recent snapshots (latest 20)</h4>
          {!data.items.length && <p>No saved snapshots in this environment.</p>}
          {data.items.map((row: Row) => (
            <article key={row.id}>
              <p>
                {row.id} · {row.records} metadata records ·{" "}
                {row.truncated
                  ? "truncated to selected limit"
                  : "no truncation at sampling time"}
              </p>
              <p>
                Key {row.key_id} · expires{" "}
                {new Date(row.expires * 1000).toLocaleString()}
              </p>
              <button
                className="btn"
                disabled={busy || row.expires * 1000 <= Date.now()}
                onClick={async () => {
                  setBusy(true);
                  setMessage("");
                  try {
                    const envelope = await api(
                      `/v1/signed-audit-evidence/${encodeURIComponent(row.id)}`,
                    );
                    download(
                      `nexus-signed-audit-${row.id}.json`,
                      JSON.stringify(envelope, null, 2),
                      "application/json",
                    );
                  } catch (e) {
                    setMessage((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Download signed snapshot
              </button>
            </article>
          ))}
          <p>{data.boundary}</p>
          <p>
            Offline verification is available through the audit signature
            command documented in the repository. It requires a separately
            trusted public key and the expected workspace and environment.
          </p>
        </>
      )}
    </details>
  );
}
