import pytest
from sqlalchemy import select,func
from test_local_switching import prepare,current,headers,switch
from test_environment_runtime import inventory,control
from test_environment_asset_copy import source,payload,copy,resolve,KEY,URL
from conftest import auth
from nexus.db import WorkspaceAsset,AssetRevision,WorkbenchRun,EnvironmentAssignment
from nexus.security import digest
from nexus.service import canonical

def create(ctx,kind,config,name):
    created=ctx['client'].post('/v1/workbench',headers=headers(current(ctx)),json={'kind':kind,'name':name,'description':'Synthetic mapped workflow fixture.','config':config})
    assert created.status_code==201,created.text
    checked=ctx['client'].post('/v1/workbench/'+created.json()['id']+'/validate',headers=headers(current(ctx)),json={'expected_version':1})
    assert checked.status_code==200,checked.text
    return checked.json()

def fixtures(ctx):
    target=prepare(ctx)
    source_refs={'retrieve':create(ctx,'knowledge',{'content':'Synthetic source-only knowledge content.'},'Source knowledge'),
                 'prompt':source(ctx),'guardrail':source(ctx,'guardrail')}
    nodes=[{'id':'input','kind':'input','label':'Input'}]+[
        {'id':kind+'-step','kind':kind,'label':kind.title()+' step','ref_id':row['id'],'ref_version':row['version']} for kind,row in source_refs.items()]+[{'id':'output','kind':'output','label':'Output'}]
    flow=create(ctx,'workflow',{'nodes':nodes},'Source workflow')
    switch(ctx,target)
    target_refs={'retrieve':create(ctx,'knowledge',{'content':'Different target knowledge stays in the target.'},'Target knowledge'),
                 'prompt':create(ctx,'prompt',{'template':'Target reviewed prompt {{query}}'},'Target prompt'),
                 'guardrail':create(ctx,'guardrail',{'blocked_terms':['target restriction']},'Target guardrail')}
    switch(ctx,{'key':'staging','version':1})
    mappings=[{'node_id':kind+'-step','target_asset_id':row['id'],'expected_target_asset_version':row['version']} for kind,row in target_refs.items()]
    return target,flow,source_refs,target_refs,payload(flow,target,reference_mappings=mappings)

def test_workflow_copy_rebinds_all_references_and_keeps_dependencies_unchanged(ctx):
    target,flow,src,refs,body=fixtures(ctx)
    result=copy(ctx,body);assert result.status_code==201,result.text
    assert result.json()['kind']=='workflow' and len(result.json()['reference_mappings'])==3
    with ctx['db']() as db:
        draft=db.get(WorkspaceAsset,result.json()['target_asset_id'])
        assert draft.status=='draft' and draft.version==1 and draft.env=='production'
        actual={node['kind']:(node['ref_id'],node['ref_version']) for node in draft.config['nodes'] if node['ref_id']}
        assert actual=={kind:(row['id'],row['version']) for kind,row in refs.items()}
        assert not ({row['id'] for row in src.values()} & {id for id,version in actual.values()})
        assert db.get(WorkspaceAsset,flow['id']).config==flow['config']
        for row in refs.values():
            stored=db.get(WorkspaceAsset,row['id'])
            assert stored.config==row['config'] and stored.version==row['version'] and stored.status=='validated'
        revisions=db.scalars(select(AssetRevision).where(AssetRevision.asset_id==draft.id)).all()
        assert len(revisions)==1 and revisions[0].snapshot['copied_from']['references']==result.json()['reference_mappings']
        assert db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production'))==4
    assert copy(ctx,body).json()==result.json() and resolve(ctx,'recover').json()==result.json()
    assert resolve(ctx,'cancel').json()==result.json()

