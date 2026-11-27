import { useEffect, useState } from "react";
import { api } from "./api";
import { liveIntentScope, sendLiveIntent } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { indexJobRequest } from "./indexJobRequest";
type Row = Record<string, any>;
export function BackgroundIndexJobs({
  me,
  sources,
  enabled,
}: {
  me: Row;
  sources: { id: string; version: number }[];
  enabled: boolean;
}) {
  const [name, setName] = useState(""),
    [jobs, setJobs] = useState<Row[]>([]);
  const [selected, setSelected] = useState(""),
    [note, setNote] = useState("");
  const [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const scope = liveIntentScope(
    "index-build-job",
    me.user.org_id,
    me.user.id,
    me.environment,
  );
  const operate = me.permissions?.includes("operate"),
    job = jobs.find((row) => row.id === selected);
  async function refresh() {
    const result = await api("/v1/neural-index-jobs");
    setJobs(result.items);
  }
  useEffect(() => {
    void refresh().catch((e: Error) => setMessage(e.message));
  }, []);
  async function act(task: () => Promise<Row>) {
    setBusy(true);
    setMessage("");
    try {
      const row = await task();
      setSelected(row.id);
      setConfirm(false);
      setMessage(
        `Build ${row.status}. ${row.error_code || "Refresh to see worker progress."}`,
      );
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Build request failed.");
    } finally {
      setBusy(false);
    }
  }
  const control = (command: string) => {
    if (!job) return;
    void act(() =>
      api(
        `/v1/neural-index-jobs/${encodeURIComponent(job.id)}/control/${command}`,
        "POST",
        { expected_version: job.version, note, confirm_uncertain: confirm },
      ),
    );
  };
  return (
    <section
      className="panel runtime-card"
      aria-label="Background index builds"
    >
      <h3>Background index builds</h3>
      <p>
        Queue the documents selected above. The execution worker builds eight
        passages at a time and saves each completed batch. Up to 32 passages per
        snapshot. Unfinished snapshots cannot be searched.
      </p>
      <p>
        Keep the normal execution worker running to process queued jobs. Refresh
        below to see progress. Pausing and cancelling an active batch take
        effect at its boundary; they do not stop a model request already sent.
      </p>
      {message && <p role="status">{message}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const body = indexJobRequest(name, sources);
          void act(() =>
            sendLiveIntent(sessionStorage, scope, body, (key) =>
              api("/v1/neural-index-jobs", "POST", body, key),
            ),
          );
        }}
      >
        <label className="field">
          <span>Background snapshot name</span>
          <input
            value={name}
            required
            minLength={2}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <p>{sources.length} pinned source documents selected.</p>
        <div className="live-actions">
          <button
            className="btn btn-primary"
            disabled={
              busy ||
              !enabled ||
              !operate ||
              !sources.length ||
              sources.length > 20 ||
              name.trim().length < 2
            }
          >
            Queue background build
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const pending = readRecovery(sessionStorage, scope);
                if (!pending)
                  throw Error(
                    "No unacknowledged job submission in this account and environment.",
                  );
                const row = await api("/v1/neural-index-jobs/recover", "POST", {
                  key: pending.key,
                });
                acknowledgeRecovery(sessionStorage, scope, pending, row);
                return row;
              })
            }
          >
            Recover submitted job
          </button>
        </div>
      </form>
      <button
        className="btn"
        disabled={busy}
        onClick={() =>
          void refresh().catch((e: Error) => setMessage(e.message))
        }
      >
        Refresh build progress
      </button>
      <label className="field">
        <span>Recent build job</span>
        <select
          value={selected}
          disabled={busy}
          onChange={(e) => {
            setSelected(e.target.value);
            setConfirm(false);
          }}
        >
          <option value="">Choose a build</option>
          {jobs.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} · {row.status} · {row.completed_passages}/
              {row.total_passages}
            </option>
          ))}
        </select>
      </label>
      {job && (
        <>
          <p>
            <strong>{job.status}</strong> · version {job.version} · checkpointed
            passages {job.completed_passages}/{job.total_passages} · snapshot{" "}
            {job.index?.status || "removed"}
          </p>
          <progress
            value={job.completed_passages}
            max={job.total_passages}
            aria-label="Checkpointed build passages"
          />
          <p>
            Confirmed local HTTP calls {job.confirmed_http_calls} · total{" "}
            {job.provider_calls ?? "unknown because a batch was interrupted"}
          </p>
          {job.stop_requested && (
            <p role="status">
              {job.stop_requested} requested; waiting for the current batch
              boundary.
            </p>
          )}
          {job.error_code && <p>{job.error_code}</p>}
          {(job.uncertain_batch || job.lease_expired) && (
            <p role="status">
              The last uncommitted batch may already have run. Resuming can
              execute that batch again. Committed batches are reused.
            </p>
          )}
          <label className="field">
            <span>Reason for this control</span>
            <input
              minLength={5}
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={confirm}
              onChange={(e) => setConfirm(e.target.checked)}
            />
            I acknowledge that resuming an uncertain batch may execute it again.
          </label>
          <div className="live-actions">
            <button
              className="btn"
              disabled={
                busy ||
                !operate ||
                note.trim().length < 5 ||
                !["queued", "processing"].includes(job.status)
              }
              onClick={() => control("pause")}
            >
              Pause build
            </button>
            <button
              className="btn"
              disabled={
                busy ||
                !operate ||
                note.trim().length < 5 ||
                (!["paused", "interrupted"].includes(job.status) &&
                  !job.lease_expired) ||
                ((job.uncertain_batch || job.lease_expired) && !confirm)
              }
              onClick={() => control("resume")}
            >
              Resume build
            </button>
            <button
              className="btn"
              disabled={
                busy ||
                !operate ||
                note.trim().length < 5 ||
                !["queued", "processing", "paused", "interrupted"].includes(
                  job.status,
                )
              }
              onClick={() => control("cancel")}
            >
              Cancel build and purge staging vectors
            </button>
          </div>
          <p>{job.boundary}</p>
          {job.status === "completed" && (
            <p>
              Refresh the stored-index list to search the published snapshot.
              Cancelled or failed jobs retain receipts; active staging vectors
              are purged.
            </p>
          )}
        </>
      )}
    </section>
  );
}
