import base64
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from conftest import auth
from nexus.db import User,Policy,KnowledgeDocument,SessionRuntimeContext,WorkspaceEnvironment,EnvironmentAssignment,Agent,Tool,Grant,Action,Audit
from nexus.security import digest


def current(ctx):
    response=ctx['client'].get('/v1/me');assert response.status_code==200,response.text
    return response.json()

def headers(me):
    c=me['runtime_context']
    return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],'X-Nexus-Context-ID':c['binding_id'],'X-Nexus-Context-Revision':str(c['revision'])}

def prepare(ctx,key='production',activate=True):
    csrf,owner=auth(ctx)
    row=ctx['client'].post('/v1/workspace-environments',headers=csrf,json={'key':key,'name':key.title(),'note':'Prepare isolated local runtime.'}).json()
    assignments=ctx['client'].get('/v1/workspace-environments/'+key+'/assignments').json()
    candidate=next(r for r in assignments['candidates'] if r['id']==owner)
    result=ctx['client'].post('/v1/workspace-environments/'+key+'/assignments/control',headers=csrf,json={'user_id':owner,'command':'grant','expected_version':row['version'],'expected_member_revision':candidate['revision'],'reviewed':True,'note':'Assign owner before local activation.'})
    assert result.status_code==200,result.text
    csrf,_=auth(ctx)  # Granting membership deliberately revokes affected sessions.
    version=result.json()['version']
    if not activate:return {'key':key,'version':version}
    result=ctx['client'].post('/v1/workspace-environments/'+key+'/activate',headers=csrf,json={'expected_version':version,'reviewed':True,'note':'Review empty local namespace and assigned members.'})
    assert result.status_code==200,result.text
    return result.json()

def selection(me,target):
    c=me['runtime_context']
    return {'workspace_id':c['workspace_id'],'environment':target['key'],'expected_revision':c['revision'],'expected_binding_id':c['binding_id'],'expected_environment_version':target['version'],'reviewed':True}

def switch(ctx,target):
    me=current(ctx)
    response=ctx['client'].post('/v1/session-context/select',headers=headers(me),json=selection(me,target))
    assert response.status_code==200,response.text
    return current(ctx)

def upload(ctx,me,key='shared-document-key-001'):
    response=ctx['client'].post('/v1/documents',headers={**headers(me),'Idempotency-Key':key},json={'title':me['environment']+' evidence','filename':'scope.txt','content_base64':base64.b64encode((me['environment']+' private needle evidence').encode()).decode(),'allowed_roles':[]})
    assert response.status_code==201,response.text
    return response.json()


def test_reviewed_empty_activation_adds_only_a_disabled_purchase_policy(ctx):
    row=prepare(ctx)
    assert row['state']=='active' and row['human_runtime_enabled']
    with ctx['db']() as db:
        policy=db.scalar(select(Policy).where(Policy.env=='production'))
        assert policy.threshold==policy.maximum=='0.00'
        assert not db.scalars(select(Agent).where(Agent.env=='production')).all()
        assert not db.scalars(select(Tool).where(Tool.env=='production')).all()
    choices=ctx['client'].get('/v1/session-context/choices').json()
    assert {r['key'] for r in choices['items']}=={'staging','production'}


def test_switching_preserves_separate_documents_and_keys_and_invalidates_old_frames(ctx):
    prod=prepare(ctx);stage_me=current(ctx);stage=upload(ctx,stage_me)
    prod_me=switch(ctx,prod)
    assert prod_me['environment']=='production' and prod_me['runtime_context']['revision']==2
    assert prod_me['csrf']!=stage_me['csrf']
    assert ctx['client'].get('/v1/documents',headers=headers(stage_me)).status_code==409
    assert ctx['client'].get('/v1/documents').status_code==409
    assert ctx['client'].get('/v1/documents',headers=headers(prod_me)).json()['items']==[]
    document=upload(ctx,prod_me);assert document['env']=='production' and document['id']!=stage['id']
    assert ctx['client'].get('/v1/documents/'+stage['id'],headers=headers(prod_me)).status_code==404
    restored=switch(ctx,{'key':'staging','version':1})
    assert restored['runtime_context']['revision']==3
    assert [d['id'] for d in ctx['client'].get('/v1/documents',headers=headers(restored)).json()['items']]==[stage['id']]
    assert ctx['client'].get('/v1/documents/'+document['id'],headers=headers(restored)).status_code==404
    assert ctx['client'].post('/auth/logout',headers=headers(restored)).status_code==200


