"""Durable local build checkpoints and worker fences with synthetic embedding transport."""
from sqlalchemy import select,func
from conftest import auth
from test_neural_index_runtime import setup,search
from test_hybrid import upload
from test_authorized_neural_search import transport
from nexus import neural_index_jobs as jobs,neural_worker
from nexus.db import WorkbenchRun,NeuralIndex,NeuralVector,KnowledgeDocument,now


def enqueue(ctx,doc,key='background-build-job-0001',role='owner'):
    headers,_=auth(ctx,role);headers['Idempotency-Key']=key
    return ctx['client'].post('/v1/neural-index-jobs',headers=headers,json={'name':'Synthetic background index','sources':[{'id':doc['id'],'version':doc['version']}]})


def context(ctx,monkeypatch,large=False):
    doc,_,_=setup(ctx,monkeypatch)
    if large:doc=upload(ctx,'Synthetic pump inspection detail. '*250)
    mock,calls=transport()
    monkeypatch.setattr(jobs,'compute',lambda payload:neural_worker.embedding_batch(payload,transport=mock))
    return doc,calls


def get(ctx,id):
    auth(ctx);response=ctx['client'].get('/v1/neural-index-jobs/'+id);assert response.status_code==200,response.text;return response.json()


def control(ctx,row,command,confirm=False):
    headers,_=auth(ctx)
    return ctx['client'].post('/v1/neural-index-jobs/'+row['id']+'/control/'+command,headers=headers,json={'expected_version':row['version'],'note':'Reviewed synthetic build control.','confirm_uncertain':confirm})


def test_enqueue_is_nonexecuting_replayable_and_worker_publishes_searchable_index(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch)
    response=enqueue(ctx,doc);assert response.status_code==202,response.text
    row=response.json();assert row['status']=='queued' and calls==[] and row['index']['status']=='building'
    assert enqueue(ctx,doc).json()['id']==row['id'] and calls==[]
    assert search(ctx,row['index_id']).status_code==409 and calls==[]
    assert jobs.run_index_job_once(ctx['db'],ctx['settings'])
    row=get(ctx,row['id']);assert row['status']=='completed' and row['provider_calls']==4 and len(calls)==4
    assert row['completed_passages']==row['total_passages']
    result=search(ctx,row['index_id']).json();assert result['status']=='completed' and result['items'][0]['document_id']==doc['id']
    assert not jobs.run_index_job_once(ctx['db'],ctx['settings'])
    headers,_=auth(ctx)
    assert ctx['client'].post('/v1/neural-index-jobs/recover',headers=headers,json={'key':'background-build-job-0001'}).json()['id']==row['id']
    assert row['id'] not in str(ctx['client'].get('/v1/workbench').json()['runs'])


def test_pause_resume_reuses_committed_batches(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch,large=True);row=enqueue(ctx,doc).json()
    assert jobs.run_index_job_once(ctx['db'],ctx['settings'])
    row=get(ctx,row['id']);assert row['status']=='queued' and row['completed_passages']==8
    assert control(ctx,row,'pause').status_code==200
    paused=get(ctx,row['id']);assert paused['status']=='paused' and not jobs.run_index_job_once(ctx['db'],ctx['settings'])
    assert control(ctx,paused,'resume').status_code==200
    for _ in range(4):jobs.run_index_job_once(ctx['db'],ctx['settings'])
    done=get(ctx,row['id']);assert done['status']=='completed' and done['confirmed_http_calls']==4*((done['total_passages']+7)//8)
    assert len(calls)==done['confirmed_http_calls']


def test_expired_batch_requires_acknowledged_resume_and_old_result_cannot_publish(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch);row=enqueue(ctx,doc).json();original=jobs.compute
    def expired(payload):
        value=original(payload)
        with ctx['db'].begin() as db:
            saved=db.get(WorkbenchRun,row['id']);saved.result={**saved.result,'lease_until':now()-1}
        return value
    monkeypatch.setattr(jobs,'compute',expired);jobs.run_index_job_once(ctx['db'],ctx['settings'])
    interrupted=get(ctx,row['id']);assert interrupted['status']=='interrupted' and interrupted['completed_passages']==0
    assert interrupted['provider_calls'] is None and interrupted['uncertain_batch']
    assert control(ctx,interrupted,'resume').status_code==409
    assert control(ctx,interrupted,'resume',True).status_code==200
    monkeypatch.setattr(jobs,'compute',original);jobs.run_index_job_once(ctx['db'],ctx['settings'])
    done=get(ctx,row['id']);assert done['status']=='completed' and done['provider_calls'] is None and done['confirmed_http_calls']==4


def test_cancel_during_batch_waits_for_worker_then_discards_staging_vectors(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch,large=True);row=enqueue(ctx,doc).json();original=jobs.compute
    def stopped(payload):
        current=get(ctx,row['id']);response=control(ctx,current,'cancel');assert response.json()['status']=='processing'
        return original(payload)
    monkeypatch.setattr(jobs,'compute',stopped);jobs.run_index_job_once(ctx['db'],ctx['settings'])
    cancelled=get(ctx,row['id']);assert cancelled['status']=='cancelled'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralVector))==0
    assert enqueue(ctx,doc).json()['id']==row['id'] and len(calls)==4


