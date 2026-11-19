import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from conftest import auth
from nexus.db import Agent,Policy,Audit,KnowledgeDocument,WorkspaceEnvironment,EnvironmentAssignment,User
from nexus.runtime_context import bind_runtime_context,bound_runtime_context,runtime_environment,environment_user_allowed
from nexus.service import scoped,active_policy,audit
from nexus.runtime_operations import signals


def fixtures(ctx):
    with ctx['db'].begin() as db:
        owner=db.scalar(select(User).where(User.org_id=='northstar',User.role=='owner'))
        stage=db.scalar(select(Agent).where(Agent.org_id=='northstar',Agent.name=='Procurement Atlas'))
        production=Agent(org_id='northstar',env='production',name='Production-only agent',owner_id=owner.id,risk='low',status='active')
        db.add(production);db.add(Policy(org_id='northstar',env='production',version=42,active=1))
        db.add(KnowledgeDocument(org_id='northstar',env='production',author_id=owner.id,title='Production document',filename='production.txt',
            language='English',content='Synthetic source',content_hash='a'*64,byte_count=16,allowed_roles=[],allowed_users=[],status='indexed',idem_key='production-context-source',request_digest='b'*64))
        db.flush()
        return owner.id,stage.id,production.id


def test_bound_helpers_follow_context_without_falling_back_to_staging(ctx):
    owner,staging,production=fixtures(ctx)
    with ctx['db'].begin() as db:
        cached=db.get(Agent,production)
        bind_runtime_context(db,'northstar')
        assert runtime_environment(db,'northstar')=='staging'
        assert scoped(db,Agent,staging,'northstar').id==staging
        assert active_policy(db,'northstar').version==1
        with pytest.raises(HTTPException) as denied:scoped(db,Agent,production,'northstar')
        assert denied.value.status_code==404
        bind_runtime_context(db,'northstar','production')
        assert scoped(db,Agent,production,'northstar') is cached
        assert active_policy(db,'northstar').version==42
        with pytest.raises(HTTPException):scoped(db,Agent,staging,'northstar')
        audit(db,'northstar',owner,'test.production.bound')
    with ctx['db']() as db:
        row=db.scalar(select(Audit).where(Audit.event=='test.production.bound'))
        assert row.org_id=='northstar' and row.env=='production'


def test_unbound_background_helpers_require_explicit_context(ctx):
    owner,stage,production=fixtures(ctx)
    with ctx['db'].begin() as db:
        for operation in (lambda:scoped(db,Agent,stage,'northstar'),lambda:active_policy(db,'northstar'),lambda:audit(db,'northstar',owner,'test.unbound')):
            with pytest.raises(RuntimeError,match='explicit environment'):operation()
        assert scoped(db,Agent,production,'northstar',environment='production').id==production
        assert active_policy(db,'northstar',environment='production').version==42
        audit(db,'northstar',owner,'test.production.explicit',env='production')
        assert bound_runtime_context(db) is None
    with ctx['db']() as db:assert db.scalar(select(Audit).where(Audit.event=='test.production.explicit')).env=='production'


@pytest.mark.parametrize('org,environment',[('other',None),('northstar','production'),('northstar','../invalid')])
def test_explicit_context_cannot_override_authenticated_binding(ctx,org,environment):
    fixtures(ctx)
    with ctx['db']() as db:
        bind_runtime_context(db,'northstar')
        for operation in (lambda:runtime_environment(db,org,environment),lambda:active_policy(db,org,environment),
                          lambda:audit(db,org,'test','test.invalid',env=environment),lambda:signals(db,org,environment)):
            with pytest.raises(RuntimeError,match='does not match'):operation()
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.event=='test.invalid'))==0


@pytest.mark.parametrize('context',[('','staging'),('northstar','Production'),('northstar','../production'),('northstar',''),('northstar',None)])
def test_invalid_internal_bindings_are_rejected(ctx,context):
    with ctx['db']() as db:
        with pytest.raises(RuntimeError,match='Invalid runtime'):bind_runtime_context(db,*context)
        assert bound_runtime_context(db) is None


@pytest.mark.parametrize('corrupt',[None,False,'staging',(),('northstar',),('northstar','../bad')])
def test_corrupt_session_metadata_fails_closed_even_for_orm_queries(ctx,corrupt):
    with ctx['db']() as db:
        db.info['nexus_runtime_context']=corrupt
        with pytest.raises(RuntimeError):db.scalar(select(func.count()).select_from(Agent))


