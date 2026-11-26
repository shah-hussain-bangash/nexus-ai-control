import { ArrowUpRight, ShieldCheck } from "lucide-react";
import "./productionStatus.css";

const available = [
  ["Local AI inference", "Run the configured local Ollama model through the governed model gateway.", "models"],
  ["Document library", "Upload, index and search authorized documents with versioned source records.", "documents"],
  ["Document-backed answers", "Include authorized excerpts in model requests and inspect source citations.", "models"],
  ["Access controls", "Manage local members, roles, sessions and environment access.", "settings"],
  ["Governed execution", "Use policy checks, human approvals and durable execution records.", "agentRuns"],
  ["Audit and usage records", "Inspect recorded activity and usage. Immutable archives and invoice reconciliation remain open.", "audit"],
  ["Synthetic recovery exercises", "Inspect readiness and recovery evidence from disposable synthetic tests.", "operations"],
];

const remaining = [
  ["Customer integrations", "Connect an approved real business system and validate purchasing, idempotency, tenant isolation and recovery. Current exercises use synthetic systems."],
  ["Autonomous agents", "Implement model-driven planning and validate real customer workflows."],
  ["Document ingestion & OCR", "Assess OCR quality, expand file compatibility and complete deployment acceptance."],
  ["Advanced retrieval", "Add neural embeddings, vector indexing, scalable retrieval and reranking, then validate broader bilingual relevance."],
  ["Answer quality", "Evaluate representative English and Arabic accuracy, grounding, citation correctness, unsupported-question refusals and malicious-document handling."],
  ["Provider resilience", "Validate model-specific failure behavior and add streaming or fallback where required."],
  ["Cost governance", "Validate hosted-provider invoice reconciliation, account-level spending controls and evidence retention."],
  ["Identity lifecycle", "Verify MFA, automated user provisioning and offboarding, and workload federation."],
  ["Workspace lifecycle", "Implement general configuration promotion and accept pilot environment and membership lifecycle operations."],
  ["Secrets & network security", "Complete managed-secret injection and rotation, reviewed HTTPS and private networking, and deployment-enforced outbound restrictions."],
  ["Monitoring & alerts", "Connect continuous external metrics, logs and traces, service objectives and notifications, then verify alert delivery."],
  ["Audit protection", "Add authenticated evidence, immutable off-host storage and enforced retention."],
  ["Backup operations", "Configure scheduled encrypted backups, protected key custody and retention. Accept deployment recovery and measure recovery-time and recovery-point objectives. Current scope is synthetic recovery only."],
  ["Deployment & rollback", "Review deployment images, validate staged rollout and rollback, and record deployment-specific recovery evidence."],
  ["Independent validation", "Complete independent security review, dependency and image scans, penetration testing, load and soak tests, and accessibility and device assessment."],
  ["Release operations", "Approve operating procedures, support ownership, representative workflow acceptance and named operator sign-off."],
];

export function ProductionStatus({ onNavigate }: { onNavigate: (view: string) => void }) {
  return (
    <section className="production-status" aria-labelledby="production-status-heading">
      <div className="production-status-heading">
        <div>
          <span className="production-status-label"><ShieldCheck size={16} aria-hidden="true" /> CURRENT PROJECT STATUS</span>
          <h2 id="production-status-heading">Capabilities &amp; production readiness</h2>
          <p>Local pilot · Production validation pending</p>
        </div>
        <button className="btn btn-outline" onClick={() => onNavigate("operations")}>
          View release readiness <ArrowUpRight size={16} aria-hidden="true" />
        </button>
      </div>
      <p className="production-status-baseline">
        Working locally: AI inference, document citations, access controls and synthetic recovery exercises.
        These checks demonstrate tested capabilities; they do not establish production readiness.
      </p>
      <h3>Working local capabilities</h3>
      <ul className="production-status-available">
        {available.map(([title, description, view]) => (
          <li key={title}>
            <strong>{title}</strong>
            <span className="production-status-pending production-status-working">Working locally</span>
            <p>{description}</p>
            <button className="btn btn-outline" aria-label={`Open ${title}`} onClick={() => onNavigate(view)}>
              Open workspace <ArrowUpRight size={14} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <h3>{remaining.length} capabilities and acceptance gaps</h3>
      <p>Some capabilities are partially implemented. The items below describe the remaining implementation or acceptance work before production.</p>
      <ol className="production-status-work">
        {remaining.map(([title, description]) => (
          <li key={title}><strong>{title}</strong><span className="production-status-pending">Work remaining</span><p>{description}</p></li>
        ))}
      </ol>
      <div className="production-status-followup">
        <h3>Windows shutdown verification</h3>
        <p>The Windows Ctrl+C fix is integrated and passed native API and worker shutdown tests. Terminal closure, power loss and interrupted external writes still require separate acceptance.</p>
        <h3>Integrated updates</h3>
        <ul>
          <li>Required-document matching — <a href="https://github.com/shah-hussain-bangash/nexus-ai-control/pull/70" target="_blank" rel="noreferrer">Merged PR #70</a></li>
          <li>Local-pilot checks, citation improvements and Windows Ctrl+C fix — <a href="https://github.com/shah-hussain-bangash/nexus-ai-control/pull/71" target="_blank" rel="noreferrer">Merged PR #71</a></li>
        </ul>
        <p>These updates are included in the current source. Passing their checks does not grant production acceptance.</p>
      </div>
      <p className="production-status-note">Project-level summary. Use the release readiness board for environment-specific evidence and recorded acceptance.</p>
    </section>
  );
}
