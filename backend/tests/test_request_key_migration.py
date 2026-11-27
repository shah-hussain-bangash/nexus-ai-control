"""Populated schema-10 fixtures, namespace enforcement, and transactional failure."""
import pytest
from sqlalchemy import MetaData, UniqueConstraint, select, inspect
from sqlalchemy.exc import IntegrityError
from conftest import auth
from nexus.db import (Base, SchemaVersion, DurableRun, KnowledgeDocument, DocumentUpdate,
                      RetrievalCheck, IngestionJob, InferenceCall, InferenceBudget, uid, migrate, CURRENT_SCHEMA)
from nexus.cli import seed
from nexus.request_key_migration import LEGACY_KEYS,namespace


def snapshot(ctx):
    with ctx['app'].state.engine.connect() as connection:
        return {table.name:[tuple(row) for row in connection.execute(select(table).order_by(*table.primary_key.columns))]
                for table in Base.metadata.sorted_tables if table.name!='schema_versions'}


@pytest.fixture
def legacy(ctx,monkeypatch):
    # Construct actual old unique constraints rather than merely changing the
    # schema-version marker on a new database. This is a disposable fixture.
    metadata=MetaData()
    for table in Base.metadata.sorted_tables:table.to_metadata(metadata)
    for name,columns in LEGACY_KEYS.items():
        table=metadata.tables[name]
        rule=next(c for c in table.constraints if isinstance(c,UniqueConstraint) and tuple(x.name for x in c.columns)==namespace(columns))
        table.constraints.remove(rule);table.append_constraint(UniqueConstraint(*columns))
    with ctx['app'].state.engine.begin() as connection:
        Base.metadata.drop_all(connection);metadata.create_all(connection)
        connection.execute(SchemaVersion.__table__.insert(),[{'version':v,'applied':float(v)} for v in range(1,11)])
    seed(ctx['db'],'Test-Only-Password-123!')
    from test_documents import upload
    from test_document_lifecycle import replace,run,suite
    from test_ingestion import create as intake
    from test_durable import create as flow
    from test_inference import setup
    import httpx
    doc=upload(ctx,text='Synthetic procurement evidence العربية remains intact.')
    assert replace(ctx,doc['id']).status_code==200
    assert run(ctx,suite(doc['id'])).status_code==201
    intake(ctx);flow(ctx,review=False,purchase=False)
    headers,body,sent=setup(ctx,monkeypatch,lambda req:httpx.Response(500))
    result=ctx['client'].post('/v1/inference',headers=headers,json=body)
    assert result.status_code==200 and result.json()['status']=='unknown'
    return {'ctx':ctx,'headers':headers,'before':snapshot(ctx),'sent':sent,'doc':doc['id']}


def assert_namespace(ctx,new):
    with ctx['app'].state.engine.connect() as connection:
        for name,old in LEGACY_KEYS.items():
            rules={tuple(r['column_names']) for r in inspect(connection).get_unique_constraints(name)}
            assert (namespace(old) if new else old) in rules,name
            assert (old if new else namespace(old)) not in rules,name


def assert_foreign_keys_on(ctx):
    if ctx['app'].state.engine.dialect.name=='sqlite':
        with ctx['app'].state.engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar()==1
            assert not connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()


def test_populated_upgrade_preserves_all_records_receipts_sessions_and_budget(legacy):
    ctx=legacy['ctx'];assert_namespace(ctx,False)
    migrate(ctx['app'].state.engine,ctx['db']);migrate(ctx['app'].state.engine,ctx['db'])
    assert_namespace(ctx,True);assert_foreign_keys_on(ctx)
    assert snapshot(ctx)==legacy['before']
    assert ctx['client'].get('/health/ready').json()['schema_version']==CURRENT_SCHEMA
    assert ctx['client'].get('/v1/me').status_code==200
    with ctx['db']() as db:
        doc=db.scalar(select(KnowledgeDocument));update=db.scalar(select(DocumentUpdate))
        paths=[('/v1/documents/recover',doc.idem_key,doc.id),
               ('/v1/documents/'+doc.id+'/updates/recover',update.idem_key,doc.id)]
        for model,path in [(DurableRun,'/v1/agent-runs/recover'),(RetrievalCheck,'/v1/retrieval-checks/recover'),(IngestionJob,'/v1/ingestion-jobs/recover')]:
            row=db.scalar(select(model));paths.append((path,row.idem_key,row.id))
        call=db.scalar(select(InferenceCall));paths.append(('/v1/inference/recover','inference-request-0001',call.id))
    for path,key,expected in paths:
        response=ctx['client'].post(path,headers=legacy['headers'],json={'key':key})
        assert response.status_code==200 and response.json()['id']==expected,response.text
    assert len(legacy['sent'])==1
    assert snapshot(ctx)==legacy['before']