def test_context_scoped_signals_and_global_operator_signals_are_distinct(ctx):
    fixtures(ctx)
    with ctx['db']() as db:
        all_signals=signals(db)
        assert all_signals['documents']=={'indexed':1}
        bind_runtime_context(db,'northstar')
        assert signals(db,'northstar')['documents']=={}
        with pytest.raises(RuntimeError,match='unbound operator'):signals(db)
        bind_runtime_context(db,'northstar','production')
        assert signals(db,'northstar')['documents']=={'indexed':1}
        assert signals(db,'northstar')['pending_unexpired_approvals']==0
    with ctx['db']() as db:
        assert signals(db,'northstar',environment='production')['documents']=={'indexed':1}
        with pytest.raises(RuntimeError,match='explicit workspace'):signals(db,environment='production')


def test_preparing_membership_and_internal_context_do_not_enable_public_switching(ctx):
    owner,stage,production=fixtures(ctx)
    with ctx['db'].begin() as db:
        db.add(WorkspaceEnvironment(org_id='northstar',key='production',name='Production',state='preparing'));db.flush()
        db.add(EnvironmentAssignment(user_id=owner,org_id='northstar',environment_key='production'))
        bind_runtime_context(db,'northstar','production')
        assert not environment_user_allowed(db,owner,'northstar','production')
    auth(ctx)
    for path in ('/v1/me','/v1/agents','/v1/settings','/v1/runtime-operations','/v1/runtime-context'):
        response=ctx['client'].get(path,headers={'X-Nexus-Environment':'production'})
        assert response.status_code==409,response.text
        assert response.json()['error']['code']=='ENVIRONMENT_CONTEXT_CHANGED'
    assert ctx['client'].get('/v1/settings').json()['environment']=='staging'
    assert ctx['client'].get('/v1/runtime-context').json()['environment']=='staging'


@pytest.mark.parametrize('deleted',[False,True])
def test_cached_foreign_row_cannot_be_relabelled_into_context_for_write_or_delete(ctx,deleted):
    _,stage,production=fixtures(ctx)
    with pytest.raises(RuntimeError,match='Persisted runtime scope'):
        with ctx['db'].begin() as db:
            row=db.get(Agent,production)
            bind_runtime_context(db,'northstar')
            row.env='staging'
            if deleted:db.delete(row)
            db.flush()
    with ctx['db']() as db:assert db.get(Agent,production).env=='production'


def test_new_rows_adopt_context_but_persisted_scope_cannot_be_cleared(ctx):
    owner,stage,production=fixtures(ctx)
    with ctx['db'].begin() as db:
        bind_runtime_context(db,'northstar','production')
        row=Agent(org_id='northstar',name='Context-bound new agent',owner_id=owner,risk='low')
        db.add(row);db.flush();assert row.env=='production'
    with pytest.raises(RuntimeError):
        with ctx['db'].begin() as db:
            bind_runtime_context(db,'northstar');row=db.get(Agent,stage)
            row.env=None;db.delete(row);db.flush()
    with ctx['db']() as db:assert db.get(Agent,stage).env=='staging'


def test_audit_source_must_match_both_bound_context_and_explicit_provenance(ctx):
    from conftest import submit
    from nexus.db import Action
    response=submit(ctx,amount='3000.00')
    assert response.status_code==202
    with ctx['db'].begin() as db:
        action=db.get(Action,response.json()['id'])
        for org,env in [('other',None),('northstar','production')]:
            with pytest.raises(RuntimeError,match='Audit source'):audit(db,org,'worker','test.mismatch',action,env=env)
        audit(db,'northstar','worker','test.action.explicit',action)
        bind_runtime_context(db,'northstar','production')
        with pytest.raises(RuntimeError,match='does not match'):audit(db,'northstar','worker','test.bound.mismatch',action)
        db.info.pop('nexus_runtime_context')
    with ctx['db']() as db:
        row=db.scalar(select(Audit).where(Audit.event=='test.action.explicit'))
        assert row.env=='staging' and row.action_id==action.id
        assert not db.scalar(select(Audit).where(Audit.event=='test.mismatch'))
