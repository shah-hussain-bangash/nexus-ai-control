import base64
import hashlib
import pytest
from conftest import auth
from nexus.db import KnowledgeDocument, DocumentChunk, RetrievalCheck, WorkbenchRun
from nexus.hybrid import compute
from nexus.hybrid_worker import rank
from nexus.search_text import NORMALIZATION_VERSION, normalized_text, search_tokens
from test_document_lifecycle import run, suite
from test_hybrid import search


@pytest.mark.parametrize('source,query',[
    ('إِدَارَة المَشْتَرَيَات','ادارة المشتريات'),
    ('أَمر المُوَافَقَة','امر الموافقة'),
    ('آلية ٱلعمل','الية العمل'),
    ('مُـوَرِّد','مورد'),
    ('على','علي'),
    ('ﻻئحة','لائحة'),
    ('ﷲ','الله'),
    ('کِتاب یومي','كتاب يومي'),
    ('ا\u0655دارة','ادارة'),
    ('ك\ufe76تاب','كتاب'),
])
def test_common_arabic_search_variants_share_tokens(source,query):
    assert search_tokens(source)==search_tokens(query)
    assert normalized_text(normalized_text(source))==normalized_text(source)


@pytest.mark.parametrize('left,right',[
    ('مدرسة','مدرسه'),('سؤال','سوال'),('بيئة','بييه'),('كتاب','الكتاب'),
    ('procurement','مشتريات'),('café','cafe'),('１２３','123'),
])
def test_normalization_does_not_translate_stem_or_fold_unrelated_letters(left,right):
    assert search_tokens(left)!=search_tokens(right)


def test_mixed_english_arabic_numbers_and_identifiers_remain_tokenized():
    assert search_tokens('PROCUREMENT_42 إِدَارَة 12500.00')==['procurement_42','ادارة','12500','00']
    assert search_tokens('َُِّـ')==[]


def upload(ctx,text,roles=None):
    h,_=auth(ctx);h['Idempotency-Key']='arabic-source-'+hashlib.sha256(text.encode()).hexdigest()[:24]
    response=ctx['client'].post('/v1/documents',headers=h,json={'title':'Bilingual evidence','filename':'source.txt',
        'language':'Bilingual','content_base64':base64.b64encode(text.encode()).decode(),'allowed_roles':roles or []})
    assert response.status_code==201,response.text
    return response.json()


def test_normalized_document_search_preserves_original_text_hash_and_citation(ctx):
    original='إِدَارَة المَشْتَرَيَات تَتَطَلَّب المُوَافَقَة. Procurement reference 42.'
    doc=upload(ctx,original)
    response=ctx['client'].get('/v1/documents/search',params={'q':'ادارة المشتريات'})
    assert response.status_code==200,response.text
    data=response.json();hit=data['items'][0]
    assert data['normalization_version']==NORMALIZATION_VERSION and data['provider_calls']==0
    assert hit['document_id']==doc['id'] and hit['excerpt']==original
    assert hit['sha256']==hashlib.sha256(original.encode()).hexdigest()
    citation=ctx['client'].get('/v1/documents/'+doc['id']+'/citations/1/1')
    assert citation.status_code==200 and citation.json()['verified_current']
    with ctx['db']() as db:
        assert db.get(KnowledgeDocument,doc['id']).content==original


def test_arabic_variants_do_not_bypass_acl_workspace_or_revocation(ctx):
    shared=upload(ctx,'مُوَافَقَة المَشْتَرَيَات العادية',['auditor'])
    private=upload(ctx,'موافقة المشتريات السرية')
    auth(ctx,'auditor');data=ctx['client'].get('/v1/documents/search',params={'q':'موافقة المشتريات'}).json()
    assert {hit['document_id'] for hit in data['items']}=={shared['id']}
    assert private['id'] not in str(data)
    h,_=auth(ctx)
    changed=ctx['client'].put('/v1/documents/'+shared['id']+'/access',headers=h,
        json={'expected_version':1,'allowed_roles':[],'allowed_users':[],'note':'Revoke synthetic source access.'})
    assert changed.status_code==200
    auth(ctx,'auditor');assert ctx['client'].get('/v1/documents/search',params={'q':'مُوَافَقَة'}).json()['items']==[]
    auth(ctx,org='other');assert ctx['client'].get('/v1/documents/search',params={'q':'موافقة'}).json()['items']==[]


def test_deleted_arabic_source_stays_absent_from_normalized_search(ctx):
    doc=upload(ctx,'إجراءات المُوَافَقَة')
    h,_=auth(ctx);response=ctx['client'].request('DELETE','/v1/documents/'+doc['id'],headers=h,
        json={'expected_version':1,'note':'Remove disposable Arabic document.'})
    assert response.status_code==200
    assert ctx['client'].get('/v1/documents/search',params={'q':'اجراءات الموافقة'}).json()['items']==[]


@pytest.mark.parametrize('query',['ادارة المشتريات','إِدَارَة المُشْتَرَيَات','إدارة المـشتريات'])
def test_real_hybrid_ranker_uses_same_normalization(query):
    payload={'texts':['إِدَارَة المَشْتَرَيَات موافقة','حديقة زهور أشجار'],'query':query,
        'dimensions':2,'semantic_weight':0,'top_k':5,'min_score':0.1}
    result=rank(payload)
    assert [row['position'] for row in result['scores']]==[0]
    assert result['scores'][0]['lexical_score']==1


def test_isolated_hybrid_worker_matches_arabic_query_without_changing_excerpt(ctx):
    original='إِدَارَة المَشْتَرَيَات موافقة'
    doc=upload(ctx,original)
    result=search(ctx,query='ادارة المشتريات',semantic_weight=0)
    assert result.status_code==201,result.text
    data=result.json();assert data['status']=='completed' and data['normalization_current']
    assert data['normalization_version']==NORMALIZATION_VERSION
    assert data['items'][0]['document_id']==doc['id'] and data['items'][0]['excerpt']==original
    with ctx['db'].begin() as db:
        row=db.get(WorkbenchRun,data['id']);row.result={k:v for k,v in row.result.items() if k!='normalization_version'}
    history=ctx['client'].get('/v1/hybrid-search/history/'+data['id']).json()
    assert not history['normalization_current'] and history['normalization_version']=='legacy-unversioned'


def test_retrieval_evidence_marks_older_search_method_stale_without_rewriting_it(ctx):
    doc=upload(ctx,'إِدَارَة المَشْتَرَيَات')
    body=suite(doc['id'],cases=[{'query':'ادارة المشتريات','expected_document_ids':[doc['id']]}])
    response=run(ctx,body);assert response.status_code==201,response.text
    data=response.json();assert data['status']=='passed' and not data['stale'] and data['normalization_current']
    with ctx['db'].begin() as db:
        row=db.get(RetrievalCheck,data['id']);row.result={k:v for k,v in row.result.items() if k!='normalization_version'}
    history=ctx['client'].get('/v1/retrieval-checks/'+data['id']).json()
    assert history['stale'] and not history['normalization_current'] and 'normalization_version' not in history['result']
    assert run(ctx,body).json()['stale']
    assert not run(ctx,body,key='arabic-retrieval-new-method').json()['stale']
