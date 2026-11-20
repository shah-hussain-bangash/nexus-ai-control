"""Persistent bounded workflows. Business effects use the existing governed outbox only."""
from typing import Literal
from fastapi import Request,Header,HTTPException,Query
from pydantic import Field,model_validator,field_validator
from sqlalchemy import select,update,func,and_,or_
from .schemas import Strict,ActionInput
from .db import DurableRun,DurableStep,Organization,Agent,Tool,Action,Approval,User,now,uid,public
from .security import fail,digest,PERMISSIONS
from .runtime_context import environment_user_allowed,runtime_environment
from .business_connector import connector_identity
from .service import scoped,submit_action,audit,canonical

ACTIVE=('queued','processing','waiting_action','waiting_review','paused','cancelling','outcome_unknown')
POLL=('queued','waiting_action','cancelling','outcome_unknown')

class StepInput(Strict):
    kind: Literal['checkpoint','approval','governed_action','output']
    label: str = Field(min_length=2,max_length=100)
    tool_id: str = Field(default='',max_length=64)
    request: ActionInput | None = None

    @field_validator('label')
    @classmethod
    def visible_label(cls,value):
        if len(value.strip())<2:raise ValueError('Use a visible checkpoint label.')
        return value.strip()

    @model_validator(mode='after')
    def action_fields(self):
        if self.kind=='governed_action' and (not self.tool_id or self.request is None):raise ValueError('A governed action requires its tool and immutable request.')
        if self.kind!='governed_action' and (self.tool_id or self.request is not None):raise ValueError('Only action steps accept tool requests.')
        return self

class RunInput(Strict):
    name: str = Field(min_length=2,max_length=120)
    agent_id: str = Field(min_length=1,max_length=64)
    steps: list[StepInput] = Field(min_length=2,max_length=12)

    @model_validator(mode='after')
    def boundaries(self):
        if not self.name.strip() or self.steps[0].kind!='checkpoint' or self.steps[-1].kind!='output':raise ValueError('A run starts at a checkpoint and finishes with an output step.')
        return self

class Control(Strict):
    expected_version: int = Field(ge=1)
    command: Literal['pause','resume','cancel','retry']
    note: str = Field(min_length=5,max_length=500)

    @field_validator('note')
    @classmethod
    def visible_note(cls,value):
        if len(value.strip())<5:raise ValueError('Include a visible review note.')
        return value.strip()

class Review(Strict):
    expected_version: int = Field(ge=1)
    decision: Literal['approve','reject']
    note: str = Field(min_length=5,max_length=500)

    @field_validator('note')
    @classmethod
    def visible_note(cls,value):
        if len(value.strip())<5:raise ValueError('Include a visible decision note.')
        return value.strip()

class Recover(Strict):
    key: str = Field(min_length=8,max_length=128)

def run_for(db,id,org,lock=False):
    query=select(DurableRun).where(DurableRun.id==id,DurableRun.org_id==org,DurableRun.env==runtime_environment(db,org))
    row=db.scalar(query.with_for_update() if lock else query)
    if not row:fail(404,'RUN_NOT_FOUND','Agent run not found in this workspace.')
    return row

def step_for(db,run):
    runtime_environment(db,run.org_id,run.env)
    return db.scalar(select(DurableStep).where(DurableStep.run_id==run.id,DurableStep.org_id==run.org_id,DurableStep.env==run.env,DurableStep.position==run.cursor))

def event(db,run,actor,name,detail=None):
    audit(db,run.org_id,actor,'agent_run.'+name,detail={'run_id':run.id,'cursor':run.cursor,'version':run.version,**(detail or {})},env=run.env)

def touch(run,status):
    run.status=status;run.version+=1;run.updated=now();run.lease_token='';run.lease_until=0;run.next_poll=now()+1


def recover_expired_claim(db,run):
    run.recoveries+=1;touch(run,'queued' if run.recoveries<=3 else 'failed')
    run.error='WORKER_LEASE_EXPIRED';event(db,run,'worker','lease_recovered')

def serialize(db,run):
    runtime_environment(db,run.org_id,run.env)
    data=public(run);data.pop('lease_token',None)
    steps=db.scalars(select(DurableStep).where(DurableStep.run_id==run.id,DurableStep.org_id==run.org_id,DurableStep.env==run.env).order_by(DurableStep.position)).all()
    data['steps']=[public(s) for s in steps]
    current=next((s for s in steps if s.position==run.cursor),None)
    data['can_retry']=bool(run.status=='failed' and current and not current.action_id)
    data['boundary']='Persistent bounded execution with a pinned business destination. Autonomous model planning and arbitrary customer protocol mapping remain outside this engine.'
    return data