def test_preparing_and_unassigned_environments_cannot_be_selected(ctx):
    target=prepare(ctx,activate=False);me=current(ctx)
    assert ctx['client'].post('/v1/session-context/select',headers=headers(me),json=selection(me,target)).status_code==403
    with ctx['db'].begin() as db:
        db.get(WorkspaceEnvironment,('northstar','production')).state='active'
        db.delete(db.get(EnvironmentAssignment,(me['user']['id'],'northstar','production')))
    assert ctx['client'].post('/v1/session-context/select',headers=headers(me),json=selection(me,target)).status_code==403


def test_activation_rejects_existing_runtime_records_and_stale_review(ctx):
    row=prepare(ctx,activate=False);me=current(ctx)
    with ctx['db'].begin() as db:db.add(Policy(org_id='northstar',env='production',version=1))
    url='/v1/workspace-environments/production/activate'
    body={'expected_version':row['version'],'reviewed':True,'note':'Do not promote existing runtime data.'}
    assert ctx['client'].post(url,headers=headers(me),json={**body,'expected_version':1}).status_code==409
    response=ctx['client'].post(url,headers=headers(me),json=body)
    assert response.status_code==409 and response.json()['error']['code']=='ENVIRONMENT_NOT_EMPTY'
    with ctx['db']() as db:assert db.get(WorkspaceEnvironment,('northstar','production')).state=='preparing'


def test_selection_review_and_target_version_are_required(ctx):
    row=prepare(ctx);me=current(ctx);body=selection(me,row)
    assert ctx['client'].post('/v1/session-context/select',headers=headers(me),json={**body,'reviewed':False}).status_code==422
    assert ctx['client'].post('/v1/session-context/select',headers=headers(me),json={**body,'expected_environment_version':1}).status_code==409
    assert current(ctx)['environment']=='staging'


def test_competing_selections_cannot_both_commit_the_same_revision(ctx):
    target=prepare(ctx);me=current(ctx);cookie=ctx['client'].cookies.get('nexus_session')
    def choose(_):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post('/v1/session-context/select',headers=headers(me),json=selection(me,target)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(choose,[1,2]))
    assert statuses.count(200)==1 and all(s in (200,403,409) for s in statuses)
    assert current(ctx)['runtime_context']['revision']==2


def test_late_read_is_withheld_when_the_selected_context_changes(ctx,monkeypatch):
    prepare(ctx);me=current(ctx);upload(ctx,me)
    from nexus import documents
    original=documents.search_documents
    def changed(db,user,*args,**kwargs):
        result=original(db,user,*args,**kwargs)
        with ctx['db'].begin() as other:
            row=other.get(SessionRuntimeContext,digest(ctx['client'].cookies.get('nexus_session')))
            row.environment='production';row.revision+=1
        return result
    monkeypatch.setattr(documents,'search_documents',changed)
    result=ctx['client'].get('/v1/documents/search?q=needle',headers=headers(me))
    assert result.status_code==409 and 'staging private needle' not in result.text


def test_workspace_provisioning_recovery_is_shared_across_environments(ctx):
    target=prepare(ctx);me=current(ctx)
    body={'email':'new-scoped@synthetic.invalid','name':'Global member','role':'engineer','reviewed':True,'note':'Provision a workspace account once.'}
    h={**headers(me),'Idempotency-Key':'workspace-member-key-001'}
    first=ctx['client'].post('/v1/member-admin',headers=h,json=body);assert first.status_code==201,first.text
    prod=switch(ctx,target)
    recover=ctx['client'].post('/v1/member-admin/provision/recover',headers=headers(prod),json={'key':'workspace-member-key-001'})
    assert recover.status_code==200 and recover.json()['id']==first.json()['id']
    replay=ctx['client'].post('/v1/member-admin',headers={**headers(prod),'Idempotency-Key':'workspace-member-key-001'},json=body)
    assert replay.status_code==201 and replay.json()['id']==first.json()['id']


