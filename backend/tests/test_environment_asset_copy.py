from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from conftest import auth
from test_local_switching import prepare,current,headers,switch
from test_environment_runtime import inventory,control
from nexus.db import WorkspaceAsset,AssetRevision,WorkbenchRun,Audit,EnvironmentAssignment,WorkspaceEnvironment

URL='/v1/environment-asset-copies'
KEY='reviewed-design-copy-001'

def source(ctx,kind='prompt',validate=True):
    config={'template':'Reviewed synthetic request {{query}}','required_terms':[],'forbidden_terms':[]} if kind=='prompt' else {'blocked_terms':['unsafe'],'mode':'block'}
    if kind=='model':config={'provider':'OpenAI','model':'synthetic-model','credential_ref':'env:TEST_PROVIDER_KEY'}
    if kind=='knowledge':config={'content':'Synthetic knowledge remains excluded from design copying.'}
    row=ctx['client'].post('/v1/workbench',headers=headers(current(ctx)),json={'kind':kind,'name':'Source design','description':'Synthetic reviewed design.','config':config})
    assert row.status_code==201,row.text
    if not validate:return row.json()
    result=ctx['client'].post('/v1/workbench/'+row.json()['id']+'/validate',headers=headers(current(ctx)),json={'expected_version':1})
    assert result.status_code==200,result.text
    return result.json()

def payload(asset,target,**changes):
    return {'source_asset_id':asset['id'],'expected_source_version':asset['version'],'target_environment':target['key'],'expected_target_version':target['version'],
            'name':'Reviewed target draft','note':'Reviewed source content and target membership.','reviewed':True,**changes}

def copy(ctx,body,key=KEY):return ctx['client'].post(URL,headers={**headers(current(ctx)),'Idempotency-Key':key},json=body)
def resolve(ctx,command,key=KEY):return ctx['client'].post(URL+'/'+command,headers=headers(current(ctx)),json={'key':key})

@pytest.mark.parametrize('kind',['prompt','guardrail'])
def test_copy_creates_only_a_new_target_draft_and_origin_revision(ctx,kind):
    target=prepare(ctx);asset=source(ctx,kind);body=payload(asset,target)
    result=copy(ctx,body);assert result.status_code==201,result.text
    receipt=result.json();assert receipt['status']=='copied' and receipt['target_asset_id']!=asset['id']
    assert 'fingerprint' not in receipt and KEY not in str(receipt)
    listing=ctx['client'].get('/v1/workbench',headers=headers(current(ctx))).json()
    assert [r['id'] for r in listing['assets']]==[asset['id']] and not listing['runs']
    assert copy(ctx,{**body,'source_asset_id':receipt['target_asset_id'],'expected_source_version':1},key='foreign-source-key-001').status_code==404
    with ctx['db']() as db:
        original=db.get(WorkspaceAsset,asset['id']);draft=db.get(WorkspaceAsset,receipt['target_asset_id'])
        assert original.version==asset['version'] and original.status=='validated'
        assert draft.env=='production' and draft.org_id=='northstar' and draft.status=='draft' and draft.version==1
        assert draft.config==original.config and draft.author_id==original.author_id
        history=db.scalars(select(AssetRevision).where(AssetRevision.asset_id==draft.id)).all()
        assert len(history)==1 and history[0].env=='production'
        assert history[0].snapshot['copied_from']=={'environment':'staging','asset_id':asset['id'],'version':asset['version']}
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.event=='environment.asset_copied'))==1
    prod=switch(ctx,target)
    target_listing=ctx['client'].get('/v1/workbench',headers=headers(prod)).json()
    assert len(target_listing['assets'])==1 and target_listing['assets'][0]['id']==receipt['target_asset_id']
    assert ctx['client'].get('/v1/workbench/'+receipt['target_asset_id']+'/history',headers=headers(prod)).status_code==200

def test_replay_recovery_and_cancel_completed_copy_return_one_immutable_outcome(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target)
    first=copy(ctx,body);assert first.status_code==201
    assert copy(ctx,body).json()==first.json()
    assert copy(ctx,{**body,'name':'Another name'}).status_code==409
    assert resolve(ctx,'recover').json()==first.json()
    assert resolve(ctx,'cancel').json()==first.json()  # Never delete an existing draft.
    assert ctx['client'].post('/v1/workbench/'+asset['id']+'/archive',headers=headers(current(ctx)),json={'expected_version':asset['version']}).status_code==200
    assert copy(ctx,body).json()==first.json()  # Replay does not require the old source to still be available.
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production'))==1

def test_cancellation_tombstone_fences_delayed_submission_and_recovery(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target)
    assert resolve(ctx,'recover').status_code==404
    cancelled=resolve(ctx,'cancel');assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
    assert resolve(ctx,'recover').json()==cancelled.json()
    assert resolve(ctx,'cancel').json()==cancelled.json()
    response=copy(ctx,body);assert response.status_code==409 and response.json()['error']['code']=='COPY_CANCELLED'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production'))==0

