"""Disposable inference controls, mocked provider traffic and explicit deadline faults."""
import argparse
from datetime import datetime,timezone
import gc
import json
import logging
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from . import __version__,inference
from .app import create_app
from .business_connector import MockBusiness
from .cli import seed
from .config import Settings
from .db import CURRENT_SCHEMA,migrate,Organization,Policy,User,WorkspaceAsset,InferenceCall,InferenceBudget,Action
from .environments import assign_staging
from .security import password_hash

BOUNDARY='Disposable synthetic inference exercise with HTTP mock transport and simulated deadline/pending states only. No model provider or customer system was contacted. This is not generated-answer quality, live-provider acceptance, authenticated evidence or production readiness.'


class DrillFailure(RuntimeError):pass


def late_response(clock,payload):
    class LateBody(httpx.SyncByteStream):
        def __iter__(self):yield json.dumps(payload).encode()
        def close(self):clock[0]=102.0
    return httpx.Response(200,stream=LateBody())


def run_drill(directory):
    root=Path(directory).resolve();root.mkdir(exist_ok=False)
    settings=Settings(database_url='sqlite:///'+(root/'control.db').as_posix(),mock_database=str(root/'business.db'),
        secret=secrets.token_urlsafe(48),agent_secret=secrets.token_urlsafe(48),frontend_dir=str(root/'no-frontend'),
        mode='local',policy_mode='reference',business_connector='synthetic',live_inference=0,
        provider_hosts='api.openai.com',provider_prices=json.dumps({'api.openai.com|drill-model':{'input':'1','output':'3'}}),
        monthly_budget_usd='1',inference_response_bytes=4096)
    report={'format':'nexus-synthetic-inference-drill','format_version':1,'release':__version__,'schema_version':CURRENT_SCHEMA,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'provider_mode':'http_mock_transport','connector_mode':'synthetic',
        'passed':False,'customer_acceptance':False,'production_ready':False,'steps':[],'boundary':BOUNDARY}
    app=None;logger=logging.getLogger('nexus.http');was_disabled=logger.disabled;logger.disabled=True
    sent=[];scenario=['normal'];clock=[100.0]
    payload={'id':'synthetic-response','choices':[{'message':{'content':'Disposable transport answer'},'finish_reason':'stop'}],
             'usage':{'prompt_tokens':12,'completion_tokens':4}}
    def check(name,condition):
        report['steps'].append({'id':name,'passed':bool(condition)})
        if not condition:raise DrillFailure(name)
    def expect(response,status):
        if response.status_code!=status:raise DrillFailure('unexpected_api_response')
        return response.json()
    def denied_network(*args,**kwargs):raise DrillFailure('network_dispatch_blocked')
    def provider(request):
        if str(request.url)!='https://api.openai.com/v1/chat/completions':raise DrillFailure('unexpected_mock_route')
        sent.append(json.loads(request.content))
        if scenario[0]=='timeout':raise httpx.ReadTimeout('private synthetic upstream detail',request=request)
        if scenario[0]=='malformed':return httpx.Response(200,json={**payload,'choices':[{'message':None}]})
        if scenario[0]=='quota':return httpx.Response(429,json={'error':'private synthetic upstream detail'})
        if scenario[0]=='redirect':return httpx.Response(302,headers={'location':'https://unapproved.invalid'})
        if scenario[0]=='oversized':return httpx.Response(200,content=b'x'*5000)
        if scenario[0]=='late':return late_response(clock,payload)
        return httpx.Response(200,json=payload)
    def login(email):expect(client.post('/auth/local/login',json={'email':email,'password':password}),200)
    def headers():
        me=expect(client.get('/v1/me'),200);context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'],'X-Nexus-Context-Revision':str(context['revision'])}
    def send(key,changes=None):return client.post('/v1/inference',headers={**headers(),'Idempotency-Key':key},json={**body,**(changes or {})})
    def runtime():return expect(client.get('/v1/runtime',headers=headers()),200)
    def recover(key):return expect(client.post('/v1/inference/recover',headers=headers(),json={'key':key}),200)
    def reconcile(row,ins=0,outs=0):return client.post('/v1/inference/'+row['id']+'/reconcile',headers=headers(),json={
        'input_tokens':ins,'output_tokens':outs,'note':'Verified disposable synthetic usage; no provider contacted.'})
    def model_config(config):
        with app.state.factory.begin() as db:db.get(WorkspaceAsset,model_id).config=config
    try:
        # Both patches are restored on every exit. No operator environment/key is read.
        with patch.object(inference,'os',SimpleNamespace(environ={'NEXUS_PROVIDER_DRILL_KEY':'disposable-transport-only'})), \
             patch.object(inference,'period',lambda:'2000-01'), \
             patch.object(httpx.HTTPTransport,'handle_request',denied_network):
            app=create_app(settings);app.state.provider_transport=httpx.MockTransport(provider)
            migrate(app.state.engine,app.state.factory);password=secrets.token_urlsafe(32);seed(app.state.factory,password)
            config={'provider':'OpenAI','model':'drill-model','endpoint':'https://api.openai.com/v1',
                'credential_ref':'env:NEXUS_PROVIDER_DRILL_KEY','token_limit':4096,'timeout_ms':2000,'temperature':0.2}
            with app.state.factory.begin() as db:
                model=WorkspaceAsset(org_id='northstar',kind='model',name='Disposable checked route',status='validated',version=2,author_id='synthetic',config=config)
                db.add(model);db.flush();model_id=model.id
                db.add(Organization(id='inference-other',name='Disposable isolated workspace'));db.add(Policy(org_id='inference-other',version=1))
                other=User(org_id='inference-other',email='other@drill.invalid',name='Disposable owner',role='owner',password_hash=password_hash(password))
                db.add(other);db.flush();assign_staging(db,other)
            body={'model_id':model_id,'expected_version':2,'query':'Use disposable confidential phrase.','max_output_tokens':100}
            key='synthetic-inference-normal-001'
            with TestClient(app) as client:
                check('isolated_mock_runtime',type(app.state.connector) is MockBusiness and type(app.state.provider_transport) is httpx.MockTransport)
                check('anonymous_runtime_blocked',client.get('/v1/runtime').status_code==401)
                login('owner@nexus.local')
                check('inference_requires_csrf',client.post('/v1/inference',headers={'Idempotency-Key':key},json=body).status_code==403 and not sent)
                check('disabled_runtime_sends_nothing',send(key).status_code==503 and not sent)
                settings.live_inference=1
                check('stale_model_version_sends_nothing',send(key,{'expected_version':1}).status_code==409 and not sent)
                model_config({**config,'endpoint':'https://unapproved.invalid/v1'})
                check('unapproved_route_sends_nothing',send(key).status_code==422 and not sent)
                model_config({**config,'model':'unpriced-synthetic-model'})
                check('unpriced_model_sends_nothing',send(key).status_code==422 and not sent);model_config(config)
                with app.state.factory.begin() as db:
                    for id,mode in [('drill-rule-001','redact'),('drill-rule-002','block')]:
                        db.add(WorkspaceAsset(id=id,org_id='northstar',kind='guardrail',name='Disposable input rule',author_id='synthetic',
                            config={'blocked_terms':['disposable confidential phrase'],'detect_email':False,'detect_override':False,'mode':mode}))
                check('redaction_cannot_hide_original_block',send(key).status_code==422 and not sent)
                expect(client.post('/v1/workbench/drill-rule-002/archive',headers=headers(),json={'expected_version':1}),200)
                normal=expect(send(key),200);state=runtime()
                check('reviewed_rule_archive_allows_redacted_dispatch',normal['status']=='completed' and len(sent)==1 and
                    'disposable confidential phrase' not in json.dumps(sent[0]) and '[REDACTED]' in json.dumps(sent[0]))
                check('successful_usage_settles_reservation',normal['charged']==24 and state['held_micro_usd']==0 and state['spent_micro_usd']==24)
                replay=expect(send(key),200);recovered=recover(key)
                check('completed_replay_recovery_does_not_send',replay['id']==recovered['id']==normal['id'] and len(sent)==1)
                check('changed_intent_rejected',send(key,{'query':'Different immutable request'}).status_code==409 and len(sent)==1)
                scenario[0]='timeout';unknown_key='synthetic-inference-timeout-001';unknown=expect(send(unknown_key),200);state=runtime()
                check('timeout_retains_unknown_reservation',unknown['status']=='unknown' and unknown['charged']==0 and state['held_micro_usd']==unknown['reserved']>0 and len(sent)==2 and
                    'private synthetic upstream detail' not in json.dumps(unknown))
                check('unknown_replay_recovery_does_not_send',expect(send(unknown_key),200)['id']==recover(unknown_key)['id']==unknown['id'] and len(sent)==2)
                login('auditor@nexus.local')
                check('nonowner_cannot_reconcile',reconcile(unknown,10,2).status_code==403)
                login('other@drill.invalid');foreign=runtime()
                check('other_workspace_has_no_private_calls_or_budget',foreign['calls']==[] and foreign['held_micro_usd']==foreign['spent_micro_usd']==0)
                check('other_workspace_cannot_recover_or_reconcile',client.post('/v1/inference/recover',headers=headers(),json={'key':unknown_key}).status_code==404 and reconcile(unknown,10,2).status_code==404)
                login('owner@nexus.local');settled=expect(reconcile(unknown,10,2),200);state=runtime()
                check('owner_reconciliation_settles_once',settled['status']=='reconciled' and settled['charged']==16 and state['held_micro_usd']==0 and state['spent_micro_usd']==40 and reconcile(unknown,10,2).status_code==409 and len(sent)==2)
                for mode in ('malformed','quota','redirect','oversized'):
                    scenario[0]=mode;failure_key='synthetic-inference-'+mode+'-001';before=len(sent)
                    row=expect(send(failure_key),200);held=runtime()['held_micro_usd'];replay=expect(send(failure_key),200)
                    check(mode+'_outcome_stays_unknown_without_retry',row['status']=='unknown' and row['charged']==0 and held==row['reserved']>0 and replay['id']==row['id'] and len(sent)==before+1 and
                        'private synthetic upstream detail' not in json.dumps(row))
                    expect(reconcile(row),200)
                scenario[0]='late'
                with patch.object(inference,'time',SimpleNamespace(monotonic=lambda:clock[0],time=time.time,perf_counter=time.perf_counter)):
                    late=expect(send('synthetic-inference-late-001'),200)
                check('simulated_late_completion_stays_unknown',late['status']=='unknown' and late['charged']==0 and runtime()['held_micro_usd']==late['reserved']>0 and len(sent)==7)
                # Represent a still-pending call using disposable state only; do not sleep or send a second provider request.
                settings.inference_max_inflight=1
                with app.state.factory.begin() as db:db.get(InferenceCall,late['id']).status='pending'
                try:
                    saturated=send('synthetic-inference-concurrent-001')
                    check('simulated_pending_saturation_sends_nothing',saturated.status_code==429 and saturated.json()['error']['code']=='INFERENCE_CONCURRENCY_LIMIT' and len(sent)==7 and runtime()['held_micro_usd']==late['reserved'])
                finally:
                    with app.state.factory.begin() as db:db.get(InferenceCall,late['id']).status='unknown'
                    settings.inference_max_inflight=4
                expect(reconcile(late),200);scenario[0]='normal';settings.monthly_budget_usd='0.000040'
                limited=send('synthetic-inference-budget-001')
                check('monthly_budget_rejection_sends_nothing',limited.status_code==429 and limited.json()['error']['code']=='MONTHLY_BUDGET_EXCEEDED' and len(sent)==7)
                settings.monthly_budget_usd='1';settings.inference_requests_per_minute=1
                limited=send('synthetic-inference-rate-001')
                check('request_rate_rejection_sends_nothing',limited.status_code==429 and limited.json()['error']['code']=='INFERENCE_RATE_LIMIT' and len(sent)==7)
                with app.state.factory() as db:
                    count=db.scalar(select(func.count()).select_from(InferenceCall));actions=db.scalar(select(func.count()).select_from(Action));ledger=db.scalar(select(InferenceBudget))
                    pending=db.scalar(select(func.count()).select_from(InferenceCall).where(InferenceCall.status.in_(('unknown','pending'))))
                    check('final_ledger_has_only_seven_mock_calls_and_no_business_effects',count==7 and actions==0 and pending==0 and ledger.held==0 and ledger.spent==40 and app.state.connector.count()==0)
                report['provider_request_count']=7;report['spent_micro_usd']=40;report['passed']=True
    except DrillFailure as exc:report['failure']=str(exc)
    except Exception:report['failure']='isolated_drill_could_not_finish'
    finally:
        if app is not None:app.state.engine.dispose()
        gc.collect();logger.disabled=was_disabled
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Exercise disposable inference controls without operator keys or network calls.')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/drills')
    args=parser.parse_args(argv)
    try:
        destination=args.output_dir.resolve();destination.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.inference-',dir=destination) as scratch:
            if Path(scratch).resolve().parent!=destination:raise ValueError('Invalid temporary directory')
            result=run_drill(Path(scratch)/'workspace')
        report=destination/('synthetic-inference-'+uuid.uuid4().hex+'.json')
        with report.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2)
        print(json.dumps({'passed':result['passed'],'steps_passed':sum(row['passed'] for row in result['steps']),'report':str(report),'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError,ValueError):
        print(json.dumps({'passed':False,'failure':'Could not create or clean up the disposable drill report.','boundary':BOUNDARY}));return 1


if __name__=='__main__':raise SystemExit(main())
