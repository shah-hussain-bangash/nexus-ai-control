import base64
import hashlib
from sqlalchemy import select
from conftest import auth
from nexus.db import WorkbenchRun,KnowledgeDocument,DocumentChunk,now
from nexus.hybrid import compute,KIND
from nexus.hybrid_worker import rank

def upload(ctx,text,roles=None):
 h,_=auth(ctx);h['Idempotency-Key']='hybrid-source-'+hashlib.sha256(text.encode()).hexdigest()[:20]
 r=ctx['client'].post('/v1/documents',headers=h,json={'title':text[:60],'filename':'evidence.txt','content_base64':base64.b64encode(text.encode()).decode(),'allowed_roles':roles or []});assert r.status_code==201,r.text;return r.json()

def search(ctx,query='car',key='hybrid-search-key-0001',**kw):
 h,_=auth(ctx);h['Idempotency-Key']=key;return ctx['client'].post('/v1/hybrid-search',headers=h,json={'query':query,'dimensions':2,**kw})

def corpus(ctx,roles=None):return [upload(ctx,t,roles) for t in ['car vehicle engine road','automobile vehicle engine road','garden flower soil plants','garden roots soil plants']]

def test_real_lsa_recovers_cooccurrence_and_hybrid_scores(ctx):
 docs=corpus(ctx);r=search(ctx);assert r.status_code==201,r.text
 data=r.json();assert data['status']=='completed',data
 car=next(x for x in data['items'] if x['document_id']==docs[0]['id']);other=next(x for x in data['items'] if x['document_id']==docs[1]['id'])
 assert car['lexical_score']>0 and other['lexical_score']==0 and other['semantic_score']>.5
 assert all(0<=x['score']<=1 for x in data['items']);assert data['provider_calls']==0 and data['rank']==2
 assert ctx['client'].get('/v1/documents/'+car['document_id']+'/citations/'+str(car['document_version'])+'/'+str(car['chunk'])).status_code==200

def test_idempotency_recovery_and_cross_account_scope(ctx):
 corpus(ctx);first=search(ctx).json();assert search(ctx).json()['id']==first['id'];assert search(ctx,query='changed').status_code==409
 h,_=auth(ctx);assert ctx['client'].post('/v1/hybrid-search/recover',headers=h,json={'key':'hybrid-search-key-0001'}).json()['id']==first['id']
 auth(ctx,'auditor');assert ctx['client'].get('/v1/hybrid-search/history/'+first['id']).status_code==404
 auth(ctx,org='other');assert ctx['client'].get('/v1/hybrid-search/history/'+first['id']).status_code==404
 assert ctx['client'].get('/v1/hybrid-search/history').json()['items']==[]

def test_acl_is_filtered_before_fit_and_rechecked_on_history(ctx):
 docs=corpus(ctx,['auditor']);private=upload(ctx,'secret submarine classified ocean navy')
 h,_=auth(ctx,'auditor');h['Idempotency-Key']='auditor-search-key-001'
 r=ctx['client'].post('/v1/hybrid-search',headers=h,json={'query':'car','dimensions':2});assert r.status_code==201 and r.json()['source_count']==4
 run_id=r.json()['id'];assert all(i['document_id']!=private['id'] for i in r.json()['items'])
 with ctx['db'].begin() as db:
  for doc in docs:db.get(KnowledgeDocument,doc['id']).allowed_roles=[]
 history=ctx['client'].get('/v1/hybrid-search/history/'+run_id).json();assert history['items']==[] and history['withheld_stale_or_inaccessible']>=1

def test_revocation_during_compute_fences_the_whole_result(ctx,monkeypatch):
 docs=corpus(ctx)
 def changed(payload):
  result=rank(payload)
  with ctx['db'].begin() as db:db.get(KnowledgeDocument,docs[0]['id']).version+=1
  return result
 monkeypatch.setattr('nexus.hybrid.compute',changed)
 data=search(ctx).json();assert data['status']=='failed' and data['error_code']=='SOURCE_SCOPE_CHANGED' and not data['items']

def test_selected_source_versions_and_hidden_sources_fail_closed(ctx):
 docs=corpus(ctx);assert search(ctx,sources=[{'id':docs[0]['id'],'version':99}]).status_code==409
 h,_=auth(ctx,'auditor');h['Idempotency-Key']='selected-search-key-001'
 assert ctx['client'].post('/v1/hybrid-search',headers=h,json={'query':'car','sources':[{'id':docs[0]['id'],'version':1}]}).status_code==404
 assert search(ctx,sources=[{'id':docs[0]['id'],'version':1}]*2).status_code==422

