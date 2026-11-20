import copy
import pytest
from sqlalchemy import select
from conftest import auth
from test_hybrid import upload,search
from nexus import hybrid
from nexus.db import WorkbenchRun,Audit
from nexus.hybrid_worker import rank
from nexus.ranking_result import normalize_result
from test_hybrid_completion import ordered_source_change


def test_non_object_ranking_failures_release_capacity_and_replay_without_rerun(ctx,monkeypatch):
    upload(ctx,'car vehicle engine road')
    monkeypatch.setattr(hybrid,'compute',lambda payload:None)
    first=search(ctx,key='malformed-ranking-first')
    assert first.status_code==201,first.text
    first=first.json();assert first['status']=='failed' and first['error_code']=='RANKING_FAILED' and first['items']==[]
    second=search(ctx,key='malformed-ranking-second')
    assert second.status_code==201 and second.json()['status']=='failed'
    def forbidden(*args):raise AssertionError('Replay must not rerun ranking')
    monkeypatch.setattr(hybrid,'compute',forbidden)
    replay=search(ctx,key='malformed-ranking-first')
    assert replay.status_code==201 and replay.json()['id']==first['id'] and replay.json()['status']=='failed'
    h,_=auth(ctx)
    recovered=ctx['client'].post('/v1/hybrid-search/recover',headers=h,json={'key':'malformed-ranking-first'})
    assert recovered.status_code==200 and recovered.json()['id']==first['id']
    monkeypatch.setattr(hybrid,'compute',rank)
    valid=search(ctx,key='valid-ranking-after-failures')
    assert valid.status_code==201 and valid.json()['status']=='completed' and valid.json()['items']


def test_unknown_ranking_error_details_are_not_saved_or_returned(ctx,monkeypatch):
    upload(ctx,'car vehicle engine road');marker='private-ranking-error-marker'
    monkeypatch.setattr(hybrid,'compute',lambda payload:{'error_code':marker})
    response=search(ctx)
    assert response.status_code==201,response.text
    assert response.json()['error_code']=='RANKING_FAILED' and marker not in response.text
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,response.json()['id'])
        assert marker not in str(saved.result) and saved.result['hits']==[]
        assert not any(marker in str(row.detail) for row in db.scalars(select(Audit)).all())


def score(**changes):return {'position':0,'score':.75,'semantic_score':.5,'lexical_score':1,**changes}
def result(**changes):return {'rank':1,'vocabulary':4,'scores':[score()],**changes}


@pytest.mark.parametrize('value',[
    None,[],False,1,'raw ranking error',{},
    result(error_code=[]),result(error_code=False),{'error_code':'private error text'},
    result(rank=True),result(rank=1.0),result(rank=33),result(vocabulary=-1),result(vocabulary=1025),
    result(scores={}),result(scores=''),result(scores=None),result(scores=[None]),
    result(scores=[score(position=True)]),result(scores=[score(position=-1)]),result(scores=[score(position=2)]),
    result(scores=[score(),score()]),result(scores=[score(),score(position=1),score(position=0)]),
    result(scores=[score(score=True)]),result(scores=[score(score='0.5')]),
    result(scores=[score(score=float('nan'))]),result(scores=[score(semantic_score=float('inf'))]),
    result(scores=[score(lexical_score=10**1000)]),result(scores=[score(score=1.01)]),
    result(scores=[{'position':0,'score':.5}]),result(scores=[score(document_id='untrusted-source')]),
    result(debug='private payload'),
])
def test_malformed_ranking_protocol_fails_closed(value):
    assert normalize_result(value,2,2)=={'error_code':'RANKING_FAILED'}


def test_valid_ranking_payload_is_copied_without_rerounding_or_mutation():
    value=result(scores=[score(score=.123456),score(position=1,score=0,semantic_score=0,lexical_score=0)])
    before=copy.deepcopy(value);normalized=normalize_result(value,2,2)
    assert normalized==before and value==before
    assert normalized['scores'] is not value['scores'] and normalized['scores'][0] is not value['scores'][0]
    assert normalize_result({'rank':0,'vocabulary':0,'scores':[]},0,5)=={'rank':0,'vocabulary':0,'scores':[]}


@pytest.mark.parametrize('error',['SEARCH_TIMEOUT','RANKING_FAILED','VOCABULARY_LIMIT','CORPUS_LIMIT'])
def test_known_failure_discards_companion_ranking_payload(error):
    assert normalize_result({'error_code':error,'scores':'private detail','rank':'private detail','vocabulary':None},2,2)=={'error_code':error}


def test_source_change_still_takes_precedence_over_malformed_output(ctx,monkeypatch):
    source=upload(ctx,'car vehicle engine road')
    def changed(payload):
        assert ordered_source_change(ctx,source['id'],'revoke')=='committed'
        return None
    monkeypatch.setattr(hybrid,'compute',changed)
    response=search(ctx)
    assert response.status_code==201,response.text
    assert response.json()['status']=='failed' and response.json()['error_code']=='SOURCE_SCOPE_CHANGED'
    assert response.json()['items']==[]