def test_source_change_before_first_batch_invalidates_empty_stage(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch);row=enqueue(ctx,doc).json();headers,_=auth(ctx)
    assert ctx['client'].put('/v1/documents/'+doc['id']+'/access',headers=headers,json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Invalidate queued synthetic source.'}).status_code==200
    jobs.run_index_job_once(ctx['db'],ctx['settings']);assert get(ctx,row['id'])['status']=='failed' and calls==[]


def test_scoped_controls_stale_versions_and_build_removal_guard(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch);row=enqueue(ctx,doc).json()
    headers,_=auth(ctx)
    assert ctx['client'].request('DELETE','/v1/neural-indexes/'+row['index_id'],headers=headers,json={'expected_version':1,'note':'Must cancel active job first.'}).status_code==409
    assert control(ctx,row,'pause').status_code==200
    assert control(ctx,row,'resume').status_code==409
    auth(ctx,'auditor');assert ctx['client'].get('/v1/neural-index-jobs/'+row['id']).status_code==404
    assert enqueue(ctx,doc,role='auditor').status_code==403
    headers,_=auth(ctx,org='other');assert ctx['client'].get('/v1/neural-index-jobs').json()['items']==[]


def test_pause_during_batch_keeps_the_checkpoint_and_resumes_remaining_work(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch,large=True);row=enqueue(ctx,doc).json();original=jobs.compute
    def paused(payload):
        assert control(ctx,get(ctx,row['id']),'pause').json()['status']=='processing'
        return original(payload)
    monkeypatch.setattr(jobs,'compute',paused);jobs.run_index_job_once(ctx['db'],ctx['settings'])
    paused=get(ctx,row['id']);assert paused['status']=='paused' and paused['completed_passages']==8
    monkeypatch.setattr(jobs,'compute',original);assert control(ctx,paused,'resume').status_code==200
    for _ in range(4):jobs.run_index_job_once(ctx['db'],ctx['settings'])
    done=get(ctx,row['id']);assert done['status']=='completed' and len(calls)==4*((done['total_passages']+7)//8)


def test_startup_recovers_expired_lease_without_implicit_model_retry(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch);row=enqueue(ctx,doc).json()
    with ctx['db'].begin() as db:
        saved=db.get(WorkbenchRun,row['id']);saved.status='processing';saved.result={**saved.result,'lease_until':now()-1,'lease_token':'lost-worker','attempts':1}
    assert jobs.run_index_job_once(ctx['db'],ctx['settings']) and calls==[]
    assert get(ctx,row['id'])['status']=='interrupted'
    assert not jobs.run_index_job_once(ctx['db'],ctx['settings']) and calls==[]


def test_checkpoint_corruption_fails_before_dispatch_and_purges_stage(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch,large=True);row=enqueue(ctx,doc).json();jobs.run_index_job_once(ctx['db'],ctx['settings'])
    before=len(calls)
    with ctx['db'].begin() as db:db.scalar(select(NeuralVector)).vector=[0,1]
    jobs.run_index_job_once(ctx['db'],ctx['settings']);assert get(ctx,row['id'])['status']=='failed' and len(calls)==before
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralVector))==0


