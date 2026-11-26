"""Bounded, allowlisted workflow snapshots; no worker or connector calls."""
import re
from datetime import datetime, timezone
from sqlalchemy import select
from . import __version__
from .db import DurableRun, DurableStep, Action, Approval, SchemaVersion
from .runtime_context import runtime_environment
from .security import digest, fail
from .service import canonical, verify
from .schemas import ActionInput, SupplierArguments, PurchaseArguments
from .check_evidence import require, timestamp

BOUNDARY = ('Unsigned recorded-state snapshot, not authenticated evidence or current server state. '
    'Workflow completion does not establish customer acceptance or production readiness. '
    'Pending and unknown actions remain unresolved. No action is dispatched, retried or reconciled by export. '
    'Names, labels, request arguments, review notes, credentials, raw results and audit history are excluded.')
RUN_STATES = frozenset(('queued','processing','waiting_action','waiting_review','paused','cancelling',
    'outcome_unknown','succeeded','cancelled','failed','rejected','expired'))
STEP_STATES = frozenset(('pending','waiting_action','waiting_review','outcome_unknown','completed',
    'cancelled','failed','rejected','expired','denied','verification_failed','blocked','changes_requested'))
ACTION_STATES = frozenset(('queued','awaiting_approval','executing','outcome_unknown','verified',
    'cancelled','denied','rejected','expired','failed','verification_failed','blocked','changes_requested'))


def build_evidence(rows, actor):
    try:
        run = rows[0][0]
        definitions = run.definition['steps']
        require(2 <= len(definitions) <= 12 and len(rows) == len(definitions))
        require(run.status in RUN_STATES and 0 <= run.cursor <= len(definitions) and run.version >= 1)
        require(digest(canonical(run.definition)) == run.payload_hash == run.request_digest)
        require(type(rows[0][4]) is int and rows[0][4] >= 1)
        destination = run.definition.get('destination','mock-business-v1')
        require(destination == 'mock-business-v1' or re.fullmatch(r'http-business-v1:[a-f0-9]{64}',destination))
        steps = []
        for position, (_, step, action, approval, schema) in enumerate(rows):
            definition = definitions[position]
            require(step is not None and step.position == position and step.kind == definition['kind'])
            require(step.label == definition['label'] and step.status in STEP_STATES)
            require(step.kind in ('checkpoint','approval','governed_action','output'))
            item = {'position':position,'kind':step.kind,'status':step.status,
                    'updated_at_utc':timestamp(step.updated),'action':None,'review':None}
            if step.action_id:
                require(step.kind == 'governed_action' and action is not None)
                envelope = action.envelope
                request = definition['request']
                body = ActionInput.model_validate(request)
                require(body.action in ('supplier:read','purchase:create'))
                arguments = (SupplierArguments if body.action == 'supplier:read' else PurchaseArguments).model_validate(body.arguments).model_dump()
                require(action.status in ACTION_STATES and digest(canonical(envelope)) == action.payload_hash)
                require(action.agent_id == run.agent_id and action.generation == run.generation)
                require(action.requester_id == run.author_id and action.principal == 'durable:'+run.author_id)
                require(action.idem_key == 'run-'+run.id+'-'+str(position))
                require(action.tool_id == definition['tool_id'])
                require(action.request_digest == digest(canonical({'agent':run.agent_id,'tool':action.tool_id,**body.model_dump()})))
                require(all(envelope[key] == value for key,value in {
                    'org_id':run.org_id,'env':run.env,'agent_id':run.agent_id,'tool_id':action.tool_id,
                    'action':request['action'],'resource':request['resource'],'arguments':arguments,
                    'tool_version':request['tool_version'],'policy_version':action.policy_version,
                    'destination':destination}.items()))
                verified = action.status == 'verified'
                if verified:
                    result = action.verification.get('result')
                    require(action.verification.get('matched') is True and verify(envelope,result))
                    require(action.external_ref == result['external_ref'])
                business_approval = None
                require(action.decision != 'require_approval' or approval is not None)
                if approval is not None:
                    require(approval.payload_hash == action.payload_hash and approval.policy_version == action.policy_version)
                    require(approval.requester_id == action.requester_id)
                    require(approval.status in ('pending','approved','rejected','expired','cancelled','changes_requested'))
                    if verified:
                        require(approval.status == 'approved' and approval.approver_id and approval.approver_id != run.author_id)
                    business_approval = {'status':approval.status,'version':approval.version}
                item['action'] = {'id':action.id,'status':action.status,'verified':verified,
                    'attempts':action.attempts,'policy_version':action.policy_version,
                    'payload_sha256':action.payload_hash,'approval':business_approval}
                # A completed step must be backed by its verified action, not a cached step result.
                require(step.status != 'completed' or verified)
            else:
                require(action is None and approval is None)
                require(step.kind != 'governed_action' or step.status != 'completed')
            if step.kind == 'approval' and step.status in ('completed','rejected'):
                result = step.result
                decision = 'approve' if step.status == 'completed' else 'reject'
                require(result['decision'] == decision and isinstance(result['reviewer_id'],str))
                require(result['reviewer_id'] and result['reviewer_id'] != run.author_id)
                item['review'] = {'decision':decision,'independent_reviewer_recorded':True}
            steps.append(item)
        if run.status == 'succeeded':require(all(step['status'] == 'completed' for step in steps))
        payload = {'format':'nexus-durable-run-evidence','format_version':1,
            'exported_at_utc':timestamp(datetime.now(timezone.utc).timestamp()),
            'source_release':__version__,'schema_version':rows[0][4],
            'scope':{'workspace_id':run.org_id,'account_id':actor.id,'environment':run.env},
            'run':{'id':run.id,'status':run.status,'version':run.version,'cursor':run.cursor,
                'definition_sha256':run.payload_hash,'recoveries':run.recoveries,
                'cancel_requested':bool(run.cancel_requested),'created_at_utc':timestamp(run.created),
                'updated_at_utc':timestamp(run.updated)},
            'connector':{'mode':'synthetic' if destination == 'mock-business-v1' else 'http',
                         'binding_source':'recorded_workflow'},
            'steps':steps,'boundary':BOUNDARY}
    except (KeyError, TypeError, ValueError, OverflowError, OSError, AttributeError):
        fail(409,'RUN_EVIDENCE_INCONSISTENT','Recorded workflow evidence is inconsistent; inspect the run and execution ledger.')
    return {'payload':payload,'integrity':{'algorithm':'sha256','canonicalization':'sorted-ascii-json-v1',
        'digest':digest(canonical(payload)),'authenticated_signature':False}}


