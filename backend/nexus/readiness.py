"""Source-defined delivery states plus scoped, versioned operator acceptance evidence."""
from urllib.parse import urlsplit
from typing import Literal
from fastapi import Request
from pydantic import Field, field_validator
from sqlalchemy import select, update
from .schemas import Strict
from .db import ReadinessEvidence, now, public
from .service import audit
from .security import fail
from .runtime_context import runtime_environment

# These are this project's workstreams, not a universal production checklist.
GATES = [
 ('customer_connectors','Customer business connectors','Engineering','partial','HTTP adapter, governed supplier checks, receipt recovery, approval-bound dispatch, unsigned evidence downloads, synthetic drills and a separate developer reference gateway with scoped durable receipts are implemented. Real customer mapping, sandbox purchase/idempotency/isolation acceptance and deployment evidence remain.','connectors'),
 ('durable_agents','Durable agent execution','Engineering','partial','Bounded pause/resume, approvals, cancellation, one-time scheduled starts, verified-supplier allowlist conditions, lease recovery, unsigned scoped run-evidence snapshots and a disposable synthetic agent-workflow drill are implemented. Autonomous planning, customer-workflow and deployment acceptance remain.','agentRuns'),
 ('document_ingestion','Document ingestion & OCR','Knowledge','partial','Authorized intake, local parsers, reviewed publication, OCR controls, deletion propagation and a disposable DOCX/PDF ingestion drill are implemented. OCR quality, broader file compatibility and deployment acceptance remain.','documents'),
 ('semantic_retrieval','Semantic retrieval & reranking','Knowledge','partial','ACL-first LSA/BM25, document diversity, disabled-by-default local neural ranking and scoped stored-vector build/query APIs with dashboard controls, durable receipts, invalidation, bounded multi-index search, checkpointed background builds, bounded larger-corpus collections and optional local model passage reranking are implemented. Larger-scale indexing and representative model/bilingual/reranking acceptance remain.','knowledge'),
 ('document_permissions','Document-level permissions','Knowledge','partial','Source ACL enforcement across retrieval, indexing and deletion, plus read-only exact indexed-text copy review with visibility-filtered counts. Source ACL federation and representative deployment acceptance remain.','documents'),
 ('answer_evaluation','Bilingual answer evaluation','Knowledge','partial','Reviewer-labelled keyword and saved indexed-search metrics, precision targets, saved-run and same-query indexed-review comparisons, synthetic retrieval checks and a disposable English/Arabic answer-control exercise with optional installed local Ollama are implemented. Independent generated-answer quality, grounding, refusal, broader poisoning and representative pilot acceptance remain.','evaluationlab'),
 ('provider_resilience','Provider resilience','Runtime','partial','Bounded response validation, elapsed-time completion checks, uncertain-outcome accounting and a disposable synthetic inference-control drill are implemented. Model-specific failure behavior, streaming/fallback if required, and live provider acceptance remain.','models'),
 ('traffic_controls','Inference traffic controls','Runtime','implemented','Shared-database admission limits, concurrency reservations and saturation behavior.','models'),
 ('usage_governance','Usage & cost governance','Runtime','partial','Owner-entered selected-call statement comparison, saved discrepancy records, stale-ledger detection and owner-managed model-route admission ceilings are implemented. Provider-verified invoice/account reconciliation, retention policies and provider-account aggregation remain.','usage'),
 ('identity_lifecycle','Identity & workload lifecycle','Governance','partial','IdP provisioning/offboarding, verified MFA and workload federation.','settings'),
 ('workspace_lifecycle','Workspace & environment lifecycle','Governance','partial','Local lifecycle, membership isolation and reviewed prompt/guardrail/workflow draft copying with pinned reference remapping and receipt recovery are implemented. Pilot lifecycle, general configuration promotion and deployment acceptance remain.','settings'),
 ('secrets_network','Secrets & network isolation','Governance','partial','Managed-secret injection, rotation and deployment-enforced egress isolation.','connectors'),
 ('telemetry_alerts','Telemetry, alerts & SLOs','Operations','partial','Environment-scoped owner threshold policies, manual database evaluations and versioned local receipts are implemented. Continuous monitoring, external logs/metrics/traces, notification delivery drills and service-objective acceptance remain.','observability'),
 ('audit_retention','Audit integrity & retention','Governance','partial','Unsigned supplier-check/workflow checksum exports and optional Ed25519 audit-metadata snapshots with independently trusted-key offline verification are implemented. Owner-managed explicit expired signed-snapshot payload retention, holds and preview-bound removal receipts are implemented. Signing-key trust/custody acceptance, immutable off-host archive, broader authenticated evidence, general retention rules and deployment acceptance remain.','audit'),
 ('recovery','Encrypted backup & recovery','Operations','partial','Quiesced snapshots, authenticated encrypted inspection, isolated SQLite recovery copies, disposable SQLite drills and a CI PostgreSQL recovery rehearsal are implemented. Scheduled encrypted backups, deployment application/PostgreSQL recovery acceptance and measured RPO/RTO remain.','operations'),
 ('cloud_delivery','Cloud deployment & rollback','Operations','partial','Reviewed images, TLS/private networking, staged rollout and recovery evidence.','operations'),
 ('security_load','Security & load acceptance','Validation','partial','Independent review, dependency/image scans, penetration and load/soak tests.','operations'),
 ('accessibility','Accessibility & device acceptance','Validation','partial','Readable text, keyboard/screen-reader checks and responsive device assessment.','operations'),
]