@pytest.mark.parametrize('case',['missing','extra','duplicate','wrong_kind','source_id','stale_version','draft_target','source_changed','source_archived'])
def test_workflow_copy_rejects_unreviewed_missing_or_changed_reference_mappings(ctx,case):
    target,flow,src,refs,body=fixtures(ctx);mappings=body['reference_mappings']
    expected=422
    if case=='missing':body['reference_mappings']=mappings[:-1]
    elif case=='extra':body['reference_mappings']=[*mappings,{'node_id':'input','target_asset_id':refs['prompt']['id'],'expected_target_asset_version':2}]
    elif case=='duplicate':body['reference_mappings']=[*mappings,mappings[0]]
    elif case=='wrong_kind':mappings[0]['target_asset_id']=refs['prompt']['id']
    elif case=='source_id':mappings[0]['target_asset_id']=src['retrieve']['id']
    elif case=='stale_version':mappings[0]['expected_target_asset_version']=1;expected=409
    else:
        with ctx['db'].begin() as db:
            row=db.get(WorkspaceAsset,refs['retrieve']['id'] if case=='draft_target' else src['retrieve']['id'])
            if case=='draft_target':row.status='draft'
            elif case=='source_changed':row.version+=1;expected=409
            else:row.status='archived';expected=409
    result=copy(ctx,body);assert result.status_code==expected,result.text
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(WorkspaceAsset).where(WorkspaceAsset.env=='production',WorkspaceAsset.kind=='workflow'))==0
        assert db.scalar(select(func.count()).select_from(WorkbenchRun).where(WorkbenchRun.kind=='environment_asset_copy'))==0

def test_reference_lookup_is_owner_assigned_active_scoped_and_metadata_only(ctx):
    target,flow,src,refs,body=fixtures(ctx)
    url=URL+'/target/production/references?expected_version='+str(target['version'])
    response=ctx['client'].get(url,headers=headers(current(ctx)));assert response.status_code==200,response.text
    assert {row['id'] for row in response.json()['items']}=={row['id'] for row in refs.values()}
    assert all(set(row)=={'id','name','kind','version'} for row in response.json()['items'])
    assert 'Different target knowledge' not in response.text
    assert ctx['client'].get(URL+'/target/production/references?expected_version=1',headers=headers(current(ctx))).status_code==409
    assert control(ctx,inventory(ctx)).status_code==200
    assert ctx['client'].get(url,headers=headers(current(ctx))).status_code==403
    assert control(ctx,inventory(ctx),'resume').status_code==200
    with ctx['db'].begin() as db:db.delete(db.get(EnvironmentAssignment,(current(ctx)['user']['id'],'northstar','production')))
    assert ctx['client'].get(url,headers=headers(current(ctx))).status_code==403
    auth(ctx,'auditor');assert ctx['client'].get(url,headers=headers(current(ctx))).status_code==403
    auth(ctx,org='other');assert ctx['client'].get(url,headers=headers(current(ctx))).status_code==403
    auth(ctx);ctx['settings'].mode='pilot';assert ctx['client'].get(url,headers=headers(current(ctx))).status_code==403

def test_standalone_receipt_fingerprint_remains_compatible_with_previous_release(ctx):
    target=prepare(ctx);asset=source(ctx);body=payload(asset,target)
    result=copy(ctx,body);assert result.status_code==201,result.text
    # This is the exact pre-workflow fingerprint protocol, with no mapping field.
    with ctx['db'].begin() as db:
        row=db.get(WorkbenchRun,result.json()['id'])
        row.result={**row.result,'fingerprint':digest(canonical(body))}
    assert copy(ctx,body).json()==result.json()
    assert copy(ctx,{**body,'reference_mappings':[]}).json()==result.json()
    assert copy(ctx,{**body,'reference_mappings':[{'node_id':'prompt','target_asset_id':asset['id'],'expected_target_asset_version':2}]},key='unexpected-mapping-001').status_code==422

def test_workflow_without_linked_designs_needs_no_mapping_and_still_starts_as_draft(ctx):
    target=prepare(ctx);flow=create(ctx,'workflow',{'nodes':[{'id':'input','kind':'input','label':'Input'},{'id':'output','kind':'output','label':'Output'}]},'Standalone workflow')
    response=copy(ctx,payload(flow,target));assert response.status_code==201,response.text
    with ctx['db']() as db:assert db.get(WorkspaceAsset,response.json()['target_asset_id']).status=='draft'
