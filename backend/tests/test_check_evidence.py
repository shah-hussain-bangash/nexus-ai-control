import pytest
from sqlalchemy import select, func
from conftest import auth
from test_local_switching import current, headers, prepare, switch
from test_connector_checks import setup, submit, URL, KEY
from nexus.db import Action, Audit
from nexus.worker import run_once
from nexus.security import digest
from nexus.service import canonical


def report(ctx, identifier):
    return ctx['client'].get(URL+'/'+identifier+'/evidence', headers=headers(current(ctx)))


def test_verified_report_checksum_privacy_and_read_only_snapshot(ctx, monkeypatch):
    body=setup(ctx);identifier=submit(ctx,body).json()['check']['id']
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    with ctx['db'].begin() as db:
        row=db.get(Action,identifier)
        row.verification={**row.verification,'secret':'private-adapter-token',
            'result':{**row.verification['result'],'raw':'private-raw-response'}}
        db.add(Audit(org_id=row.org_id,env=row.env,event='qa.evidence',actor='test',action_id=row.id,
            detail={'note':'private-review-note','token':'private-adapter-token'}))
    def forbidden(*a,**kw):pytest.fail('Evidence must never contact the connector')
    monkeypatch.setattr(ctx['connector'],'invoke',forbidden)
    monkeypatch.setattr(ctx['connector'],'lookup',forbidden)
    with ctx['db']() as db:
        before=canonical(db.get(Action,identifier).verification)
        count=db.scalar(select(func.count()).select_from(Audit))
    response=report(ctx,identifier);assert response.status_code==200,response.text
    value=response.json();p=value['payload'];i=value['integrity']
    assert i['digest']==digest(canonical(p)) and i['authenticated_signature'] is False
    assert p['check']['verified'] and p['connector']['mode']=='synthetic'
    assert p['scope']['environment']=='staging' and len(p['audit_events'])>=3
    assert p['verification']['result']['supplier_id']==body['supplier_id']
    for private in (KEY,'private-adapter-token','private-raw-response','private-review-note',body['note']):
        assert private not in response.text
    with ctx['db']() as db:
        assert before==canonical(db.get(Action,identifier).verification)
        assert count==db.scalar(select(func.count()).select_from(Audit))


@pytest.mark.parametrize('status',['queued','outcome_unknown','awaiting_approval'])
def test_unresolved_reports_preserve_uncertainty_and_recorded_destination(ctx,status):
    body=setup(ctx);identifier=submit(ctx,body).json()['check']['id']
    with ctx['db'].begin() as db:db.get(Action,identifier).status=status
    ctx['settings'].business_connector='http'
    ctx['settings'].business_base_url='https://sandbox.customer.invalid/api/v1'
    ctx['settings'].business_host='sandbox.customer.invalid'
    ctx['settings'].business_tenant='test-tenant'
    response=report(ctx,identifier);assert response.status_code==200,response.text
    p=response.json()['payload']
    assert p['check']['status']==status and not p['check']['verified']
    assert p['connector']['mode']=='synthetic' and p['route']['destination_binding']=='mock-business-v1'


@pytest.mark.parametrize('corrupt',['hash','verification','external_ref','scope','operation'])
def test_inconsistent_records_cannot_claim_valid_evidence(ctx,corrupt):
    body=setup(ctx);identifier=submit(ctx,body).json()['check']['id']
    assert run_once(ctx['db'],ctx['settings'],ctx['connector'])
    with ctx['db'].begin() as db:
        row=db.get(Action,identifier)
        if corrupt=='hash':row.payload_hash='0'*64
        elif corrupt=='verification':row.verification={'matched':True,'result':{'state':'found','supplier_id':'wrong','external_ref':row.external_ref}}
        elif corrupt=='external_ref':row.external_ref='wrong'
        else:
            row.envelope={**row.envelope,('org_id' if corrupt=='scope' else 'action'):'wrong'}
            row.payload_hash=digest(canonical(row.envelope))
    response=report(ctx,identifier)
    assert response.status_code==409 and response.json()['error']['code']=='EVIDENCE_INCONSISTENT'


def test_report_access_is_bound_to_owner_account_workspace_environment_and_mode(ctx):
    body=setup(ctx);identifier=submit(ctx,body).json()['check']['id']
    assert report(ctx,'missing').status_code==404
    for role in ('auditor','approver'):
        auth(ctx,role);assert report(ctx,identifier).status_code==403
    auth(ctx,org='other');assert report(ctx,identifier).status_code==404
    auth(ctx);state=prepare(ctx,key='sandbox');switch(ctx,state)
    assert report(ctx,identifier).status_code==404
    auth(ctx);ctx['settings'].mode='pilot'
    assert report(ctx,identifier).status_code==403


def test_evidence_refuses_incomplete_audit_history(ctx):
    body=setup(ctx);identifier=submit(ctx,body).json()['check']['id']
    with ctx['db'].begin() as db:
        row=db.get(Action,identifier)
        db.add_all([Audit(org_id=row.org_id,env=row.env,event='qa.event',actor='qa',action_id=row.id) for _ in range(201)])
    response=report(ctx,identifier)
    assert response.status_code==422 and response.json()['error']['code']=='EVIDENCE_CAPACITY'


def test_other_owner_in_same_workspace_cannot_export_someone_elses_check(ctx):
    from nexus.db import User
    from nexus.environments import assign_staging
    from nexus.security import issue_session
    body=setup(ctx);identifier=submit(ctx,body).json()['check']['id']
    with ctx['db'].begin() as db:
        original=db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar'))
        user=User(org_id='northstar',email='second-owner@test.invalid',name='Second owner',role='owner',password_hash=original.password_hash)
        db.add(user);db.flush();assign_staging(db,user)
        token,_=issue_session(db,user,ctx['settings'])
    ctx['client'].cookies.set('nexus_session',token)
    assert report(ctx,identifier).status_code==404


def test_anonymous_report_request_is_rejected(ctx):
    assert ctx['client'].get(URL+'/missing/evidence').status_code==401


def test_canonical_unicode_vector_matches_browser():
    value={'z':[True,None,42],'a':'مرحبا 😀'}
    assert digest(canonical(value))=='ad60c2f7273c87c5c67253c6edc376a0f7619c1db916bcbfe35495a3e21b3978'
