import copy
import pytest
from sqlalchemy import select,func
from test_ingestion import create,detail,control,publish
from nexus.db import IngestionJob,KnowledgeDocument,Audit
from nexus.ingestion import run_ingestion_once
from nexus.extraction_result import normalize_result


def test_non_object_result_is_failed_and_does_not_block_next_file(ctx):
    bad=create(ctx,key='malformed-extraction-first')
    good=create(ctx,key='malformed-extraction-second')
    def extractor(data,job,settings):
        return None if job.id==bad['id'] else {'text':'Valid synthetic extraction','info':{'method':'test'}}
    assert run_ingestion_once(ctx['db'],ctx['settings'],extractor)
    failed=detail(ctx,bad['id'])
    assert failed['status']=='failed' and failed['error_code']=='EXTRACTOR_RESULT_INVALID' and failed['can_retry']
    assert run_ingestion_once(ctx['db'],ctx['settings'],extractor)
    assert detail(ctx,good['id'])['status']=='awaiting_review'
    assert publish(ctx,failed).status_code==409
    queued=control(ctx,failed,'retry').json();assert queued['id']==bad['id']
    assert run_ingestion_once(ctx['db'],ctx['settings'],lambda *args:{'text':'Recovered synthetic extraction','info':{}})
    assert detail(ctx,bad['id'])['attempts']==2
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==0
        assert not db.get(IngestionJob,bad['id']).lease_token


def test_unrecognized_error_and_untrusted_metadata_are_not_persisted(ctx):
    marker='private-extractor-error-marker'
    job=create(ctx)
    assert run_ingestion_once(ctx['db'],ctx['settings'],lambda *args:{'error_code':marker,'info':{'raw_error':marker}})
    result=detail(ctx,job['id'])
    assert result['error_code']=='EXTRACTOR_RESULT_INVALID' and marker not in str(result)
    with ctx['db']() as db:
        row=db.get(IngestionJob,job['id'])
        assert marker not in str(row.extraction) and not row.extracted_text
        assert not any(marker in str(event.detail) for event in db.scalars(select(Audit)).all())


@pytest.mark.parametrize('value',[
    None,[],['text'],True,1,'raw error',{},
    {'text':None},{'text':[]},{'text':True},{'text':float('nan')},
    {'text':'bad\x00text'},{'text':'\ud800'},{'text':'ع'*16385},
    {'text':'safe','error_code':False},{'text':'safe','error_code':[]},
    {'error_code':'private raw exception'},{'text':'safe','unexpected':'private field'},
    {'text':'safe','info':None},{'text':'safe','info':[]},{'text':'safe','info':{'raw_error':'private detail'}},
    {'text':'safe','info':{'method':''}},{'text':'safe','info':{'method':'x'*65}},
    {'text':'safe','info':{'method':'bad\nmethod'}},{'text':'safe','info':{'method':'\ud800'}},
    {'text':'safe','info':{'pages':True}},{'text':'safe','info':{'pages':13}},
    {'text':'safe','info':{'ocr_pages':-1}},{'text':'safe','info':{'ocr_pages':float('nan')}},
    {'text':'safe','info':{'pages':1,'ocr_pages':2}},
    {'text':'safe','info':{'review_required':False}},{'text':'safe','info':{'review_required':1}},
    {'text':'safe','info':{'extraction_mode':[]}},{'text':'safe','info':{'extraction_mode':'unknown'}},
])
def test_malformed_protocol_shapes_are_sanitized(value):
    assert normalize_result(value)=={'error_code':'EXTRACTOR_RESULT_INVALID'}


@pytest.mark.parametrize('info',[
    {},{'method':'docx-text','pages':None,'ocr_pages':0,'review_required':True},
    {'method':'pdf-text','pages':12,'ocr_pages':0,'review_required':True,'extraction_mode':'auto'},
    {'method':'pdf-ocr','pages':12,'ocr_pages':12,'review_required':True,'extraction_mode':'ocr'},
    {'method':'image-ocr','pages':1,'ocr_pages':1,'review_required':True},
])
def test_valid_metadata_and_utf8_limit_are_preserved_without_mutation(info):
    value={'text':'ع'*16384,'info':info};before=copy.deepcopy(value)
    normalized=normalize_result(value)
    assert normalized==value and value==before and normalized['info'] is not value['info']


@pytest.mark.parametrize('error',['PDF_PAGE_LIMIT','OCR_ENGINE_UNAVAILABLE','EXTRACTION_TIMEOUT','REQUESTER_REVOKED'])
def test_documented_failure_codes_survive_without_failed_payload(error):
    assert normalize_result({'error_code':error,'text':'private failure text','info':{'raw_error':'private detail'}})=={'error_code':error}


def test_empty_valid_text_keeps_existing_no_text_failure(ctx):
    job=create(ctx)
    assert run_ingestion_once(ctx['db'],ctx['settings'],lambda *args:{'text':'  ','info':{}})
    assert detail(ctx,job['id'])['error_code']=='NO_EXTRACTABLE_TEXT'