def test_no_match_empty_corpus_and_unicode_arabic(ctx):
 assert search(ctx).json()['items']==[]
 doc=upload(ctx,'مضخات معدات صيانة مشتريات')
 data=search(ctx,query='صيانة',key='arabic-search-key-001').json();assert data['items'][0]['document_id']==doc['id']
 assert search(ctx,query='unseenunknownterm',key='empty-search-key-002').json()['items']==[]

def test_original_query_and_excerpts_are_not_saved_or_exposed_through_workbench(ctx):
 corpus(ctx);query='car private-query-marker';r=search(ctx,query=query).json()
 with ctx['db']() as db:
  row=db.get(WorkbenchRun,r['id']);raw=str(row.result);assert query not in raw and 'private-query-marker' not in raw and 'car vehicle engine road' not in raw
 assert all(x['id']!=r['id'] for x in ctx['client'].get('/v1/workbench').json()['runs'])

def test_bounds_csrf_and_rate_limit(ctx):
 auth(ctx)
 assert ctx['client'].post('/v1/hybrid-search',headers={'Idempotency-Key':'valid-search-key-001'},json={'query':'car'}).status_code==403
 for body in [{'query':' '},{'query':'x'*501},{'query':'car','dimensions':33},{'query':'car','semantic_weight':2}]:
  h,_=auth(ctx);h['Idempotency-Key']='invalid-search-key-001';assert ctx['client'].post('/v1/hybrid-search',headers=h,json=body).status_code==422
 h,uid=auth(ctx)
 with ctx['db'].begin() as db:
  for _ in range(30):db.add(WorkbenchRun(org_id='northstar',author_id=uid,kind=KIND,status='completed',duration_ms=0,result={}))
 assert search(ctx).status_code==429

def test_concurrency_and_interrupted_records(ctx):
 h,uid=auth(ctx)
 with ctx['db'].begin() as db:
  for _ in range(2):db.add(WorkbenchRun(org_id='northstar',author_id=uid,kind=KIND,status='processing',duration_ms=0,result={}))
 assert search(ctx).status_code==429
 with ctx['db'].begin() as db:
  for row in db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind==KIND)):row.created=now()-130
 assert search(ctx).status_code==201
 with ctx['db']() as db:assert len(db.scalars(select(WorkbenchRun).where(WorkbenchRun.status=='interrupted')).all())==2

def test_oversized_corpus_and_vocabulary_are_explicit(ctx):
 doc=upload(ctx,'bounded text')
 with ctx['db'].begin() as db:
  for i in range(130):db.add(DocumentChunk(org_id='northstar',document_id=doc['id'],document_version=1,position=i+2,text='bounded text',content_hash='test'))
 assert search(ctx).status_code==422
 result=compute({'texts':[' '.join('t'+str(i) for i in range(80*j,80*j+80)) for j in range(14)],'query':'t1','dimensions':2,'semantic_weight':.6,'top_k':5,'min_score':.1})
 assert result['error_code']=='VOCABULARY_LIMIT'

def test_failure_and_malformed_worker_result_never_fabricate_results(ctx,monkeypatch):
 corpus(ctx);monkeypatch.setattr('nexus.hybrid.compute',lambda p:{'rank':2,'vocabulary':10,'scores':[{'position':999,'score':1,'semantic_score':1,'lexical_score':1}]})
 data=search(ctx).json();assert data['status']=='failed' and data['error_code']=='RANKING_FAILED' and data['items']==[]


def test_worker_deadline_sanitizes_environment_and_removes_private_inputs(monkeypatch):
 import os,subprocess
 import pytest
 if os.name!='posix':pytest.skip('POSIX process-group deadline assertion; not available on Windows')
 from pathlib import Path
 from nexus import hybrid
 captured={};killed=[]
 class Process:
  pid=123456
  def wait(self,timeout=None):
   if timeout is not None:raise subprocess.TimeoutExpired('synthetic-worker',timeout)
   return -9
 def launch(args,**kwargs):
  captured.update(kwargs);captured['input']=Path(args[-2]);captured['output']=Path(args[-1]);assert captured['input'].exists()
  return Process()
 monkeypatch.setenv('NEXUS_SECRET','synthetic-not-a-runtime-secret')
 monkeypatch.setattr(hybrid.subprocess,'Popen',launch)
 monkeypatch.setattr(hybrid.os,'killpg',lambda pid,sig:killed.append(pid))
 # Windows uses taskkill instead of killpg; this test exercises the POSIX path.
 assert compute({'texts':['private fixture input'],'query':'fixture'})=={'error_code':'SEARCH_TIMEOUT'}
 assert killed==[123456] and 'NEXUS_SECRET' not in captured['env']
 assert captured['env']['OPENBLAS_NUM_THREADS']=='1'
 assert not captured['input'].exists() and not captured['output'].exists()