def register_run_evidence(app, factory, human):
    from fastapi import Request

    @app.get('/v1/agent-runs/{id}/evidence')
    def export(id:str, request:Request):
        from fastapi.responses import JSONResponse
        with factory() as db:
            actor = human(request,db,False,'export')
            environment = runtime_environment(db,actor.org_id)
            # A single SELECT captures the run, steps, linked actions and approvals
            # in one statement snapshot on both SQLite and PostgreSQL.
            schema = select(SchemaVersion.version).order_by(SchemaVersion.version.desc()).limit(1).scalar_subquery()
            rows = db.execute(select(DurableRun,DurableStep,Action,Approval,schema).outerjoin(DurableStep,
                (DurableStep.run_id == DurableRun.id)&(DurableStep.org_id == DurableRun.org_id)&(DurableStep.env == DurableRun.env))
                .outerjoin(Action,(Action.id == DurableStep.action_id)&(Action.org_id == DurableRun.org_id)&(Action.env == DurableRun.env))
                .outerjoin(Approval,(Approval.action_id == Action.id)&(Approval.org_id == DurableRun.org_id)&(Approval.env == DurableRun.env))
                .where(DurableRun.id == id,DurableRun.org_id == actor.org_id,DurableRun.env == environment)
                .order_by(DurableStep.position).limit(13)).all()
            if not rows:fail(404,'RUN_NOT_FOUND','Agent run not found in this workspace.')
            if len(rows)>12:fail(422,'RUN_EVIDENCE_CAPACITY','This report supports up to 12 persisted workflow steps.')
            return JSONResponse(build_evidence(rows,actor),headers={'Cache-Control':'no-store'})