def test_worker_can_claim_another_job_while_first_lease_is_active(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch);first=enqueue(ctx,doc).json();second=enqueue(ctx,doc,key='second-worker-build-001').json();original=jobs.compute;entered=[]
    def concurrent(payload):
        if not entered:
            entered.append(True);assert jobs.run_index_job_once(ctx['db'],ctx['settings'])
        return original(payload)
    monkeypatch.setattr(jobs,'compute',concurrent);assert jobs.run_index_job_once(ctx['db'],ctx['settings'])
    assert get(ctx,first['id'])['status']==get(ctx,second['id'])['status']=='completed' and len(calls)==8


def test_requester_revocation_after_dispatch_blocks_publication(ctx,monkeypatch):
    from nexus.db import User
    doc,calls=context(ctx,monkeypatch);row=enqueue(ctx,doc).json();original=jobs.compute
    def revoked(payload):
        result=original(payload)
        with ctx['db'].begin() as db:db.scalar(select(User).where(User.role=='owner',User.org_id=='northstar')).active=0
        return result
    monkeypatch.setattr(jobs,'compute',revoked);jobs.run_index_job_once(ctx['db'],ctx['settings'])
    with ctx['db']() as db:
        assert db.get(WorkbenchRun,row['id']).status=='failed' and db.scalar(select(func.count()).select_from(NeuralVector))==0


def test_cancelled_expired_batch_is_purged_without_retry(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch,large=True);row=enqueue(ctx,doc).json();jobs.run_index_job_once(ctx['db'],ctx['settings'])
    with ctx['db'].begin() as db:
        saved=db.get(WorkbenchRun,row['id']);saved.status='processing';saved.result={**saved.result,'lease_until':now()-1,'lease_token':'lost-worker','stop_requested':'cancelled'}
    before=len(calls);jobs.run_index_job_once(ctx['db'],ctx['settings'])
    assert get(ctx,row['id'])['status']=='cancelled' and len(calls)==before
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(NeuralVector))==0


def test_lease_expiring_during_finalization_rolls_back_only_uncommitted_batch(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch,large=True);row=enqueue(ctx,doc).json();jobs.run_index_job_once(ctx['db'],ctx['settings'])
    assert get(ctx,row['id'])['completed_passages']==8
    original=jobs.prepare_entries
    def late(entries):
        result=original(entries);monkeypatch.setattr(jobs,'now',lambda:now()+200);return result
    monkeypatch.setattr(jobs,'prepare_entries',late)
    for _ in range(4):
        jobs.run_index_job_once(ctx['db'],ctx['settings'])
        with ctx['db']() as db:
            if db.get(WorkbenchRun,row['id']).status=='interrupted':break
    with ctx['db']() as db:
        saved=db.get(WorkbenchRun,row['id']);assert saved.status=='interrupted'
        assert db.get(NeuralIndex,row['index_id']).status=='building'
        assert db.scalar(select(func.count()).select_from(NeuralVector))==saved.result['offset']
        assert 8<=saved.result['offset']<len(saved.result['entries'])


def test_index_worker_shares_inflight_capacity_with_search(ctx,monkeypatch):
    doc,calls=context(ctx,monkeypatch);first=enqueue(ctx,doc).json();second=enqueue(ctx,doc,key='capacity-second-build-001').json();original=jobs.compute
    def occupied(payload):
        with ctx['db'].begin() as db:
            author=db.get(WorkbenchRun,first['id']).author_id
            db.add(WorkbenchRun(org_id='northstar',env='staging',author_id=author,kind='hybrid_search',status='processing',duration_ms=0,result={}))
        assert not jobs.run_index_job_once(ctx['db'],ctx['settings'])
        return original(payload)
    monkeypatch.setattr(jobs,'compute',occupied);jobs.run_index_job_once(ctx['db'],ctx['settings'])
    assert get(ctx,first['id'])['status']=='completed' and get(ctx,second['id'])['status']=='queued' and len(calls)==4
