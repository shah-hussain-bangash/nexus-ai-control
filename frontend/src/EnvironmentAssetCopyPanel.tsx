import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import {
  readRecovery,
  acknowledgeRecovery,
  type RecoveryRecord,
} from "./inferenceRecovery";
import {
  copyPayload,
  copyOutcome,
  type CopyAsset,
  type CopyTarget,
} from "./environmentAssetCopy";

export function EnvironmentAssetCopy({
  user,
  environment,
}: {
  user: { id: string; org_id: string };
  environment: string;
}) {
  const scope = liveIntentScope(
    "asset-copy",
    user.org_id,
    user.id,
    environment,
  );
  const [assets, setAssets] = useState<CopyAsset[]>([]),
    [targets, setTargets] = useState<CopyTarget[]>([]);
  const [assetId, setAssetId] = useState(""),
    [targetKey, setTargetKey] = useState(""),
    [name, setName] = useState(""),
    [note, setNote] = useState("");
  const [reviewed, setReviewed] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<RecoveryRecord | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const asset = assets.find((a) => a.id === assetId),
    target = targets.find((t) => t.key === targetKey);
  useEffect(() => {
    let active = true;
    load().catch((e) => {
      if (active) setError((e as Error).message);
    });
    return () => {
      active = false;
    };
  }, [scope]);
  async function load() {
    setLoading(true);
    setError("");
    setReviewed(false);
    try {
      setPending(readRecovery(sessionStorage, scope, true));
      const [source, choices] = await Promise.all([
        api("/v1/workbench"),
        api("/v1/session-context/choices"),
      ]);
      setAssets(
        source.assets.filter(
          (a: CopyAsset) =>
            ["prompt", "guardrail"].includes(a.kind) &&
            a.status === "validated",
        ),
      );
      setTargets(
        choices.items.filter((t: CopyTarget) => t.key !== environment),
      );
      setAssetId("");
      setTargetKey("");
      setName("");
      setNote("");
    } finally {
      setLoading(false);
    }
  }
  function saved(value: ReturnType<typeof copyOutcome>) {
    setPending(null);
    setReviewed(false);
    setNotice(
      value.status === "cancelled"
        ? "The pending copy was cancelled. A delayed request with that key cannot create a draft."
        : `Draft ${value.name || value.target_asset_id} was created in ${value.target_environment}. Switch there to review and validate it. Recovery or cancellation never deletes an already-created draft.`,
    );
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!asset || !target || busy || pending) return;
    let body;
    try {
      body = copyPayload(environment, asset, target, name, note, reviewed);
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await sendLiveIntent(
        sessionStorage,
        scope,
        body,
        async (key) =>
          copyOutcome(
            await api("/v1/environment-asset-copies", "POST", body, key),
            environment,
          ),
      );
      saved(result);
    } catch (e) {
      setError((e as Error).message);
      try {
        setPending(readRecovery(sessionStorage, scope, true));
      } catch (storageError) {
        setError((storageError as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }
  async function resolve(command: "recover" | "cancel") {
    if (!pending || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = copyOutcome(
        await api(`/v1/environment-asset-copies/${command}`, "POST", {
          key: pending.key,
        }),
        environment,
      );
      acknowledgeRecovery(sessionStorage, scope, pending, result);
      saved(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const locked = busy || loading || !!pending;
  return (
    <section className="panel runtime-card" aria-label="Copy reviewed designs">
      <h2>Copy reviewed designs</h2>
      <p>
        Copy a validated prompt or guardrail from <strong>{environment}</strong>{" "}
        into a different assigned active local environment. Each copy starts as
        a new draft. Existing designs, validation history, credentials, agents
        and approvals are never overwritten or copied.
      </p>
      <button
        className="btn"
        disabled={busy || loading}
        onClick={() => void load().catch((e) => setError((e as Error).message))}
      >
        Refresh copy choices
      </button>
      {loading && <p role="status">Loading reviewed designs…</p>}
      {pending && (
        <div className="ops-alert">
          <p>
            A copy request is awaiting confirmation. Recover its result, or
            cancel the pending intent before creating another copy. Cancellation
            preserves a draft that already exists.
          </p>
          <button
            className="btn"
            disabled={busy}
            onClick={() => void resolve("recover")}
          >
            Recover copy result
          </button>
          <button
            className="btn"
            disabled={busy}
            onClick={() => void resolve("cancel")}
          >
            Cancel pending copy
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="ops-alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <form className="runtime-form" onSubmit={submit}>
        <label className="field">
          <span>Validated source design</span>
          <select
            disabled={locked}
            value={assetId}
            onChange={(e) => {
              const next = assets.find((a) => a.id === e.target.value);
              setAssetId(e.target.value);
              setName(next ? (next.name + " copy").slice(0, 120) : "");
              setReviewed(false);
            }}
          >
            <option value="">Choose a validated prompt or guardrail</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} · {a.kind} · v{a.version}
              </option>
            ))}
          </select>
        </label>
        {asset && (
          <details open>
            <summary>Review source configuration</summary>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {JSON.stringify(asset.config, null, 2)}
            </pre>
            <p>{asset.description}</p>
          </details>
        )}
        <label className="field">
          <span>Target environment for draft</span>
          <select
            disabled={locked}
            value={targetKey}
            onChange={(e) => {
              setTargetKey(e.target.value);
              setReviewed(false);
            }}
          >
            <option value="">Choose another assigned active environment</option>
            {targets.map((t) => (
              <option key={t.key} value={t.key}>
                {t.name} ({t.key})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>New draft name</span>
          <input
            disabled={locked}
            value={name}
            minLength={2}
            maxLength={120}
            required
            onChange={(e) => {
              setName(e.target.value);
              setReviewed(false);
            }}
          />
        </label>
        <label className="field">
          <span>Reason for design copy</span>
          <input
            disabled={locked}
            value={note}
            minLength={5}
            maxLength={500}
            required
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <label className="product-check">
          <input
            type="checkbox"
            checked={reviewed}
            disabled={locked}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          I reviewed the source contents and target access. The copy is a new
          draft and will not run or become validated automatically.
        </label>
        {!loading && (!assets.length || !targets.length) && (
          <p>
            Validate a prompt or guardrail in this environment and assign
            yourself to another active local environment to enable copying.
          </p>
        )}
        <button
          className="btn btn-primary"
          disabled={locked || !asset || !target || !reviewed}
        >
          {busy ? "Saving…" : "Copy as new draft"}
        </button>
      </form>
    </section>
  );
}