def create_run(db,settings,user,body,key):
    if not key or not 8<=len(key)<=128:fail(422,'IDEMPOTENCY_KEY_REQUIRED','Use an 8–128 character idempotency key.')
    # Serialize organization admission before the idempotency and quota reads.
    db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
    request={**body.model_dump(),'destination':connector_identity(settings)};hashed=digest(canonical(request))
    existing=db.scalar(select(DurableRun).where(DurableRun.org_id==user.org_id,DurableRun.env==runtime_environment(db,user.org_id),DurableRun.author_id==user.id,DurableRun.idem_key==key))
    if existing:
        if existing.request_digest!=hashed:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another immutable workflow request.')
        return existing
    if db.scalar(select(func.count()).select_from(DurableRun).where(DurableRun.org_id==user.org_id,DurableRun.env==runtime_environment(db,user.org_id),DurableRun.status.in_(ACTIVE)))>=50:fail(429,'RUN_CAPACITY','This workspace already has 50 active runs.')
    agent=scoped(db,Agent,body.agent_id,user.org_id)
    if agent.status!='active':fail(403,'AGENT_INACTIVE','Choose an active agent.')
    for step in body.steps:
        if step.kind=='governed_action':
            tool=scoped(db,Tool,step.tool_id,user.org_id)
            if tool.kind not in ('supplier','purchase') or tool.version!=step.request.tool_version:fail(422,'UNSUPPORTED_RUN_TOOL','Only the versioned governed supplier/purchase tools are supported by this bounded engine.')
            if settings.mode!='local' and step.request.simulation!='normal':fail(403,'SIMULATION_DISABLED','Fault injection is local-only.')
    run=DurableRun(org_id=user.org_id,env=runtime_environment(db,user.org_id),name=body.name.strip(),agent_id=agent.id,generation=agent.generation,author_id=user.id,definition=request,payload_hash=hashed,request_digest=hashed,idem_key=key)
    db.add(run);db.flush()
    for i,step in enumerate(body.steps):db.add(DurableStep(org_id=user.org_id,env=run.env,run_id=run.id,position=i,label=step.label,kind=step.kind))
    db.flush();event(db,run,user.id,'created');return run

def finish_cancel(db,run):
    runtime_environment(db,run.org_id,run.env)
    db.execute(update(DurableStep).where(DurableStep.run_id==run.id,DurableStep.org_id==run.org_id,DurableStep.env==run.env,DurableStep.position>=run.cursor,DurableStep.status.in_(('pending','waiting_review'))).values(status='cancelled',updated=now()))
    touch(run,'cancelled')

def cancel_current(db,run):
    step=step_for(db,run)
    action=db.scalar(select(Action).where(Action.id==step.action_id,Action.org_id==run.org_id,Action.env==run.env).with_for_update()) if step and step.action_id else None
    if step and step.action_id and not action:fail(409,'ACTION_MISSING','The linked action is unavailable.')
    run.cancel_requested=1
    if action and action.status in ('queued','awaiting_approval'):
        changed=db.execute(update(Action).where(Action.id==action.id,Action.org_id==run.org_id,Action.env==run.env,Action.status.in_(('queued','awaiting_approval'))).values(status='cancelled',updated=now()))
        if changed.rowcount:
            db.execute(update(Approval).where(Approval.action_id==action.id,Approval.org_id==run.org_id,Approval.env==run.env,Approval.status=='pending').values(status='cancelled',version=Approval.version+1))
            if step:step.status='cancelled'
            finish_cancel(db,run);return
        db.refresh(action)
    if action and action.status in ('executing','outcome_unknown'):
        touch(run,'outcome_unknown' if action.status=='outcome_unknown' else 'cancelling');return
    if action and step:
        step.result={'action_id':action.id,'status':action.status,'external_ref':action.external_ref,'verification':action.verification}
        step.status='completed' if action.status=='verified' else action.status;step.updated=now()
        if action.status=='verified':run.cursor+=1
    if step and step.status=='pending':step.status='cancelled'
    finish_cancel(db,run)

