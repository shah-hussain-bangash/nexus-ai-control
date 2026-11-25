import { ArrowUpRight, ShieldCheck } from "lucide-react";
import "./productionStatus.css";

const remaining = [
  ["Customer acceptance", "Validate approved customer workflows, including failure and recovery."],
  ["Answer quality", "Evaluate English and Arabic accuracy, grounding, refusals and malicious documents."],
  ["Deployment security", "Verify HTTPS, managed secrets, identity controls and network restrictions."],
  ["Operations & recovery", "Connect monitoring and alerts; schedule backups and measure deployment restore times."],
  ["Independent validation", "Complete security review, dependency and image scans, load testing and accessibility checks."],
  ["Release acceptance", "Approve operating procedures, rollback, support ownership and release sign-off."],
];

export function ProductionStatus({ onNavigate }: { onNavigate: (view: string) => void }) {
  return (
    <section className="production-status" aria-labelledby="production-status-heading">
      <div className="production-status-heading">
        <div>
          <span className="production-status-label"><ShieldCheck size={16} aria-hidden="true" /> CURRENT PROJECT STATUS</span>
          <h2 id="production-status-heading">Production validation pending</h2>
          <p>NEXUS AI Control is an operational development platform undergoing production validation.</p>
        </div>
        <button className="btn btn-outline" onClick={() => onNavigate("operations")}>
          View release readiness <ArrowUpRight size={16} aria-hidden="true" />
        </button>
      </div>
      <p className="production-status-baseline">
        Working locally: AI inference, document citations, access controls and synthetic recovery exercises.
        These checks demonstrate tested capabilities; they do not establish production readiness.
      </p>
      <h3>6 remaining work areas</h3>
      <p>Complete and record acceptance for these areas before a production release.</p>
      <ol className="production-status-work">
        {remaining.map(([title, description]) => (
          <li key={title}><strong>{title}</strong><span className="production-status-pending">Pending</span><p>{description}</p></li>
        ))}
      </ol>
      <p className="production-status-note">Project-level summary. Use the release readiness board for environment-specific evidence and recorded acceptance.</p>
    </section>
  );
}
