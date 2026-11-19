"""Schema 11 request namespaces. No key, row, or budget value is rewritten."""
from contextlib import contextmanager
import re
from sqlalchemy import MetaData, UniqueConstraint, inspect, select, func
from sqlalchemy.schema import CreateTable, AddConstraint

LEGACY_KEYS={
    'durable_runs':('org_id','author_id','idem_key'),
    'knowledge_documents':('org_id','author_id','idem_key'),
    'document_updates':('org_id','author_id','idem_key'),
    'retrieval_checks':('org_id','author_id','idem_key'),
    'ingestion_jobs':('org_id','author_id','idem_key'),
    'inference_calls':('org_id','key_hash'),
}


@contextmanager
def migration_connection(engine):
    if engine.dialect.name!='sqlite':
        with engine.begin() as connection:yield connection
        return
    # Foreign keys cannot be toggled within a SQLite transaction. This connection
    # is checked out exclusively, and BEGIN IMMEDIATE serializes schema writers.
    # Explicit BEGIN also makes DDL transactional under sqlite3 legacy mode.
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql('PRAGMA foreign_keys=OFF');connection.commit()
            if connection.exec_driver_sql('PRAGMA foreign_keys').scalar()!=0:
                raise RuntimeError('SQLite migration could not acquire its foreign-key rebuild mode.')
            connection.commit()
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            yield connection
            if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Migration failed foreign-key validation; no upgrade was committed.')
            connection.commit()
        except BaseException:
            connection.rollback();raise
        finally:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON');connection.commit()
            if connection.exec_driver_sql('PRAGMA foreign_keys').scalar()!=1:
                raise RuntimeError('SQLite foreign-key enforcement could not be restored.')
            connection.commit()


def namespace(old):return (old[0],'env',*old[1:])


def _uniques(connection,name):
    return inspect(connection).get_unique_constraints(name)


def _sqlite_layout(connection,table,old):
    reader=inspect(connection)
    definition=connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table.name,)).scalar() or ''
    if re.search(r'\bCOLLATE\b|\bWITHOUT\s+ROWID\b|\bON\s+CONFLICT\b',definition,re.IGNORECASE):
        raise RuntimeError('Custom request table options require operator migration review.')
    columns=reader.get_columns(table.name)
    if [c['name'] for c in columns]!=list(table.c.keys()):
        raise RuntimeError('Custom request table columns require operator migration review.')
    for column in columns:
        expected=table.c[column['name']]
        if (column['nullable']!=expected.nullable or column['type']._type_affinity!=expected.type._type_affinity
            or column['default'] is not None or column.get('computed') or column.get('identity')):
            raise RuntimeError('Custom request table columns require operator migration review.')
    if reader.get_check_constraints(table.name):
        raise RuntimeError('Custom request table checks require operator migration review.')
    pk=reader.get_pk_constraint(table.name)['constrained_columns']
    if pk!=[c.name for c in table.primary_key]:raise RuntimeError('Unexpected request table primary key.')
    expected_fks={(tuple(c.parent.name for c in fk.elements),tuple(c.column.table.name for c in fk.elements),tuple(c.column.name for c in fk.elements)) for fk in table.foreign_key_constraints}
    actual_fks={(tuple(fk['constrained_columns']),tuple([fk['referred_table']]*len(fk['referred_columns'])),tuple(fk['referred_columns'])) for fk in reader.get_foreign_keys(table.name)}
    if actual_fks!=expected_fks or any(fk.get('options') for fk in reader.get_foreign_keys(table.name)):
        raise RuntimeError('Custom request table foreign keys require operator migration review.')
    expected={tuple(c.name for c in rule.columns) for rule in table.constraints if isinstance(rule,UniqueConstraint)}
    observed={tuple(rule['column_names']) for rule in _uniques(connection,table.name)}
    legacy=(expected-{namespace(old)})|{old}
    if observed not in (expected,legacy,expected|{old}):
        raise RuntimeError('Custom request table uniqueness requires operator migration review.')


def _sqlite_rebuild(connection,table,metadata):
    quote=connection.dialect.identifier_preparer.quote
    temporary='_nexus_v11_'+table.name
    if temporary in inspect(connection).get_table_names():
        raise RuntimeError('A request migration scratch table already exists; operator review is required.')
    copy=table.to_metadata(metadata,name=temporary)
    connection.execute(CreateTable(copy))
    columns=', '.join(quote(c.name) for c in table.columns)
    count=connection.scalar(select(func.count()).select_from(table))
    copied=connection.exec_driver_sql(f'INSERT INTO {quote(temporary)} ({columns}) SELECT {columns} FROM {quote(table.name)}')
    if copied.rowcount!=count:raise RuntimeError('Request migration row copy was incomplete.')
    connection.exec_driver_sql(f'DROP TABLE {quote(table.name)}')
    connection.exec_driver_sql(f'ALTER TABLE {quote(temporary)} RENAME TO {quote(table.name)}')


def migrate_request_keys(connection,base_metadata):
    targets=[]
    for name,old in LEGACY_KEYS.items():
        observed={tuple(c['column_names']) for c in _uniques(connection,name)}
        if old not in observed and namespace(old) not in observed:
            raise RuntimeError('Expected request key constraint is missing; operator review is required.')
        if old in observed:targets.append(base_metadata.tables[name])
    if connection.dialect.name=='sqlite':
        if targets and inspect(connection).get_view_names():
            raise RuntimeError('SQLite views require operator migration review before rebuilding request tables.')
        metadata=MetaData()
        for table in base_metadata.sorted_tables:table.to_metadata(metadata)
        saved=[]
        # Preflight every target before changing any table. Preserve explicit
        # indexes/triggers verbatim; autoindexes follow the new constraints.
        for table in targets:
            _sqlite_layout(connection,table,LEGACY_KEYS[table.name])
            saved.extend(connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name",(table.name,)).scalars())
        for table in targets:_sqlite_rebuild(connection,table,metadata)
        for sql in saved:connection.exec_driver_sql(sql)
    elif connection.dialect.name=='postgresql':
        quote=connection.dialect.identifier_preparer.quote
        for table in targets:
            old=LEGACY_KEYS[table.name]
            rules=_uniques(connection,table.name)
            for rule in rules:
                if tuple(rule['column_names'])==old:
                    connection.exec_driver_sql(f'ALTER TABLE {quote(table.name)} DROP CONSTRAINT {quote(rule["name"])}')
            if not any(tuple(rule['column_names'])==namespace(old) for rule in rules):
                rule=next(c for c in table.constraints if isinstance(c,UniqueConstraint) and tuple(x.name for x in c.columns)==namespace(old))
                # Keep the source metadata usable for later fresh databases in
                # this process; AddConstraint otherwise suppresses CREATE TABLE.
                connection.execute(AddConstraint(rule,isolate_from_table=False))
    else:raise RuntimeError('Unsupported database for request-key migration.')
    for name,old in LEGACY_KEYS.items():
        rules={tuple(c['column_names']) for c in _uniques(connection,name)}
        indexes=inspect(connection).get_indexes(name)
        if old in rules or namespace(old) not in rules or any(i['unique'] and tuple(i['column_names'])==old for i in indexes):
            raise RuntimeError('Request namespace verification failed; no upgrade was committed.')
