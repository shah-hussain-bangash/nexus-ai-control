from conftest import auth, approve
from test_durable import body, create, advance, control
from test_local_switching import prepare, switch, headers, current
from nexus.db import DurableRun, Action

URL='/v1/agent-runs?attention_only=true'


def items(ctx):
    response=ctx['client'].get(URL)
    assert response.status_code==200,response.text
    return response.json()['items']


def test_normal_queued_and_successful_work_does_not_enter_attention_queue(ctx):
    run=create(ctx,review=False,purchase=False)
    assert items(ctx)==[] and ctx['connector'].count()==0
    assert len(ctx['client'].get('/v1/agent-runs').json()['items'])==1
    assert advance(ctx,run['id'])['status']=='succeeded'
    assert items(ctx)==[] and ctx['connector'].count()==1


def test_independent_review_and_pending_business_approval_are_both_visible(ctx):
    run=create(ctx);run=advance(ctx,run['id'])
    assert [r['id'] for r in items(ctx)]==[run['id']]
    h,_=auth(ctx,'approver')
    assert ctx['client'].post('/v1/agent-runs/'+run['id']+'/decision',headers=h,json={
        'expected_version':run['version'],'decision':'approve','note':'Reviewed workflow checkpoint.'}).status_code==200
    run=advance(ctx,run['id']);auth(ctx)
    assert run['status']=='waiting_action' and [r['id'] for r in items(ctx)]==[run['id']]
    paused=control(ctx,run,'pause').json()
    assert [r['id'] for r in items(ctx)]==[run['id']]
    assert paused['status']=='paused' and ctx['connector'].count()==1
    assert approve(ctx).status_code==200
    auth(ctx);assert items(ctx)==[]  # paused, approved work is not a new review
    assert ctx['connector'].count()==1


def test_unknown_and_cancelling_effects_stay_visible_without_replay(ctx):
    run=create(ctx,review=False,simulation='timeout_after_commit');run=advance(ctx,run['id'])
    assert approve(ctx).status_code==200
    run=advance(ctx,run['id']);auth(ctx)
    assert run['status']=='outcome_unknown'
    assert items(ctx)[0]['id']==run['id'] and items(ctx)[0]['status']=='outcome_unknown'
    assert control(ctx,run,'cancel').status_code==200
    assert items(ctx)[0]['cancel_requested'] and ctx['connector'].count()==2


def test_filtered_pagination_and_workspace_environment_isolation(ctx):
    h,_=auth(ctx);identifiers=[]
    for index,status in enumerate(('queued','failed','expired','rejected','cancelled')):
        h['Idempotency-Key']='attention-pagination-'+str(index)
        response=ctx['client'].post('/v1/agent-runs',headers=h,json=body(ctx,review=False,purchase=False))
        assert response.status_code==201,response.text
        identifiers.append(response.json()['id'])
        with ctx['db'].begin() as db:
            row=db.get(DurableRun,identifiers[-1]);row.status=status;row.created=100+index
    first=ctx['client'].get(URL+'&limit=2').json()
    assert [r['id'] for r in first['items']]==[identifiers[3],identifiers[2]] and first['next_offset']==2
    second=ctx['client'].get(URL+'&limit=2&offset=2').json()
    assert [r['id'] for r in second['items']]==[identifiers[1]] and second['next_offset'] is None
    auth(ctx,org='other');assert items(ctx)==[]
    auth(ctx);state=prepare(ctx,key='sandbox');switch(ctx,state)
    response=ctx['client'].get(URL,headers=headers(current(ctx)))
    assert response.status_code==200 and response.json()['items']==[]


def test_old_step_actions_do_not_raise_attention_for_a_later_cursor(ctx):
    run=create(ctx,review=False,purchase=False);run=advance(ctx,run['id'])
    with ctx['db'].begin() as db:
        row=db.get(DurableRun,run['id']);row.status='queued';row.cursor=2
        db.get(Action,run['steps'][1]['action_id']).status='awaiting_approval'
    assert items(ctx)==[]


def test_filter_uses_existing_auth_and_rejects_invalid_values(ctx):
    ctx['client'].cookies.clear();assert ctx['client'].get(URL).status_code==401
    auth(ctx,'auditor');assert items(ctx)==[]
    assert ctx['client'].get('/v1/agent-runs?attention_only=unrecognized').status_code==422
