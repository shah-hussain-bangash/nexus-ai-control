"""Disposable storage/migration checks; no model or application-data backup."""
import copy
from dataclasses import replace
import shutil
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func,inspect,delete
from conftest import auth
from test_hybrid import upload
from test_document_lifecycle import replace_body
from test_documents import payload
from nexus.app import create_app
from nexus.backup import backup,inspect_backup
from nexus.cli import seed
from nexus.config import Settings
from nexus.db import (NeuralIndex,NeuralVector,DocumentChunk,User,KnowledgeDocument,SchemaVersion,CURRENT_SCHEMA,migrate,public)
from nexus.environments import assign_staging
from nexus.neural_index_store import create_index,describe_index,rank_index,remove_index
from nexus.runtime_context import bind_runtime_context

MODEL='synthetic-embedding:test';DIGEST='1'*64

def actor(db,role='owner',org='northstar',env='staging'):
    user=db.scalar(select(User).where(User.org_id==org,User.role==role))
    bind_runtime_context(db,org,env);return user

def entries(ctx,doc):
    with ctx['db']() as db:
        rows=db.scalars(select(DocumentChunk).where(DocumentChunk.document_id==doc['id']).order_by(DocumentChunk.position)).all()
        return [{'document_id':r.document_id,'document_version':r.document_version,'position':r.position,'sha256':r.content_hash,'vector':[3.,4.]} for r in rows]

def create(ctx,doc,role='owner',key='synthetic-index-key-001'):
    values=entries(ctx,doc)
    with ctx['db'].begin() as db:
        return create_index(db,actor(db,role),name='Synthetic index',model=MODEL,model_digest=DIGEST,entries=values,key=key)

def rank(ctx,index,role='owner',org='northstar',env='staging',**changes):
    with ctx['db'].begin() as db:
        return rank_index(db,actor(db,role,org,env),index['id'],[3,4],model=MODEL,model_digest=DIGEST,**changes)

def test_persisted_index_ranks_current_sources_without_exposing_vectors(ctx):
    doc=upload(ctx,'Synthetic indexed procurement source العربية')
    index=create(ctx,doc);result=rank(ctx,index)
    assert index['dimensions']==2 and index['entry_count']==1 and index['status']=='ready'
    assert result['items'][0]['document_id']==doc['id'] and result['items'][0]['score']==1
    assert not result['query_vector_stored'] and result['provider_calls']==0
    assert 'vector' not in str(index) and 'vector' not in result['items'][0]
    with ctx['db']() as db:assert 'vector' not in public(db.scalar(select(NeuralVector)))
    assert create(ctx,doc)['id']==index['id']
    with ctx['db'].begin() as db:
        with pytest.raises(HTTPException) as error:
            create_index(db,actor(db),name='Changed synthetic name',model=MODEL,model_digest=DIGEST,entries=entries(ctx,doc),key='synthetic-index-key-001')
        assert error.value.status_code==409

@pytest.mark.parametrize('change',['access','content','delete'])
def test_normal_document_updates_atomically_purge_all_vectors_and_invalidate_snapshot(ctx,change):
    doc=upload(ctx,'Synthetic source to invalidate');index=create(ctx,doc);headers,_=auth(ctx)
    if change=='access':response=ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':['auditor'],'allowed_users':[],'note':'Change synthetic source reader set.'})
    elif change=='content':response=ctx['client'].put('/v1/documents/'+doc['id']+'/content',headers={**headers,'Idempotency-Key':'replace-vector-source-001'},json=replace_body(text='New synthetic source'))
    else:response=ctx['client'].request('DELETE','/v1/documents/'+doc['id'],headers=headers,json={'expected_version':1,'note':'Remove synthetic indexed source.'})
    assert response.status_code==200,response.text
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(NeuralVector))==0
        saved=db.get(NeuralIndex,index['id']);assert saved.status=='invalidated' and saved.version==2
    with pytest.raises(HTTPException) as error:rank(ctx,index)
    assert error.value.status_code==409 and error.value.detail['code']=='INDEX_INVALIDATED'

def test_failed_document_update_keeps_index_and_vectors(ctx):
    doc=upload(ctx,'Synthetic stable source');index=create(ctx,doc);headers,_=auth(ctx)
    response=ctx['client'].request('DELETE','/v1/documents/'+doc['id'],headers=headers,json={'expected_version':9,'note':'Stale synthetic deletion request.'})
    assert response.status_code==409 and rank(ctx,index)['items']


def test_invalidation_purges_whole_affected_snapshot_and_preserves_other_indexes(ctx):
    first=upload(ctx,'Synthetic first source');second=upload(ctx,'Synthetic second source')
    with ctx['db'].begin() as db:
        combined=create_index(db,actor(db),name='Two source snapshot',model=MODEL,model_digest=DIGEST,
            entries=entries(ctx,first)+entries(ctx,second),key='combined-vector-key-001')
    independent=create(ctx,second,key='independent-vector-key-001');headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+first['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Invalidate combined synthetic snapshot.'}).status_code==200
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(NeuralVector).where(NeuralVector.index_id==combined['id']))==0
    assert rank(ctx,independent)['items'][0]['document_id']==second['id']


