import copy
import pytest
from pydantic import ValidationError
from conftest import auth
from nexus.interfaces import Blueprint,catalog
from test_interfaces import payload


def operational(spec):
    return {'records':[{'id':'review-1','title':'Synthetic review','owner':'Platform team','state':'draft','attributes':{f['id']:f['default'] for f in spec['operations']['fields']}}],'events':[]}


@pytest.mark.parametrize('spec',catalog()['modules'],ids=lambda s:s['id'])
def test_operational_plan_persists_domain_fields_and_state_events(ctx,spec):
    headers,_=auth(ctx);body=payload(spec);state=operational(spec);body['config']['operational_state']=state
    response=ctx['client'].post('/v1/workbench',headers=headers,json=body)
    assert response.status_code==201,response.text
    row=response.json();command=spec['operations']['commands'][0];state['records'][0]['state']=command['to_state']
    state['events'].append({'id':'event-1','record_id':'review-1','command':command['id'],'from_state':'draft','to_state':command['to_state'],'at':'2026-11-17T12:00:00Z','note':'Reviewed synthetic operational journey.','scenario':'happy_path'})
    result=ctx['client'].put('/v1/workbench/'+row['id'],headers=headers,json={'kind':'blueprint','expected_version':row['version'],'name':row['name'],'description':row['description'],'config':body['config']})
    assert result.status_code==200,result.text
    assert result.json()['config']['operational_state']==state
    history=ctx['client'].get('/v1/workbench/'+row['id']+'/history').json()
    assert len(history)==2


@pytest.mark.parametrize('scenario',['permission_denied','dependency_unavailable','timeout_unknown','stale_revision'])
def test_failed_ui_scenarios_cannot_advance_operational_state(scenario):
    spec=catalog()['modules'][0];config=payload(spec)['config'];state=operational(spec);config['operational_state']=state;cmd=spec['operations']['commands'][0]
    event=dict(id='event-1',record_id='review-1',command=cmd['id'],from_state='draft',to_state='draft',at='2026-11-17T12:00:00Z',note='Review failure.',scenario=scenario);state['events']=[event]
    assert Blueprint.model_validate(config).operational_state.records[0].state=='draft'
    event['to_state']=cmd['to_state'];state['records'][0]['state']=cmd['to_state']
    with pytest.raises(ValidationError):Blueprint.model_validate(config)


def test_operational_metadata_rejects_forged_state_secret_and_invalid_schema():
    spec=catalog()['modules'][0];config=payload(spec)['config'];config['operational_state']=operational(spec)
    bad=copy.deepcopy(config);bad['operational_state']['records'][0]['state']='active'
    with pytest.raises(ValidationError):Blueprint.model_validate(bad)
    for field,value in [('secret_ref','raw-secret'),('schema','[]'),('endpoint','https://token@example.invalid')]:
        bad=copy.deepcopy(config);bad['operational_state']['records'][0]['attributes'][field]=value
        with pytest.raises(ValidationError):Blueprint.model_validate(bad)


def test_operational_metadata_is_bounded_and_event_references_are_valid():
    spec=catalog()['modules'][0];config=payload(spec)['config'];state=operational(spec);config['operational_state']=state
    bad=copy.deepcopy(config);bad['operational_state']['records']*=51
    with pytest.raises(ValidationError):Blueprint.model_validate(bad)
    state['events']=[dict(id='event-1',record_id='missing',command='request_review',from_state='draft',to_state='review_requested',at='2026-11-17T12:00:00Z',note='Review.',scenario='happy_path')]
    with pytest.raises(ValidationError):Blueprint.model_validate(config)