def test_competing_copy_and_cancel_have_one_terminal_receipt(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target);me=current(ctx);cookie=ctx['client'].cookies.get('nexus_session')
    def execute(command):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post(URL+('/cancel' if command=='cancel' else ''),headers={**headers(me),'Idempotency-Key':KEY},json={'key':KEY} if command=='cancel' else body)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,['copy','cancel']))
    copied,cancelled=results;assert cancelled.status_code==200
    with ctx['db']() as db:
        count=db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production'))
        rows=db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind=='environment_asset_copy')).all()
        assert len(rows)==1
        assert (copied.status_code,cancelled.json()['status'],count) in ((201,'copied',1),(409,'cancelled',0))

def test_competing_identical_copies_do_not_duplicate_target_drafts(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target);me=current(ctx);cookie=ctx['client'].cookies.get('nexus_session')
    def execute(_):
        with TestClient(ctx['app']) as client:
            client.cookies.set('nexus_session',cookie)
            return client.post(URL,headers={**headers(me),'Idempotency-Key':KEY},json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,[1,2]))
    assert all(r.status_code==201 for r in results) and results[0].json()==results[1].json()

def test_source_and_target_versions_and_review_are_rechecked(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target)
    for changes,status in (({'reviewed':False},422),({'expected_source_version':1},409),({'expected_target_version':1},409),({'target_environment':'staging'},422),({'name':'  '},422)):
        assert copy(ctx,{**body,**changes}).status_code==status
    draft=source(ctx,validate=False);assert copy(ctx,payload(draft,target)).status_code==409
    knowledge=source(ctx,'knowledge');assert copy(ctx,payload(knowledge,target)).status_code==422
    assert ctx['client'].post(URL,headers=headers(current(ctx)),json=body).status_code==422

def test_target_must_be_active_assigned_and_in_the_same_workspace(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target);owner=current(ctx)['user']['id']
    assert control(ctx,inventory(ctx)).status_code==200
    assert copy(ctx,body).status_code==403
    assert control(ctx,inventory(ctx),'resume').status_code==200
    with ctx['db'].begin() as db:db.delete(db.get(EnvironmentAssignment,(owner,'northstar','production')))
    assert copy(ctx,body).status_code==403
    auth(ctx,org='other');assert copy(ctx,body).status_code==403

def test_copy_and_receipts_require_owner_csrf_local_mode_and_actor_source_scope(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target);first=copy(ctx,body);assert first.status_code==201
    assert ctx['client'].post(URL,headers={'Idempotency-Key':'without-csrf-key-001'},json=body).status_code==403
    assert ctx['client'].post(URL+'/cancel',json={'key':KEY}).status_code==403
    prod=switch(ctx,target)
    assert resolve(ctx,'recover').status_code==404
    assert resolve(ctx,'cancel').json()['status']=='cancelled'  # Same key in another source has a separate scope.
    auth(ctx,'auditor');assert resolve(ctx,'recover').status_code==403
    auth(ctx,org='other');assert resolve(ctx,'recover').status_code==404
    auth(ctx);ctx['settings'].mode='pilot';assert copy(ctx,body).status_code==403 and resolve(ctx,'cancel').status_code==403

def test_copy_is_atomic_if_revision_storage_fails(ctx,monkeypatch):
    from sqlalchemy.orm import Session
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target);original=Session.execute
    def execute(db,statement,*args,**kwargs):
        if getattr(getattr(statement,'table',None),'name',None)=='asset_revisions' and getattr(statement,'is_insert',False):raise RuntimeError('Synthetic storage failure')
        return original(db,statement,*args,**kwargs)
    monkeypatch.setattr(Session,'execute',execute)
    with pytest.raises(RuntimeError,match='Synthetic storage failure'):copy(ctx,body)
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production'))==0
        assert db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind=='environment_asset_copy'))==0


def test_reverse_copy_and_same_key_in_a_different_source_are_isolated(ctx):
    target=prepare(ctx);asset=source(ctx)
    first=copy(ctx,payload(asset,target));assert first.status_code==201
    switch(ctx,target);other=source(ctx)
    second=copy(ctx,payload(other,inventory(ctx,'staging')));assert second.status_code==201,second.text
    assert second.json()['target_environment']=='staging' and second.json()['id']!=first.json()['id']
    assert resolve(ctx,'recover').json()==second.json()


@pytest.mark.parametrize('kind',['receipt','target'])
def test_copy_capacity_is_bounded_without_creating_a_partial_draft(ctx,kind):
    target=prepare(ctx);asset=source(ctx);owner=current(ctx)['user']['id']
    with ctx['db'].begin() as db:
        if kind=='receipt':
            db.add_all([WorkbenchRun(org_id='northstar',env='staging',kind='environment_asset_copy',status='cancelled',duration_ms=0,author_id=owner,result={'status':'cancelled'}) for _ in range(1000)])
        else:
            db.add_all([WorkspaceAsset(org_id='northstar',env='production',kind='prompt',name='Existing draft '+str(i),config={'template':'Existing synthetic design'},author_id=owner) for i in range(500)])
    result=copy(ctx,payload(asset,target));assert result.status_code==429,result.text
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production'))==(500 if kind=='target' else 0)