def test_persistent_ranking_groups_documents_before_top_k(ctx):
    first=upload(ctx,('Synthetic repeated passage '*120).strip());second=upload(ctx,'Synthetic independent passage')
    with ctx['db'].begin() as db:
        index=create_index(db,actor(db),name='Document diversity',model=MODEL,model_digest=DIGEST,
            entries=entries(ctx,first)+entries(ctx,second),key='diverse-vector-key-001')
    value=rank(ctx,index,one_per_document=True,top_k=2)
    assert {item['document_id'] for item in value['items']}=={first['id'],second['id']}
    assert all(item['position']==0 for item in value['items'])


def test_workspace_capacity_requires_explicit_removal(ctx,monkeypatch):
    monkeypatch.setattr('nexus.neural_index_store.MAX_INDEXES',1)
    doc=upload(ctx,'Synthetic quota source');create(ctx,doc)
    with pytest.raises(HTTPException) as error:create(ctx,doc,key='second-quota-index-key')
    assert error.value.status_code==429

def test_owner_account_environment_and_source_revocation_are_enforced(ctx):
    with ctx['db'].begin() as db:
        user=User(id='synthetic-vector-reader',org_id='northstar',email='vectors@test.invalid',name='Vector evaluator',role='engineer',password_hash='not-a-login-hash')
        db.add(user);db.flush();assign_staging(db,user)
    doc=upload(ctx,'Synthetic shared source',['engineer']);index=create(ctx,doc,role='engineer')
    assert rank(ctx,index,role='engineer')['items']
    for options in ({'role':'auditor'},{'org':'other'},{'env':'production'}):
        with pytest.raises(HTTPException) as error:rank(ctx,index,**options)
        assert error.value.status_code==404
    # Even a direct DB change that misses eager invalidation is blocked at use.
    with ctx['db'].begin() as db:db.get(KnowledgeDocument,doc['id']).allowed_roles=[]
    with pytest.raises(HTTPException) as error:rank(ctx,index,role='engineer')
    assert error.value.status_code==409

def test_inactive_actor_and_model_or_storage_tampering_fail_closed(ctx):
    doc=upload(ctx,'Synthetic source');index=create(ctx,doc)
    with ctx['db'].begin() as db:
        user=actor(db)
        with pytest.raises(HTTPException) as error:rank_index(db,user,index['id'],[3,4],model=MODEL,model_digest='2'*64)
        assert error.value.status_code==409
    with ctx['db'].begin() as db:db.scalar(select(NeuralVector)).vector=[1.,0.]
    with pytest.raises(HTTPException) as error:rank(ctx,index)
    assert error.value.status_code==409
    with ctx['db'].begin() as db:db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner')).active=0
    with pytest.raises(HTTPException) as error:rank(ctx,index)
    assert error.value.status_code==404

def test_purge_and_invalidation_roll_back_with_failed_source_transaction(ctx):
    from nexus.neural_index_store import invalidate_source
    doc=upload(ctx,'Synthetic rollback source');index=create(ctx,doc)
    with pytest.raises(RuntimeError):
        with ctx['db'].begin() as db:
            actor(db);invalidate_source(db,'northstar','staging',doc['id']);raise RuntimeError('synthetic rollback')
    assert rank(ctx,index)['items']

def test_removal_requires_version_and_can_remove_invalidated_metadata(ctx):
    doc=upload(ctx,'Synthetic removable source');index=create(ctx,doc)
    with ctx['db'].begin() as db:
        with pytest.raises(HTTPException) as error:remove_index(db,actor(db),index['id'],expected_version=2,note='Reviewed synthetic removal.')
        assert error.value.status_code==409
    headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Invalidate before synthetic cleanup.'}).status_code==200
    with ctx['db'].begin() as db:
        user=actor(db);assert describe_index(db,user,index['id'])['version']==2
        assert remove_index(db,user,index['id'],expected_version=2,note='Reviewed synthetic removal.')['status']=='removed'
    with ctx['db']() as db:assert db.get(NeuralIndex,index['id']) is None and db.scalar(select(func.count()).select_from(NeuralVector))==0

@pytest.mark.parametrize('vector',[[],[0,0],[True,1],[float('nan'),1],[float('inf'),1],[1]*4097,[10**400,1]])
def test_vector_bounds_reject_invalid_values_before_storage(ctx,vector):
    doc=upload(ctx,'Synthetic vector-bound source');value=entries(ctx,doc);value[0]['vector']=vector
    with pytest.raises(HTTPException):
        with ctx['db'].begin() as db:create_index(db,actor(db),name='Bounded index',model=MODEL,model_digest=DIGEST,entries=value,key='bounded-vector-key-001')
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralIndex))==0