class EvidenceInput(Strict):
    outcome: Literal['not_tested','passed','failed']
    summary: str = Field(min_length=20, max_length=1000)
    reference: str = Field(default='', max_length=500)
    expected_version: int = Field(ge=0)

    @field_validator('summary')
    @classmethod
    def clean_summary(cls,value):
        value=value.strip()
        if len(value)<20:raise ValueError('Include the tested scope, environment and result.')
        return value

    @field_validator('reference')
    @classmethod
    def safe_reference(cls,value):
        if not value:return ''
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use a credential-free HTTPS evidence URL without query or fragment.')
        return value


def readiness(db, org_id, environment=None):
    environment=runtime_environment(db,org_id,environment)
    evidence={r.gate:r for r in db.scalars(select(ReadinessEvidence).where(ReadinessEvidence.org_id==org_id,ReadinessEvidence.env==environment)).all()}
    gates=[]
    for key,title,group,delivery,required,view in GATES:
        row=evidence.get(key)
        gates.append({'id':key,'title':title,'group':group,'delivery':delivery,'required_evidence':required,'view':view,'evidence':public(row) if row else None,'accepted_for_current_scope':bool(delivery=='implemented' and row and row.outcome=='passed')})
    return {'total_workstreams':len(gates),'implemented':sum(g['delivery']=='implemented' for g in gates),'partial':sum(g['delivery']=='partial' for g in gates),'not_implemented':sum(g['delivery']=='not_implemented' for g in gates),'accepted':sum(g['accepted_for_current_scope'] for g in gates),'production_ready':all(g['accepted_for_current_scope'] for g in gates),'gates':gates,'boundary':'Delivery states are defined by this source release. Evidence is an operator attestation, not independent verification or certification. A recorded pass cannot implement missing software.'}


def register_readiness(app,factory,settings,human):
    @app.get('/v1/production-readiness')
    def report(request:Request):
        with factory() as db:
            user=human(request,db)
            return readiness(db,user.org_id)

    @app.put('/v1/production-readiness/{gate}')
    def record(gate:str,body:EvidenceInput,request:Request):
        definition=next((g for g in GATES if g[0]==gate),None)
        if not definition:fail(404,'GATE_NOT_FOUND','Production workstream not found.')
        with factory.begin() as db:
            user=human(request,db,True,'policy')
            if definition[3]=='not_implemented' and body.outcome=='passed':fail(422,'CAPABILITY_MISSING','This source release does not implement this capability. Evidence cannot mark it as passed.')
            environment=runtime_environment(db,user.org_id)
            row=db.scalar(select(ReadinessEvidence).where(ReadinessEvidence.org_id==user.org_id,ReadinessEvidence.env==environment,ReadinessEvidence.gate==gate))
            if row:
                changed=db.execute(update(ReadinessEvidence).where(ReadinessEvidence.id==row.id,ReadinessEvidence.org_id==user.org_id,ReadinessEvidence.env==environment,ReadinessEvidence.version==body.expected_version).values(outcome=body.outcome,summary=body.summary,reference=body.reference,version=ReadinessEvidence.version+1,updated=now(),author_id=user.id))
                if changed.rowcount!=1:fail(409,'STALE_VERSION','Another reviewer changed the evidence. Refresh before recording.')
                db.refresh(row)
            else:
                if body.expected_version!=0:fail(409,'STALE_VERSION','Refresh the current evidence version.')
                row=ReadinessEvidence(org_id=user.org_id,env=environment,gate=gate,outcome=body.outcome,summary=body.summary,reference=body.reference,author_id=user.id);db.add(row);db.flush()
            audit(db,user.org_id,user.id,'readiness.evidence_recorded',detail={'gate':gate,'outcome':row.outcome,'version':row.version,'summary':body.summary,'reference':body.reference})
            return public(row)