def test_pilot_mode_keeps_non_staging_runtime_disabled(ctx):
    target=prepare(ctx);ctx['settings'].mode='pilot';me=current(ctx)
    assert me['runtime_context']['switching_enabled'] is False
    result=ctx['client'].post('/v1/session-context/select',headers=headers(me),json=selection(me,target))
    assert result.status_code==409
    assert ctx['client'].post('/v1/workspace-environments/production/activate',headers=headers(me),json={'expected_version':target['version'],'reviewed':True,'note':'Pilot activation must remain disabled.'}).status_code==403


def test_worker_finishes_in_origin_environment_after_session_switch(ctx):
    from test_ingestion import payload
    from nexus.ingestion import run_ingestion_once
    from nexus.db import IngestionJob
    target=prepare(ctx);prod=switch(ctx,target)
    result=ctx['client'].post('/v1/ingestion-jobs',headers={**headers(prod),'Idempotency-Key':'origin-job-key-001'},json=payload())
    assert result.status_code==201,result.text
    job=result.json()
    stage=switch(ctx,{'key':'staging','version':1})
    assert run_ingestion_once(ctx['db'],ctx['settings'],lambda *args:{'text':'Production evidence remains in its origin environment.','info':{'method':'synthetic'}})
    assert ctx['client'].get('/v1/ingestion-jobs/'+job['id'],headers=headers(stage)).status_code==404
    prod=switch(ctx,target)
    parsed=ctx['client'].get('/v1/ingestion-jobs/'+job['id'],headers=headers(prod)).json()
    assert parsed['status']=='awaiting_review'
    published=ctx['client'].post('/v1/ingestion-jobs/'+job['id']+'/publish',headers=headers(prod),json={'expected_version':parsed['version'],'note':'Reviewed extracted source in its origin environment.','reviewed':True})
    assert published.status_code==200,published.text
    with ctx['db']() as db:
        assert db.get(KnowledgeDocument,published.json()['document_id']).env=='production'
        assert db.get(IngestionJob,job['id']).env=='production'


def test_revoked_membership_blocks_selected_runtime_and_worker_publication(ctx):
    from test_ingestion import payload
    from nexus.ingestion import run_ingestion_once
    from nexus.db import IngestionJob
    target=prepare(ctx);prod=switch(ctx,target)
    result=ctx['client'].post('/v1/ingestion-jobs',headers={**headers(prod),'Idempotency-Key':'revoked-origin-key-001'},json=payload())
    assert result.status_code==201,result.text
    with ctx['db'].begin() as db:db.delete(db.get(EnvironmentAssignment,(prod['user']['id'],'northstar','production')))
    assert ctx['client'].get('/v1/documents',headers=headers(prod)).status_code==403
    def forbidden(*args):raise AssertionError('Revoked author must not reach extractor')
    assert run_ingestion_once(ctx['db'],ctx['settings'],forbidden)
    with ctx['db']() as db:
        job=db.get(IngestionJob,result.json()['id'])
        assert job.status=='failed' and job.error_code=='REQUESTER_REVOKED'


def test_activation_requires_owner_assignment_review_and_csrf(ctx):
    csrf,owner=auth(ctx)
    row=ctx['client'].post('/v1/workspace-environments',headers=csrf,json={'key':'sandbox','name':'Sandbox','note':'Prepare unassigned local sandbox.'}).json()
    url='/v1/workspace-environments/sandbox/activate'
    body={'expected_version':row['version'],'reviewed':True,'note':'Review activation before runtime access.'}
    assert ctx['client'].post(url,headers=csrf,json=body).status_code==403
    assert ctx['client'].post(url,json=body).status_code==403
    assert ctx['client'].post(url,headers=csrf,json={**body,'reviewed':False}).status_code==422
    csrf,_=auth(ctx,'auditor')
    assert ctx['client'].post(url,headers=csrf,json=body).status_code==403