def test_schema11_upgrade_preserves_accounts_sources_and_is_idempotent(ctx):
    doc=upload(ctx,'Synthetic migration source العربية');engine=ctx['app'].state.engine
    with ctx['db']() as db:before=[(u.id,u.password_hash,u.active) for u in db.scalars(select(User).order_by(User.id))]
    with engine.begin() as connection:
        NeuralVector.__table__.drop(connection);NeuralIndex.__table__.drop(connection)
        connection.execute(delete(SchemaVersion).where(SchemaVersion.version==12))
    migrate(engine,ctx['db']);migrate(engine,ctx['db'])
    with ctx['db']() as db:
        assert before==[(u.id,u.password_hash,u.active) for u in db.scalars(select(User).order_by(User.id))]
        assert db.get(KnowledgeDocument,doc['id']).content=='Synthetic migration source العربية'
        assert db.scalar(select(func.max(SchemaVersion.version)))==12==CURRENT_SCHEMA
    assert create(ctx,doc)['status']=='ready'

def test_failed_schema12_upgrade_rolls_back_new_tables_and_marker(ctx,monkeypatch):
    engine=ctx['app'].state.engine
    with engine.begin() as connection:
        NeuralVector.__table__.drop(connection);NeuralIndex.__table__.drop(connection)
        connection.execute(delete(SchemaVersion).where(SchemaVersion.version==12))
    original=NeuralVector.__table__.create
    def fail(*args,**kwargs):raise RuntimeError('synthetic migration interruption')
    monkeypatch.setattr(NeuralVector.__table__,'create',fail)
    with pytest.raises(RuntimeError):migrate(engine,ctx['db'])
    with ctx['db']() as db:assert db.scalar(select(func.max(SchemaVersion.version)))==11
    assert 'neural_indexes' not in inspect(engine).get_table_names()
    monkeypatch.setattr(NeuralVector.__table__,'create',original);migrate(engine,ctx['db'])
    assert 'neural_vectors' in inspect(engine).get_table_names()

def test_synthetic_backup_restores_stored_index_and_functioning_source_api(tmp_path,monkeypatch):
    # Always SQLite, including PostgreSQL CI; all paths belong to this fixture.
    settings=Settings(database_url='sqlite:///'+(tmp_path/'source.sqlite3').as_posix(),mock_database=str(tmp_path/'business.sqlite3'),secret='synthetic-session-'+'x'*48,agent_secret='synthetic-agent-'+'y'*48,frontend_dir=str(tmp_path/'no-ui'))
    from test_authorized_neural_search import configure,transport
    from nexus import neural_index_runtime,neural_worker
    configure({'settings':settings})
    mock,calls=transport()
    monkeypatch.setattr(neural_index_runtime,'compute',lambda payload:neural_worker.embedding_batch(payload,transport=mock))
    app=create_app(settings);migrate(app.state.engine,app.state.factory);seed(app.state.factory,'Synthetic-vector-test-password!')
    with TestClient(app) as client:
        ctx={'app':app,'db':app.state.factory,'settings':settings,'client':client}
        doc=upload(ctx,'Synthetic restored index source العربية');index=create(ctx,doc)
    app.state.engine.dispose()
    destination=tmp_path/'backup';backup(settings,destination,quiesced=True)
    assert inspect_backup(destination)['checksums_valid']
    restored=tmp_path/'restore';restored.mkdir();shutil.copy2(destination/'control.sqlite3',restored/'control.sqlite3')
    recovered_settings=replace(settings,database_url='sqlite:///'+(restored/'control.sqlite3').as_posix(),mock_database=str(restored/'business.sqlite3'))
    recovered=create_app(recovered_settings)
    try:
        with TestClient(recovered) as client:
            ctx={'app':recovered,'db':recovered.state.factory,'settings':recovered_settings,'client':client}
            auth(ctx);assert client.get('/health/ready').json()['schema_version']==12
            assert client.get('/v1/documents/'+doc['id']).json()['content']=='Synthetic restored index source العربية'
            assert rank(ctx,index)['items'][0]['document_id']==doc['id']
            headers,_=auth(ctx);headers['Idempotency-Key']='restored-index-query-0001'
            response=client.post('/v1/neural-indexes/search',headers=headers,json={'index_id':index['id'],'query':'synthetic restored pump'})
            assert response.status_code==201,response.text
            assert response.json()['items'][0]['document_id']==doc['id']
            headers,_=auth(ctx,'auditor');headers['Idempotency-Key']='restored-auditor-index-001'
            assert client.post('/v1/neural-indexes/search',headers=headers,json={'index_id':index['id'],'query':'synthetic restored pump'}).status_code==404
            assert len(calls)==4
            headers,_=auth(ctx,'auditor')
            assert client.post('/v1/documents',headers={**headers,'Idempotency-Key':'auditor-rejected-source'},json=payload()).status_code==403
            with pytest.raises(HTTPException) as error:rank(ctx,index,role='auditor')
            assert error.value.status_code==404
    finally:recovered.state.engine.dispose()