def test_each_runtime_namespace_allows_other_environment_but_rejects_same_context_duplicates(legacy):
    ctx=legacy['ctx'];migrate(ctx['app'].state.engine,ctx['db'])
    models=(DurableRun,KnowledgeDocument,DocumentUpdate,RetrievalCheck,IngestionJob,InferenceCall)
    production_doc=None
    for model in models:
        with ctx['db']() as db:
            original=db.scalar(select(model).where(model.env=='staging'))
            values={c.name:getattr(original,c.name) for c in model.__table__.columns}
        values.update(id=uid(),env='production')
        if model is DocumentUpdate:values['document_id']=production_doc
        with ctx['db'].begin() as db:db.add(model(**values))
        if model is KnowledgeDocument:production_doc=values['id']
        for environment in ('staging','production'):
            duplicate={**values,'id':uid(),'env':environment}
            if model is DocumentUpdate and environment=='staging':duplicate['document_id']=legacy['doc']
            with pytest.raises(IntegrityError):
                with ctx['db'].begin() as db:db.add(model(**duplicate));db.flush()
    # The budget remains workspace/month scoped. A second environment cannot
    # create a new allowance or release another reservation by duplicating it.
    with ctx['db']() as db:
        ledger=db.scalar(select(InferenceBudget));values={c.name:getattr(ledger,c.name) for c in ledger.__table__.columns}
    with pytest.raises(IntegrityError):
        with ctx['db'].begin() as db:db.add(InferenceBudget(**{**values,'id':uid(),'env':'production'}));db.flush()
    assert_foreign_keys_on(ctx)


def test_mid_upgrade_failure_rolls_back_tables_constraints_and_version(legacy,monkeypatch):
    ctx=legacy['ctx'];import nexus.request_key_migration as migration
    calls=0
    if ctx['app'].state.engine.dialect.name=='sqlite':
        original=migration._sqlite_rebuild
        def fail(connection,table,metadata):
            nonlocal calls
            original(connection,table,metadata);calls+=1
            if calls==2:raise RuntimeError('Synthetic migration interruption')
        monkeypatch.setattr(migration,'_sqlite_rebuild',fail)
    else:
        original=migration.AddConstraint
        def fail(rule,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('Synthetic migration interruption')
            return original(rule,**kwargs)
        monkeypatch.setattr(migration,'AddConstraint',fail)
    with pytest.raises(RuntimeError,match='Synthetic'):migrate(ctx['app'].state.engine,ctx['db'])
    assert calls==2 and snapshot(ctx)==legacy['before']
    assert_namespace(ctx,False);assert_foreign_keys_on(ctx)
    with ctx['db']() as db:assert db.get(SchemaVersion,11) is None and db.get(SchemaVersion,10)


def test_sqlite_rebuild_preserves_operator_index_trigger_and_does_not_replay_them(legacy):
    ctx=legacy['ctx'];engine=ctx['app'].state.engine
    if engine.dialect.name!='sqlite':pytest.skip('SQLite table rebuild contract.')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE migration_probe (id TEXT)')
        connection.exec_driver_sql('CREATE INDEX operator_document_title ON knowledge_documents (title)')
        connection.exec_driver_sql('CREATE TRIGGER operator_document_created AFTER INSERT ON knowledge_documents BEGIN INSERT INTO migration_probe (id) VALUES (NEW.id); END')
    migrate(engine,ctx['db'])
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT count(*) FROM migration_probe').scalar()==0
        assert 'operator_document_title' in {i['name'] for i in inspect(connection).get_indexes('knowledge_documents')}
    with ctx['db'].begin() as db:
        original=db.scalar(select(KnowledgeDocument))
        values={c.name:getattr(original,c.name) for c in original.__table__.columns}
        db.add(KnowledgeDocument(**{**values,'id':'trigger-proof','idem_key':'trigger-key'}))
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT count(*) FROM migration_probe').scalar()==1
    assert_foreign_keys_on(ctx)


def test_custom_sqlite_layout_is_rejected_without_changing_existing_data(legacy):
    ctx=legacy['ctx'];engine=ctx['app'].state.engine
    if engine.dialect.name!='sqlite':pytest.skip('SQLite custom layout preflight.')
    with engine.begin() as connection:connection.exec_driver_sql('ALTER TABLE knowledge_documents ADD COLUMN operator_note TEXT')
    with pytest.raises(RuntimeError,match='Custom request table columns'):migrate(engine,ctx['db'])
    assert snapshot(ctx)==legacy['before'];assert_namespace(ctx,False);assert_foreign_keys_on(ctx)
    with engine.connect() as connection:assert 'operator_note' in {c['name'] for c in inspect(connection).get_columns('knowledge_documents')}


def test_custom_old_unique_index_cannot_leave_a_partially_upgraded_namespace(legacy):
    ctx=legacy['ctx'];engine=ctx['app'].state.engine
    if engine.dialect.name!='sqlite':pytest.skip('SQLite explicit custom index verification.')
    with engine.begin() as connection:connection.exec_driver_sql('CREATE UNIQUE INDEX operator_old_namespace ON inference_calls (org_id,key_hash)')
    with pytest.raises(RuntimeError,match='namespace verification failed'):migrate(engine,ctx['db'])
    assert snapshot(ctx)==legacy['before'];assert_namespace(ctx,False);assert_foreign_keys_on(ctx)
    with engine.connect() as connection:
        assert 'operator_old_namespace' in {i['name'] for i in inspect(connection).get_indexes('inference_calls')}