def register_durable(app,factory,settings,human):
    @app.get('/v1/agent-runs')
    def listing(request:Request,offset:int=Query(0,ge=0,le=10000),limit:int=Query(20,ge=1,le=50)):
        with factory() as db:
            user=human(request,db)
            rows=db.scalars(select(DurableRun).where(DurableRun.org_id==user.org_id,DurableRun.env==runtime_environment(db,user.org_id)).order_by(DurableRun.created.desc(),DurableRun.id).offset(offset).limit(limit+1)).all()
            return {'items':[serialize(db,r) for r in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}

    @app.post('/v1/agent-runs',status_code=201)
    def create(body:RunInput,request:Request,idempotency_key:str=Header(default='',alias='Idempotency-Key')):
        with factory.begin() as db:
            user=human(request,db,True,'operate');run=create_run(db,settings,user,body,idempotency_key)
            return serialize(db,run)

    @app.post('/v1/agent-runs/recover')
    def recover(body:Recover,request:Request):
        with factory() as db:
            user=human(request,db,True)
            run=db.scalar(select(DurableRun).where(DurableRun.org_id==user.org_id,DurableRun.env==runtime_environment(db,user.org_id),DurableRun.author_id==user.id,DurableRun.idem_key==body.key))
            if not run:fail(404,'RUN_INTENT_NOT_FOUND','No committed run is visible for this intent. Retry the unchanged request with the same key; do not submit a different intent blindly.')
            return serialize(db,run)

    @app.get('/v1/agent-runs/{id}')
    def detail(id:str,request:Request):
        with factory() as db:
            user=human(request,db);return serialize(db,run_for(db,id,user.org_id))

    @app.post('/v1/agent-runs/{id}/control')
    def control(id:str,body:Control,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'operate');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));run=run_for(db,id,user.org_id,True)
            if run.version!=body.expected_version:fail(409,'STALE_VERSION','The worker or another operator changed this run. Refresh before acting.')
            if body.command=='pause':
                if run.status not in ('queued','processing','waiting_action','waiting_review'):fail(409,'RUN_STATE','This run cannot be paused in its current state.')
                run.resume_state='queued' if run.status=='processing' else run.status;touch(run,'paused')
            elif body.command=='resume':
                if run.status!='paused':fail(409,'RUN_STATE','Only a paused run can resume.')
                if run.resume_state=='waiting_review' and run.review_until<=now():fail(409,'REVIEW_EXPIRED','The independent review expired. Create a new run.')
                touch(run,run.resume_state)
            elif body.command=='retry':
                step=step_for(db,run)
                if run.status!='failed' or not step or step.action_id:fail(409,'UNSAFE_RETRY','A submitted business action cannot be replayed by this control. Reconcile it or submit a new reviewed intent.')
                run.error='';step.status='pending';touch(run,'queued')
            else:
                if run.status not in ACTIVE:fail(409,'RUN_STATE','This run is already terminal.')
                cancel_current(db,run)
            event(db,run,user.id,body.command,{'note':body.note.strip()});db.flush();return serialize(db,run)

    @app.post('/v1/agent-runs/{id}/decision')
    def decision(id:str,body:Review,request:Request):
        with factory.begin() as db:
            user=human(request,db,True,'approve');db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name));run=run_for(db,id,user.org_id,True)
            if run.author_id==user.id:fail(403,'SELF_APPROVAL','An independent authorized reviewer must decide this checkpoint.')
            if run.version!=body.expected_version or run.status!='waiting_review':fail(409,'STALE_VERSION','This review is no longer pending at that version.')
            if run.review_until<=now():fail(409,'REVIEW_EXPIRED','This checkpoint review expired. Create a new run.')
            if digest(canonical(run.definition))!=run.payload_hash:fail(409,'PAYLOAD_CHANGED','The workflow fingerprint changed.')
            step=step_for(db,run)
            if not step or step.kind!='approval':fail(409,'RUN_STATE','No independent review checkpoint is active.')
            step.result={'reviewer_id':user.id,'decision':body.decision,'note':body.note.strip()};step.status='completed' if body.decision=='approve' else 'rejected';step.updated=now()
            if body.decision=='approve':run.cursor+=1
            touch(run,'queued' if body.decision=='approve' else 'rejected');event(db,run,user.id,'review_'+body.decision);db.flush();return serialize(db,run)

