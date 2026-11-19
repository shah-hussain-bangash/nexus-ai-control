import { useEffect, useRef, useState } from "react";
import { FileUp, RefreshCw, ShieldCheck, ArrowRight } from "lucide-react";
import { api } from "./api";
import { Modal } from "./RuntimeDialog";
import { sendLiveIntent, liveIntentScope } from "./liveIntent";
import { readRecovery, acknowledgeRecovery } from "./inferenceRecovery";
import { registerNavigationGuard } from "./navigationGuard";
import { queuedFileMetadata } from "./liveRequests";
import "./intake.css";
type Row = Record<string, any>;
function pending(scope: string) {
  try {
    return readRecovery(sessionStorage, scope);
  } catch {
    return null;
  }
}
const errorText: Record<string, string> = {
  OCR_DISABLED:
    "OCR is disabled on the worker. Ask the operator to provision and enable Tesseract.",
  OCR_REQUIRED:
    "This PDF needs OCR. Enable the OCR worker or upload a searchable PDF.",
  OCR_LANGUAGE_UNAVAILABLE:
    "The requested OCR language is not configured. No English fallback was used.",
  OCR_ENGINE_UNAVAILABLE:
    "The worker could not find the configured Tesseract executable.",
  OCR_ENGINE_FAILED:
    "OCR failed. Check language data and review the source before retrying.",
  EXTRACTION_TIMEOUT:
    "The bounded parser timed out. Simplify the file or inspect worker resource limits.",
  PDF_PAGE_LIMIT: "The PDF exceeds the 12-page limit.",
  EXTRACTED_TEXT_LIMIT:
    "Extracted text exceeds 32 KiB. Split the source into smaller documents.",
  WORKER_INTERRUPTED:
    "A prior worker lease expired. Review the file and retry explicitly.",
  UNSUPPORTED_OR_MALFORMED_FILE:
    "The parser rejected this file. Re-export a clean document.",
  REQUESTER_REVOKED: "The requesting author is no longer authorized.",
  REVIEW_WINDOW_EXPIRED:
    "The 24-hour review window expired. Pending source bytes were removed.",
};
export function IntakeQueue({
  me,
  onPublished,
}: {
  me: Row;
  onPublished: (id: string) => void;
}) {
  const [rows, setRows] = useState<Row[]>([]),
    [detail, setDetail] = useState<Row | null>(null),
    [caps, setCaps] = useState<Row | null>(null),
    [offset, setOffset] = useState(0),
    [next, setNext] = useState<number | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [uploading, setUploading] = useState(false),
    [title, setTitle] = useState(""),
    [filename, setFilename] = useState(""),
    [content, setContent] = useState(""),
    [language, setLanguage] = useState("English"),
    [mode, setMode] = useState("auto"),
    [roles, setRoles] = useState<string[]>([]),
    [target, setTarget] = useState<Row | null>(null),
    [command, setCommand] = useState(""),
    [note, setNote] = useState(""),
    [reviewed, setReviewed] = useState(false),
    [discard, setDiscard] = useState(false);
  const scope = liveIntentScope("intake", me.user.org_id, me.user.id, me.environment),
    [intent, setIntent] = useState(() => pending(scope));
  const canOperate = me.permissions?.includes("operate"),
    selected = useRef(""),
    afterLeave = useRef<() => void>(() => {});
  const dirty = uploading && Boolean(content);
  useEffect(() => {
    if (!dirty) return;
    const stop = registerNavigationGuard((next) => {
      afterLeave.current = next;
      setDiscard(true);
    });
    const unload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", unload);
    return () => {
      stop();
      window.removeEventListener("beforeunload", unload);
    };
  }, [dirty]);
  async function inspect(id: string) {
    try {
      const r = await api("/v1/ingestion-jobs/" + id);
      selected.current = id;
      setDetail(r);
    } catch (e) {
      setDetail(null);
      setError((e as Error).message);
    }
  }
  async function load() {
    try {
      const r = await api("/v1/ingestion-jobs?offset=" + offset + "&limit=20");
      setRows(r.items);
      setNext(r.next_offset);
      if (selected.current) await inspect(selected.current);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    api("/v1/ingestion-capabilities")
      .then(setCaps)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [offset]);
  async function choose(file?: File) {
    if (!file) return;
    try {
      queuedFileMetadata(file);
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (const byte of bytes) binary += String.fromCharCode(byte);
      setContent(btoa(binary));
      setFilename(file.name);
      setTitle(file.name.replace(/\.[^.]+$/, ""));
      setError("");
    } catch (e) {
      setContent("");
      setError((e as Error).message);
    }
  }
  function close() {
    if (busy) return;
    if (content) {
      afterLeave.current = () => {
        setUploading(false);
        setContent("");
      };
      setDiscard(true);
    } else setUploading(false);
  }
  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!content) return;
    setBusy(true);
    setError("");
    try {
      const body = {
        title,
        filename,
        content_base64: content,
        language,
        extraction_mode: mode,
        allowed_roles: roles,
        allowed_users: [],
      };
      const result = await sendLiveIntent<Row & { id: string; status: string }>(
        sessionStorage,
        scope,
        body,
        (key) => api("/v1/ingestion-jobs", "POST", body, key),
      );
      setIntent(null);
      setUploading(false);
      setContent("");
      setOffset(0);
      await load();
      await inspect(result.id);
      setNotice(
        "File queued. Extraction is private until an authorized operator reviews and publishes it.",
      );
    } catch (e) {
      setIntent(pending(scope));
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recover() {
    if (!intent) return;
    setBusy(true);
    try {
      const r = await api("/v1/ingestion-jobs/recover", "POST", {
        key: intent.key,
      });
      acknowledgeRecovery(sessionStorage, scope, intent, r);
      setIntent(null);
      await load();
      await inspect(r.id);
      setNotice("Original intake recovered without queuing another parse.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function act(e: React.FormEvent) {
    e.preventDefault();
    if (!target) return;
    setBusy(true);
    setError("");
    try {
      const r = await api(
        "/v1/ingestion-jobs/" +
          target.id +
          (command === "publish" ? "/publish" : "/control/" + command),
        "POST",
        {
          expected_version: target.version,
          note,
          ...(command === "publish" ? { reviewed } : {}),
        },
      );
      setTarget(null);
      setCommand("");
      await load();
      await inspect(r.id);
      setNotice(
        command === "publish"
          ? "Reviewed source published with its original hash and extraction provenance."
          : "Intake control saved. Cancellation prevents publication of any late parser result.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function open(command: string) {
    setTarget(detail);
    setCommand(command);
    setNote("");
    setReviewed(false);
    setError("");
  }
  return (
    <section className="intake-queue" aria-label="Document processing queue">
      <header className="intake-heading">
        <div>
          <small>PDF · DOCX · IMAGE OCR</small>
          <h2>Extract. Review. Publish.</h2>
          <p>
            Queue a source file, inspect extracted text and approve publication
            to your authorized document library.
          </p>
        </div>
        <div className="live-actions">
          <button className="btn btn-outline" disabled={busy} onClick={load}>
            <RefreshCw size={16} />
            Refresh intake
          </button>
          <button
            className="btn btn-primary"
            disabled={!canOperate || busy}
            onClick={() => {
              setUploading(true);
              setContent("");
              setFilename("");
              setTitle("");
              setRoles([]);
              setMode("auto");
              setLanguage("English");
              setError("");
            }}
          >
            <FileUp size={17} />
            Queue a file
          </button>
        </div>
      </header>
      {caps && (
        <div className="intake-caps">
          <span>1 MiB per file</span>
          <span>12 PDF pages</span>
          <span>32 KiB extracted text</span>
          <span>
            {caps.ocr_enabled
              ? "OCR enabled · " + caps.ocr_languages_configured
              : "OCR disabled · searchable PDF/DOCX available"}
          </span>
          <span>Review expires after 24 hours</span>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="ops-alert" role="status">
          {notice}
        </p>
      )}
      {intent && (
        <div className="ops-alert">
          <p>
            An unacknowledged intake remains in this tab. File content is not
            saved in browser storage.
          </p>
          <button className="btn btn-outline" disabled={busy} onClick={recover}>
            Recover pending intake
          </button>
        </div>
      )}
      <div className="live-grid">
        <section className="live-list" aria-label="Intake jobs">
          {rows.length ? (
            rows.map((j) => (
              <button
                className={j.id === detail?.id ? "selected" : ""}
                key={j.id}
                onClick={() => inspect(j.id)}
              >
                <strong>{j.title}</strong>
                <span className={"live-state " + j.status}>
                  {j.status.replaceAll("_", " ")}
                </span>
                <small>
                  {j.filename} · {j.original_bytes.toLocaleString()} original
                  bytes
                </small>
                <small>
                  Version {j.version} · attempt {j.attempts}/3
                </small>
              </button>
            ))
          ) : (
            <div className="ops-empty">
              <FileUp size={30} />
              <h3>No intake jobs in this view</h3>
              <p>
                Searchable PDF and DOCX work without OCR. Images and scanned
                pages need an enabled OCR engine and language data.
              </p>
            </div>
          )}
        </section>
        <article className="live-detail">
          {detail ? (
            <>
              <header>
                <div>
                  <small>PRIVATE INTAKE RECORD</small>
                  <h3>{detail.title}</h3>
                </div>
                <span className={"live-state " + detail.status}>
                  {detail.status.replaceAll("_", " ")}
                </span>
              </header>
              <p>
                {detail.filename} · {detail.language} · version {detail.version}
              </p>
              <code className="live-hash">
                Original SHA-256 {detail.original_sha256}
              </code>
              {detail.error_code && (
                <div className="ops-alert">
                  <strong>{detail.error_code}</strong>
                  <p>
                    {errorText[detail.error_code] ||
                      "Extraction could not complete. Review the source and worker configuration before retrying."}
                  </p>
                </div>
              )}
              {detail.extraction?.method && (
                <p>
                  Method: {detail.extraction.method} · pages:{" "}
                  {detail.extraction.pages ?? "not measured"} · OCR pages:{" "}
                  {detail.extraction.ocr_pages || 0}
                </p>
              )}
              {detail.status === "processing" && (
                <p role="status">
                  The worker is extracting this file in a bounded process.
                  Cancellation stops publication; the parser may take until its
                  timeout to exit.
                </p>
              )}
              {detail.status === "awaiting_review" && (
                <>
                  <p>
                    <ShieldCheck size={17} /> Compare this text with the
                    original source before publishing. OCR and mixed-layout
                    extraction can contain errors. Shared reader roles:{" "}
                    {detail.allowed_roles.join(", ") || "author/admin only"}.
                  </p>
                  <pre className="live-document">{detail.extracted_text}</pre>
                  <p>
                    Review deadline:{" "}
                    {new Date(detail.expires * 1000).toLocaleString()}
                  </p>
                </>
              )}
              <div className="live-actions">
                {canOperate && detail.status === "awaiting_review" && (
                  <button
                    className="btn btn-primary"
                    onClick={() => open("publish")}
                  >
                    Review and publish
                  </button>
                )}
                {canOperate && detail.can_retry && (
                  <button
                    className="btn btn-outline"
                    onClick={() => open("retry")}
                  >
                    Retry extraction
                  </button>
                )}
                {canOperate &&
                  [
                    "queued",
                    "processing",
                    "awaiting_review",
                    "failed",
                  ].includes(detail.status) && (
                    <button
                      className="btn btn-outline"
                      onClick={() => open("cancel")}
                    >
                      Cancel intake
                    </button>
                  )}
                {canOperate &&
                  ["indexed", "failed", "cancelled", "expired"].includes(
                    detail.status,
                  ) && (
                    <button
                      className="btn btn-outline"
                      onClick={() => open("archive")}
                    >
                      Archive intake record
                    </button>
                  )}
                {detail.document_id && (
                  <button
                    className="btn btn-outline"
                    onClick={() => onPublished(detail.document_id)}
                  >
                    Inspect published source
                    <ArrowRight size={16} />
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="ops-empty">
              <h3>A review boundary before search</h3>
              <p>
                Choose an intake to inspect its status, extraction evidence and
                publication controls. This queue does not execute source
                instructions or generate model answers.
              </p>
            </div>
          )}
        </article>
      </div>
      <footer className="ops-pagination">
        <span>Page {Math.floor(offset / 20) + 1}</span>
        <button
          className="btn btn-outline"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 20))}
        >
          Previous intake jobs
        </button>
        <button
          className="btn btn-outline"
          disabled={next === null}
          onClick={() => setOffset(next!)}
        >
          Next intake jobs
        </button>
      </footer>
      {uploading && (
        <Modal title="Queue a document for extraction" onClose={close}>
          <form onSubmit={create}>
            <p>
              Original bytes are stored privately while awaiting
              processing/review. Pending buffers expire after 24 hours and are
              cleared by a running worker. Publication requires a separate
              review. Use approved data.
            </p>
            <label>
              Source file
              <input
                type="file"
                accept=".pdf,.docx,.png,.jpg,.jpeg"
                onChange={(e) => choose(e.target.files?.[0])}
              />
            </label>
            <label>
              Source title
              <input
                required
                minLength={2}
                maxLength={120}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              Source language
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option>English</option>
                <option>Arabic</option>
                <option>Bilingual</option>
              </select>
            </label>
            <label>
              Extraction mode
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="auto">
                  Extract text; OCR blank PDF pages if enabled
                </option>
                <option value="ocr">Force OCR for PDF/image</option>
              </select>
            </label>
            <p>
              Mixed PDFs with sparse searchable text may need Force OCR. Arabic
              OCR requires ara language data and operator configuration; no
              fallback to English is used.
            </p>
            <fieldset className="live-role-options">
              <legend>Reader roles after publication</legend>
              {["engineer", "approver", "auditor"].map((role) => (
                <label key={role}>
                  <input
                    type="checkbox"
                    checked={roles.includes(role)}
                    onChange={(e) =>
                      setRoles(
                        e.target.checked
                          ? [...roles, role]
                          : roles.filter((r) => r !== role),
                      )
                    }
                  />
                  {role}
                </label>
              ))}
              <p>
                The source author and owner/security administrators retain
                access.
              </p>
            </fieldset>
            <p>
              {filename || "No file selected"} · PDF/DOCX/PNG/JPEG up to 1 MiB.
            </p>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <footer>
              <button className="btn btn-primary" disabled={busy || !content}>
                {busy ? "Queuing…" : "Queue for private extraction"}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {target && (
        <Modal
          title={
            command === "publish"
              ? "Review and publish extracted evidence"
              : command.charAt(0).toUpperCase() + command.slice(1) + " intake"
          }
          onClose={() => {
            if (!busy) setTarget(null);
          }}
        >
          <form onSubmit={act}>
            <p>
              {target.title} · pinned version {target.version}
            </p>
            <p>
              {command === "publish"
                ? "Publishing indexes the extracted text with the declared reader grants. The original upload bytes are removed from active intake storage."
                : command === "archive"
                  ? "Archiving removes pending file/text buffers and hides the job from the list. Published sources and audit receipts are preserved."
                  : "Cancellation prevents publication of late extraction results. Retry is explicit, bounded to three attempts and keeps the original file intent."}
            </p>
            {command === "publish" && (
              <label className="intake-attestation">
                <input
                  type="checkbox"
                  required
                  checked={reviewed}
                  onChange={(e) => setReviewed(e.target.checked)}
                />
                I compared the extracted text with the source and reviewed its
                reader access.
              </label>
            )}
            <label>
              Review / control note
              <textarea
                required
                minLength={5}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <footer>
              <button
                className="btn btn-primary"
                disabled={busy || (command === "publish" && !reviewed)}
              >
                Confirm {command}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {discard && (
        <Modal
          title="Discard the selected intake draft?"
          onClose={() => setDiscard(false)}
        >
          <p>
            The selected file is held only in this form until submission. Any
            pending submitted intent keeps its separate recovery key.
          </p>
          <footer>
            <button
              className="btn btn-outline"
              onClick={() => setDiscard(false)}
            >
              Keep editing
            </button>
            <button
              className="btn btn-primary"
              onClick={() => {
                setDiscard(false);
                setUploading(false);
                setContent("");
                afterLeave.current();
              }}
            >
              Discard draft
            </button>
          </footer>
        </Modal>
      )}
    </section>
  );
}
