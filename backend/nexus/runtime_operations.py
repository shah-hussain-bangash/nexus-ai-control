"""Tenant-scoped operating signals and optional token-protected Prometheus exposition."""
import hmac
from sqlalchemy import select,func
from fastapi import Request
from fastapi.responses import PlainTextResponse
from .db import Action,DurableRun,KnowledgeDocument,Approval,Incident,SchemaVersion,now
from .security import fail
from .business_connector import connector_profile


def grouped(db,model,org=None):
    query=select(model.status,func.count()).group_by(model.status)
    if org is not None:query=query.where(model.org_id==org,model.env=='staging')
    return dict(db.execute(query).all())


def signals(db,org=None):
    actions=grouped(db,Action,org);runs=grouped(db,DurableRun,org);docs=grouped(db,KnowledgeDocument,org)
    queued=select(func.min(Action.created)).where(Action.status=='queued')
    approvals=select(func.count()).select_from(Approval).where(Approval.status=='pending',Approval.expires>now())
    if org is not None:
        queued=queued.where(Action.org_id==org,Action.env=='staging');approvals=approvals.where(Approval.org_id==org,Approval.env=='staging')
    oldest=db.scalar(queued)
    return {'actions':actions,'agent_runs':runs,'documents':docs,'pending_unexpired_approvals':db.scalar(approvals),
            'oldest_queued_action_age_seconds':round(max(0,now()-oldest),2) if oldest else 0,
            'sampled_at':now(),'schema_version':db.scalar(select(func.max(SchemaVersion.version)))}


def register_runtime_operations(app,factory,settings,human):
    @app.get('/v1/runtime-operations')
    def overview(request:Request):
        with factory() as db:
            user=human(request,db)
            return {**signals(db,user.org_id),'connector':connector_profile(settings),
                    'metrics_enabled':bool(settings.metrics_token),'metrics_authentication':'server-configured X-Nexus-Metrics-Token header; never put the token in URLs',
                    'boundary':'Current database signals only. These are not distributed request metrics, worker liveness, alert delivery, SLO acceptance or production certification.'}

    @app.get('/metrics',response_class=PlainTextResponse,include_in_schema=False)
    def metrics(request:Request):
        if not settings.metrics_token:fail(404,'METRICS_DISABLED','Metrics export is not enabled.')
        token=request.headers.get('X-Nexus-Metrics-Token','')
        if not hmac.compare_digest(token.encode(),settings.metrics_token.encode()):fail(403,'METRICS_FORBIDDEN','Metrics authentication failed.')
        with factory() as db:values=signals(db)
        lines=['# HELP nexus_schema_version Current database schema version.','# TYPE nexus_schema_version gauge',f'nexus_schema_version {values["schema_version"] or 0}']
        allowed={'actions':('queued','executing','verified','outcome_unknown','failed','denied','blocked','awaiting_approval','cancelled','expired','rejected','changes_requested'),
                 'agent_runs':('queued','processing','waiting_action','waiting_review','paused','cancelling','outcome_unknown','succeeded','failed','cancelled','expired','rejected'),
                 'documents':('indexed','deleted')}
        for key,states in allowed.items():
            metric='nexus_'+key
            lines.extend([f'# HELP {metric} Current records by fixed status; no tenant or record labels.',f'# TYPE {metric} gauge'])
            for status in states:lines.append(f'{metric}{{status="{status}"}} {values[key].get(status,0)}')
        for key in ('pending_unexpired_approvals','oldest_queued_action_age_seconds'):
            name='nexus_'+key;lines.extend([f'# TYPE {name} gauge',f'{name} {values[key]}'])
        return PlainTextResponse('\n'.join(lines)+'\n',media_type='text/plain; version=0.0.4',headers={'Cache-Control':'no-store'})