def run_flow_once(factory,settings):
    with factory.begin() as db:
        for run in db.scalars(select(DurableRun).where(DurableRun.status=='processing',DurableRun.lease_until<=now()).with_for_update()).all():
            recover_expired_claim(db,run)
        pending_review=or_(DurableRun.status=='waiting_review',and_(DurableRun.status=='paused',DurableRun.resume_state=='waiting_review'))
        for run in db.scalars(select(DurableRun).where(pending_review,DurableRun.review_until<=now()).with_for_update()).all():
            step=step_for(db,run)
            if step and step.kind=='approval' and step.status=='waiting_review':step.status='expired';step.updated=now()
            touch(run,'expired');event(db,run,'worker','review_expired')
        candidate=db.scalar(select(DurableRun).where(DurableRun.status.in_(POLL),DurableRun.next_poll<=now()).order_by(DurableRun.next_poll,DurableRun.created).limit(1))
        if not candidate:return False
        token=uid();previous=candidate.status
        claimed=db.execute(update(DurableRun).where(DurableRun.id==candidate.id,DurableRun.org_id==candidate.org_id,DurableRun.env==candidate.env,DurableRun.version==candidate.version,DurableRun.status==previous).values(status='processing',lease_token=token,lease_until=now()+30))
        if claimed.rowcount!=1:return False
        run_id=candidate.id;org=candidate.org_id;environment=candidate.env
    try:
        with factory.begin() as db:
            run=db.scalar(select(DurableRun).where(DurableRun.id==run_id,DurableRun.org_id==org,DurableRun.env==environment,DurableRun.status=='processing',DurableRun.lease_token==token).with_for_update())
            if not run:return True
            # A matching token is insufficient if this worker started its step
            # after the claim deadline, even when no other worker swept it yet.
            if run.lease_until<=now():recover_expired_claim(db,run);return True
            if digest(canonical(run.definition))!=run.payload_hash:fail(409,'PAYLOAD_CHANGED','Workflow fingerprint changed.')
            if run.cursor>=len(run.definition['steps']):touch(run,'succeeded');event(db,run,'worker','succeeded');return True
            step=step_for(db,run);definition=run.definition['steps'][run.cursor]
            if step.action_id:
                action=db.get(Action,step.action_id)
                if not action or action.org_id!=run.org_id or action.env!=run.env:fail(409,'ACTION_MISSING','The linked action is unavailable.')
                prior_action_status=step.result.get('status')
                step.result={'action_id':action.id,'status':action.status,'external_ref':action.external_ref,'verification':action.verification}
                if action.status=='verified':
                    step.status='completed';step.updated=now();run.cursor+=1
                    if run.cancel_requested:finish_cancel(db,run)
                    else:touch(run,'queued')
                    event(db,run,'worker','action_verified')
                elif action.status in ('queued','executing','awaiting_approval','outcome_unknown'):
                    target='outcome_unknown' if action.status=='outcome_unknown' else 'cancelling' if run.cancel_requested else 'waiting_action'
                    if action.status=='outcome_unknown':step.status='outcome_unknown'
                    if prior_action_status!=action.status or previous!=target:touch(run,target)
                    else:
                        run.status=target;run.lease_token='';run.lease_until=0;run.next_poll=now()+1
                else:
                    step.status=action.status;run.error=action.reason
                    if run.cancel_requested:finish_cancel(db,run)
                    else:touch(run,'failed')
                    event(db,run,'worker','action_stopped')
                return True
            if run.cancel_requested:finish_cancel(db,run);return True
            if run.definition.get('destination','mock-business-v1')!=connector_identity(settings):fail(409,'DESTINATION_CHANGED','The reviewed workflow connector destination changed. Create a new reviewed run for the configured adapter.')
            author=db.scalar(select(User).where(User.id==run.author_id).with_for_update());agent=db.scalar(select(Agent).where(Agent.id==run.agent_id,Agent.org_id==run.org_id,Agent.env==run.env).with_for_update())
            if not author or author.org_id!=run.org_id or not author.active or 'operate' not in PERMISSIONS.get(author.role,set()) or not environment_user_allowed(db,author.id,run.org_id,run.env,allow_non_staging=settings.mode=='local'):fail(403,'REQUESTER_REVOKED','Requester is no longer authorized.')
            if not agent or agent.org_id!=run.org_id or agent.env!=run.env or agent.status!='active' or agent.generation!=run.generation or not environment_user_allowed(db,agent.owner_id,run.org_id,run.env,allow_non_staging=settings.mode=='local'):fail(403,'AGENT_CHANGED','Agent identity or authorization changed.')
            if definition['kind']=='approval':step.status='waiting_review';run.review_until=now()+1800;touch(run,'waiting_review');event(db,run,'worker','review_required')
            elif definition['kind']=='governed_action':
                tool=scoped(db,Tool,definition['tool_id'],run.org_id,environment=run.env)
                body=ActionInput.model_validate(definition['request'])
                action=submit_action(db,settings,agent,tool,body,'run-'+run.id+'-'+str(run.cursor),'durable:'+author.id,author.id)
                step.action_id=action.id;step.status='waiting_action';step.updated=now();touch(run,'waiting_action');event(db,run,'worker','action_submitted',{'action_id':action.id})
            else:
                step.status='completed';step.result={'checkpoint':definition['label'],'completed_at':now()};step.updated=now();run.cursor+=1
                touch(run,'succeeded' if run.cursor==len(run.definition['steps']) else 'queued');event(db,run,'worker','checkpoint_completed')
        return True
    except HTTPException as exc:
        with factory.begin() as db:
            run=db.scalar(select(DurableRun).where(DurableRun.id==run_id,DurableRun.org_id==org,DurableRun.env==environment,DurableRun.status=='processing',DurableRun.lease_token==token).with_for_update())
            if run:
                run.error=exc.detail.get('code','CONTROL_FAILED') if isinstance(exc.detail,dict) else 'CONTROL_FAILED';touch(run,'failed')
                step=step_for(db,run)
                if step:step.status='failed';step.result={'error_code':run.error};step.updated=now()
                event(db,run,'worker','failed',{'code':run.error})
        return True
