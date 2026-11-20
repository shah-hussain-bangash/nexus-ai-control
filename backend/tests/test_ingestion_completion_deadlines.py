import pytest
from sqlalchemy import select, func
from test_ingestion import create, detail, publish, control
from nexus import ingestion
from nexus.db import IngestionJob, KnowledgeDocument, now


@pytest.mark.parametrize('outcome',[{'text':'Late synthetic extraction','info':{'method':'test'}},{'error_code':'EXTRACTION_UNAVAILABLE'}])
@pytest.mark.parametrize('deadline',['review','lease'])
def test_expired_completion_never_becomes_reviewable(ctx,monkeypatch,outcome,deadline):
    job=create(ctx);clock=[now()]
    if deadline=='review':
        with ctx['db'].begin() as db:db.get(IngestionJob,job['id']).expires=clock[0]+5
    monkeypatch.setattr(ingestion,'now',lambda:clock[0])
    def delayed(*args):
        clock[0]+=5 if deadline=='review' else 90
        return outcome
    assert ingestion.run_ingestion_once(ctx['db'],ctx['settings'],delayed)
    result=detail(ctx,job['id'])
    assert result['status']==('expired' if deadline=='review' else 'failed')
    assert result['error_code']==('REVIEW_WINDOW_EXPIRED' if deadline=='review' else 'WORKER_INTERRUPTED')
    assert result['attempts']==1 and 'extracted_text' not in result
    assert publish(ctx,result).status_code==409
    with ctx['db']() as db:
        row=db.get(IngestionJob,job['id'])
        assert not row.extracted_text and not row.lease_token and row.lease_until==0
        assert bool(row.original_data)==(deadline=='lease')
        assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==0


@pytest.mark.parametrize('deadline',['review','lease'])
def test_completion_immediately_before_deadline_is_still_reviewable(ctx,monkeypatch,deadline):
    job=create(ctx);clock=[now()]
    if deadline=='review':
        with ctx['db'].begin() as db:db.get(IngestionJob,job['id']).expires=clock[0]+5
    monkeypatch.setattr(ingestion,'now',lambda:clock[0])
    def just_in_time(*args):
        clock[0]+=(5 if deadline=='review' else 90)-.01
        return {'text':'Timely synthetic extraction','info':{'method':'test'}}
    assert ingestion.run_ingestion_once(ctx['db'],ctx['settings'],just_in_time)
    result=detail(ctx,job['id'])
    assert result['status']=='awaiting_review' and result['extracted_text']=='Timely synthetic extraction'


def test_review_expiry_takes_precedence_when_both_deadlines_elapsed(ctx,monkeypatch):
    job=create(ctx);clock=[now()]
    with ctx['db'].begin() as db:db.get(IngestionJob,job['id']).expires=clock[0]+5
    monkeypatch.setattr(ingestion,'now',lambda:clock[0])
    def delayed(*args):
        clock[0]+=100
        return {'text':'Discard this late extraction','info':{'method':'test'}}
    ingestion.run_ingestion_once(ctx['db'],ctx['settings'],delayed)
    result=detail(ctx,job['id']);assert result['status']=='expired' and not result['can_retry']
    with ctx['db']() as db:assert not db.get(IngestionJob,job['id']).original_data


def test_lease_expiry_allows_an_explicit_retry_without_automatic_publication(ctx,monkeypatch):
    job=create(ctx);clock=[now()];monkeypatch.setattr(ingestion,'now',lambda:clock[0])
    def late(*args):
        clock[0]+=90
        return {'text':'Old attempt must not be reviewed','info':{'method':'test'}}
    ingestion.run_ingestion_once(ctx['db'],ctx['settings'],late)
    failed=detail(ctx,job['id']);assert failed['status']=='failed' and failed['can_retry']
    queued=control(ctx,failed,'retry').json();assert queued['status']=='queued' and queued['id']==job['id']
    ingestion.run_ingestion_once(ctx['db'],ctx['settings'],lambda *args:{'text':'Fresh reviewed attempt','info':{'method':'test'}})
    result=detail(ctx,job['id']);assert result['status']=='awaiting_review' and result['attempts']==2
    assert result['extracted_text']=='Fresh reviewed attempt'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==0
    assert publish(ctx,result).status_code==200


def test_cancellation_still_wins_over_late_worker_result(ctx,monkeypatch):
    job=create(ctx);clock=[now()];monkeypatch.setattr(ingestion,'now',lambda:clock[0])
    def cancelled(*args):
        processing=detail(ctx,job['id']);assert control(ctx,processing,'cancel').status_code==200
        clock[0]+=100
        return {'text':'Cancelled late extraction','info':{'method':'test'}}
    ingestion.run_ingestion_once(ctx['db'],ctx['settings'],cancelled)
    result=detail(ctx,job['id']);assert result['status']=='cancelled' and not result['can_retry']
    with ctx['db']() as db:
        row=db.get(IngestionJob,job['id']);assert not row.original_data and not row.extracted_text


def test_late_result_cannot_expire_or_overwrite_a_replacement_lease(ctx,monkeypatch):
    job=create(ctx);clock=[now()];monkeypatch.setattr(ingestion,'now',lambda:clock[0]);replacement=[]
    def superseded(*args):
        with ctx['db'].begin() as db:
            row=db.get(IngestionJob,job['id'])
            row.lease_token='replacement-worker-token';row.lease_until=clock[0]+500;row.version+=1
            replacement.append((row.version,row.lease_until))
        clock[0]+=100
        return {'text':'Superseded extraction must not be saved','info':{'method':'test'}}
    ingestion.run_ingestion_once(ctx['db'],ctx['settings'],superseded)
    with ctx['db']() as db:
        row=db.get(IngestionJob,job['id'])
        assert row.status=='processing' and row.lease_token=='replacement-worker-token'
        assert (row.version,row.lease_until)==replacement[0]
        assert row.original_data and not row.extracted_text and not row.error_code
