"""Run separately: python -m nexus.worker. A durable action row is the MVP outbox."""
import time
from sqlalchemy import select, update
from .db import Action, Agent, Grant, Approval, now
from .config import Settings
from .db import database
from .mock_connector import UncertainOutcome
from .business_connector import business_connector, connector_identity
from .service import active_policy, canonical, audit, verify
from .security import digest
from .durable import run_flow_once
from .ingestion import run_ingestion_once


def run_once(factory, settings, connector):
    # Recover an expired dispatched lease conservatively; never replay blindly.
    with factory.begin() as db:
        expired = db.scalars(select(Action).where(Action.status == 'executing', Action.lease_until < now())).all()
        for row in expired:
            row.status = 'outcome_unknown'; row.updated = now()
            audit(db, row.org_id, 'worker', 'execution.lease_expired', row)
    with factory.begin() as db:
        candidate = db.scalar(select(Action).where(Action.status == 'queued').order_by(Action.created).limit(1))
        if not candidate: return False
        claimed = db.execute(update(Action).where(Action.id == candidate.id, Action.status == 'queued').values(
            status='executing', lease_until=now() + 60, attempts=Action.attempts + 1, updated=now()))
        if claimed.rowcount != 1: return False
        db.refresh(candidate)
        agent = db.scalar(select(Agent).where(Agent.id == candidate.agent_id).with_for_update())
        policy = active_policy(db, candidate.org_id)
        grant = db.scalar(select(Grant).where(Grant.org_id == candidate.org_id, Grant.env == candidate.env,
                     Grant.agent_id == candidate.agent_id, Grant.tool_id == candidate.tool_id,
                     Grant.scope == candidate.envelope['action']))
        approval = db.scalar(select(Approval).where(Approval.action_id == candidate.id))
        valid = (agent and agent.status == 'active' and agent.generation == candidate.generation and grant and
                 policy.version == candidate.policy_version and candidate.envelope.get('destination')==connector_identity(settings) and digest(canonical(candidate.envelope)) == candidate.payload_hash)
        if candidate.decision == 'require_approval':
            valid = valid and approval and approval.status == 'approved' and approval.expires > now() and approval.payload_hash == candidate.payload_hash
        if not valid:
            candidate.status = 'blocked'; candidate.reason = 'DISPATCH_AUTHORIZATION_CHANGED'
            audit(db, candidate.org_id, 'worker', 'execution.blocked', candidate)
            return True
        action_id, envelope, org = candidate.id, candidate.envelope, candidate.org_id
        audit(db, org, 'worker', 'execution.started', candidate, {'attempt': candidate.attempts})
        # Commit establishes the documented dispatch cutoff. Later revocation cannot undo this external call.
    try:
        result = connector.invoke(action_id, envelope, envelope.get('simulation', 'normal'))
        status = 'verified' if verify(envelope, result) else 'failed'
    except UncertainOutcome:
        result, status = {}, 'outcome_unknown'
    except ValueError:
        result, status = {}, 'failed'
    except Exception:
        # Unknown connector failures may have side effects. Avoid false failure/automatic replay.
        result, status = {}, 'outcome_unknown'
    with factory.begin() as db:
        action = db.get(Action, action_id)
        action.status = status; action.updated = now(); action.external_ref = result.get('external_ref')
        action.verification = {'matched': status == 'verified', 'result': result}
        audit(db, org, 'worker', 'execution.' + status, action, {'external_ref': action.external_ref})
    return True


def main():
    settings = Settings.from_env(); settings.validate()
    _, factory = database(settings.database_url); connector = business_connector(settings)
    print('NEXUS execution worker started. Waiting for authorized queued actions; keep this terminal open.', flush=True)
    while True:
        try:
            did_action=run_once(factory, settings, connector)
            did_run=run_flow_once(factory,settings)
            did_intake=run_ingestion_once(factory,settings) if settings.ingestion_in_action_worker else False
            if not did_action and not did_run and not did_intake: time.sleep(1)
        except KeyboardInterrupt:
            print('NEXUS execution worker stopped.', flush=True)
            break
        except Exception:
            # No sensitive payloads or secrets in operational errors. DB failures leave work persisted.
            print('Worker control unavailable; protected dispatch paused.', flush=True); time.sleep(3)


if __name__ == '__main__': main()
