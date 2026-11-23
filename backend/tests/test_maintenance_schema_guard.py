"""Maintenance previews must not initialize, migrate or delete application data."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace
import pytest
from sqlalchemy import delete,select
from sqlalchemy.exc import SQLAlchemyError
from nexus import cli,operations
from nexus.db import (Audit,CURRENT_SCHEMA,Export,OIDCTransaction,SchemaVersion,
    SessionRecord,SessionRuntimeContext,User)


def fixture_records(ctx):
    stamp=time.time()
    with ctx['db'].begin() as db:
        user=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
        for name,expires in [('expired',stamp-7200),('live',stamp+86400)]:
            db.add(SessionRecord(id='maintenance-'+name,user_id=user.id,csrf='fixture',expires=expires))
        db.flush()
        for name in ('expired','live'):
            db.add(SessionRuntimeContext(session_id='maintenance-'+name,user_id=user.id,org_id=user.org_id,environment='staging'))
        for name,expires in [('expired',stamp-7200),('grace',stamp-10),('live',stamp+86400)]:
            db.add(OIDCTransaction(id='maintenance-'+name,binding_hash='fixture',nonce='fixture',verifier_ciphertext='fixture',expires=expires))
        for name,expires in [('expired',stamp-7200),('live',stamp+86400)]:
            db.add(Export(id='maintenance-'+name,org_id=user.org_id,owner_id=user.id,records=[],expires=expires))
        db.add(Audit(id='maintenance-evidence',org_id=user.org_id,event='keep',actor='fixture',created=stamp))


def rows(ctx,models=(SessionRecord,SessionRuntimeContext,OIDCTransaction,Export,Audit,SchemaVersion,User)):
    with ctx['db']() as db:
        return {model.__tablename__:sorted(repr(tuple(row)) for row in db.execute(select(model.__table__))) for model in models}


def test_preview_enforces_read_only_access_and_preserves_all_records(ctx,monkeypatch):
    fixture_records(ctx);before=rows(ctx);original=operations.housekeeping;checked=[]
    def read_only(factory,*,apply):
        assert not apply
        with pytest.raises(SQLAlchemyError):
            with factory.begin() as db:db.execute(delete(SessionRecord))
        checked.append(True)
        return original(factory,apply=False)
    monkeypatch.setattr(operations,'housekeeping',read_only)
    report=operations.maintenance(ctx['settings'])
    assert checked==[True] and report['expired_records']=={'sessions':1,'oidc_transactions':1,'exports':1}
    assert not report['applied'] and not report['audit_evidence_deleted'] and rows(ctx)==before


@pytest.mark.parametrize('apply',[False,True])
def test_cli_routes_maintenance_without_initialization_or_migration(ctx,monkeypatch,capsys,apply):
    fixture_records(ctx);before=rows(ctx)
    monkeypatch.setattr(cli.Settings,'from_env',lambda:ctx['settings'])
    def forbidden(*args,**kwargs):pytest.fail('Maintenance entered initialization or migration')
    for name in ('database','migrate','seed'):monkeypatch.setattr(cli,name,forbidden)
    monkeypatch.setattr(sys,'argv',['nexus','maintenance',*(['--apply'] if apply else [])])
    cli.main();report=json.loads(capsys.readouterr().out)
    assert report['applied']==apply and report['expired_records']=={'sessions':1,'oidc_transactions':1,'exports':1}
    if not apply:assert rows(ctx)==before
    else:
        with ctx['db']() as db:
            assert db.get(SessionRecord,'maintenance-expired') is None and db.get(SessionRecord,'maintenance-live')
            assert db.get(SessionRuntimeContext,'maintenance-expired') is None and db.get(SessionRuntimeContext,'maintenance-live')
            assert db.get(OIDCTransaction,'maintenance-grace') and db.get(OIDCTransaction,'maintenance-live')
            assert db.get(Export,'maintenance-live') and db.get(Audit,'maintenance-evidence')
        after=rows(ctx)
        for model in (Audit,SchemaVersion,User):assert after[model.__tablename__]==before[model.__tablename__]


@pytest.mark.parametrize('apply',[False,True])
@pytest.mark.parametrize('version',[CURRENT_SCHEMA-1,CURRENT_SCHEMA+1])
def test_wrong_schema_is_rejected_without_upgrade_or_cleanup(ctx,apply,version):
    fixture_records(ctx)
    with ctx['db'].begin() as db:
        db.execute(delete(SchemaVersion));db.add(SchemaVersion(version=version))
    before=rows(ctx)
    with pytest.raises(RuntimeError,match='current database schema'):operations.maintenance(ctx['settings'],apply=apply)
    assert rows(ctx)==before


def test_cleanup_failure_rolls_back_earlier_deletes_and_hides_sql(ctx):
    fixture_records(ctx)
    with ctx['db'].begin() as db:Export.__table__.drop(db.connection())
    models=(SessionRecord,SessionRuntimeContext,OIDCTransaction,Audit,SchemaVersion,User);before=rows(ctx,models)
    with pytest.raises(RuntimeError,match='cleanup completion was not confirmed') as error:
        operations.maintenance(ctx['settings'],apply=True)
    assert rows(ctx,models)==before and error.value.__suppress_context__
    assert 'DELETE FROM' not in str(error.value) and 'exports' not in str(error.value)


@pytest.mark.parametrize('apply',[False,True])
@pytest.mark.parametrize('kind',['missing','memory','empty','old','query'])
def test_sqlite_guard_never_creates_or_upgrades_files(tmp_path,apply,kind):
    source=tmp_path/'absent-parent'/'control.db'
    if kind in ('empty','old'):
        source.parent.mkdir()
        with closing(sqlite3.connect(source)) as db:
            if kind=='old':
                db.execute('CREATE TABLE schema_versions (version INTEGER PRIMARY KEY)')
                db.execute('INSERT INTO schema_versions VALUES (?)',(CURRENT_SCHEMA-1,));db.commit()
    before=source.read_bytes() if source.is_file() else None
    url='sqlite:///'+source.as_posix()
    if kind=='memory':url='sqlite:///:memory:'
    elif kind=='query':url+='?mode=rwc'
    with pytest.raises(RuntimeError):operations.maintenance(SimpleNamespace(database_url=url),apply=apply)
    if before is None:assert not source.exists() and not source.parent.exists()
    else:assert source.read_bytes()==before


@pytest.mark.parametrize('apply',[False,True])
def test_sqlite_disappearance_after_preflight_never_recreates_source(tmp_path,monkeypatch,apply):
    source=tmp_path/'control.db'
    with closing(sqlite3.connect(source)) as db:db.execute('CREATE TABLE fixture (id INTEGER)')
    original=sqlite3.connect;calls=[]
    def disappeared(*args,**kwargs):
        source.unlink();calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(sqlite3,'connect',disappeared)
    with pytest.raises(RuntimeError,match='cleanup completion was not confirmed'):
        operations.maintenance(SimpleNamespace(database_url='sqlite:///'+source.as_posix()),apply=apply)
    assert calls and not source.exists()
