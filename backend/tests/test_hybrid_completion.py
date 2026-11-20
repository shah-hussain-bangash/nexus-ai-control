from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import update, text
from sqlalchemy.exc import OperationalError
from conftest import auth
from test_hybrid import upload
from nexus import hybrid
from nexus.db import KnowledgeDocument, Organization, WorkbenchRun
from nexus.hybrid_worker import rank


def ordered_source_change(ctx, identifier, command, short_deadline=False):
    """Use the same workspace-first ordering as a source-management request."""
    try:
        with ctx['db'].begin() as db:
            if short_deadline:
                if db.bind.dialect.name=='postgresql':db.execute(text("SET LOCAL lock_timeout = '200ms'"))
                else:db.execute(text('PRAGMA busy_timeout=200'))
            db.execute(update(Organization).where(Organization.id=='northstar').values(name=Organization.name))
            source=db.get(KnowledgeDocument,identifier)
            if command=='revoke':source.allowed_roles=[]
            else:source.status='deleted';source.content=''
            source.version+=1
        return 'committed'
    except OperationalError as error:
        original=error.orig
        if getattr(original,'sqlstate',None)=='55P03' or getattr(original,'sqlite_errorcode',None) in (5,6):return 'blocked'
        raise


@pytest.mark.parametrize('command',['revoke','delete'])
def test_source_write_cannot_cross_completion_check_and_saved_response(ctx,monkeypatch,command):
    source=upload(ctx,'car vehicle engine road',['auditor'])
    monkeypatch.setattr(hybrid,'compute',rank)
    original=hybrid.can_read;attempts=[]
    with ThreadPoolExecutor(max_workers=1) as pool:
        def during_check(document,user,environment):
            allowed=original(document,user,environment)
            if not attempts:
                # The completion path has already loaded the source and evaluated its ACL.
                # Try to commit a revocation before it saves/serializes that result.
                future=pool.submit(ordered_source_change,ctx,source['id'],command,True)
                attempts.append(future.result(timeout=5))
            return allowed
        monkeypatch.setattr(hybrid,'can_read',during_check)
        h,_=auth(ctx,'auditor');h['Idempotency-Key']='completion-race-search-001'
        response=ctx['client'].post('/v1/hybrid-search',headers=h,json={'query':'car','dimensions':2})
    assert response.status_code==201,response.text
    result=response.json()
    assert not (attempts==['committed'] and result['items']), 'A revoked or deleted source excerpt escaped after its access change committed'
    assert attempts==['blocked'],'A source write committed between authorization and search completion'
    assert result['status']=='completed' and len(result['items'])==1
    # Once completion commits, the source operation can commit and saved history
    # must apply that newer access/version state instead of replaying old excerpts.
    assert ordered_source_change(ctx,source['id'],command)=='committed'
    history=ctx['client'].get('/v1/hybrid-search/history/'+result['id'])
    assert history.status_code==200 and history.json()['items']==[]
    assert history.json()['withheld_stale_or_inaccessible']==1
    replay=ctx['client'].post('/v1/hybrid-search',headers=h,json={'query':'car','dimensions':2})
    assert replay.status_code==201 and replay.json()['id']==result['id'] and replay.json()['items']==[]


@pytest.mark.parametrize('command',['revoke','delete'])
def test_source_change_committed_during_compute_fences_complete_result(ctx,monkeypatch,command):
    source=upload(ctx,'car vehicle engine road',['auditor'])
    def changed(payload):
        result=rank(payload)
        assert ordered_source_change(ctx,source['id'],command,True)=='committed'
        return result
    monkeypatch.setattr(hybrid,'compute',changed)
    h,_=auth(ctx,'auditor');h['Idempotency-Key']='completion-before-search-001'
    response=ctx['client'].post('/v1/hybrid-search',headers=h,json={'query':'car','dimensions':2})
    assert response.status_code==201,response.text
    result=response.json();assert result['status']=='failed' and result['error_code']=='SOURCE_SCOPE_CHANGED' and result['items']==[]
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,result['id'])
        assert saved.result['hits']==[] and 'car vehicle engine road' not in str(saved.result)
