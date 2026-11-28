"""CSV extraction and reviewed publication with disposable sources only."""
import json
import pytest
from sqlalchemy import select,func
from conftest import auth
from test_ingestion import create,payload,detail,publish,control
from nexus.csv_extraction import csv_file,CsvError,MAX_FILE
from nexus.extraction_result import normalize_result
from nexus.ingestion import run_ingestion_once
from nexus.db import IngestionJob,KnowledgeDocument,Audit


def parse(tmp_path,data,mode='auto'):
    path=tmp_path/'synthetic.csv';path.write_bytes(data)
    return csv_file(path,tmp_path,{'mode':mode})


def test_csv_preserves_literal_cells_quoted_commas_multiline_bom_and_bilingual_text(tmp_path):
    data='\ufeffname,value\r\n"pump,one","=SUM(1,2)"\r\n"سطر\nثان","001"\r\n'.encode('utf-8')
    text,info=parse(tmp_path,data)
    values=[json.loads(line.split(': ',1)[1]) for line in text.splitlines()]
    assert values==[['name','value'],['pump,one','=SUM(1,2)'],['سطر\nثان','001']]
    assert info=={'method':'csv-text','pages':None,'ocr_pages':0,'review_required':True,'extraction_mode':'auto','csv_rows':3,'csv_columns':2}
    assert normalize_result({'text':text,'info':info})=={'text':text,'info':info}


@pytest.mark.parametrize('data,code',[
    (b'\xff','CSV_TEXT_ENCODING'),(b'a\x00,b','CSV_TEXT_ENCODING'),
    (b'"unclosed,x\n','CSV_MALFORMED'),(b'a,b\nx\n','CSV_COLUMN_MISMATCH'),
    (b'x\n'*501,'CSV_ROW_LIMIT'),(b','.join([b'x']*33),'CSV_COLUMN_LIMIT'),
    (b'x'*2049,'CSV_CELL_LIMIT'),(('ع'*1025).encode('utf-8'),'CSV_CELL_LIMIT'),
    ((b'x'*500+b'\n')*80,'EXTRACTED_TEXT_LIMIT'),(b' , \n,\n','NO_EXTRACTABLE_TEXT'),
    (b'x'*(MAX_FILE+1),'FILE_SIZE_LIMIT'),
])
def test_csv_bounds_and_invalid_inputs_fail_without_partial_text(tmp_path,data,code):
    with pytest.raises(CsvError) as error:parse(tmp_path,data)
    assert str(error.value)==code


def test_csv_exact_row_column_cell_bounds_and_blank_records(tmp_path):
    assert parse(tmp_path,b'x\n'*500)[1]['csv_rows']==500
    assert parse(tmp_path,b','.join([b'x']*32))[1]['csv_columns']==32
    assert parse(tmp_path,('ع'*1024).encode('utf-8'))[1]['csv_rows']==1
    assert parse(tmp_path,b'\na,b\n\nc,d\n')[1]['csv_rows']==2
    with pytest.raises(CsvError,match='UNSUPPORTED_EXTRACTION_MODE'):parse(tmp_path,b'a,b',mode='ocr')


def test_csv_normal_api_requires_review_and_preserves_provenance_acl_and_literal_formula(ctx):
    data='sensor,value\npumpcsvneedle,45 minutes\nحساس,=1+1\n'.encode('utf-8')
    body=payload(data=data,filename='sensors.csv',language='Bilingual')
    job=create(ctx,body);assert job['format']=='csv' and job['status']=='queued'
    assert create(ctx,body)['id']==job['id']
    assert run_ingestion_once(ctx['db'],ctx['settings'])
    review=detail(ctx,job['id']);assert review['status']=='awaiting_review',review
    assert review['extraction']['csv_rows']==3 and review['extraction']['csv_columns']==2
    assert 'pumpcsvneedle' in review['extracted_text'] and '=1+1' in review['extracted_text']
    assert ctx['client'].get('/v1/documents/search?q=pumpcsvneedle').json()['items']==[]
    result=publish(ctx,review);assert result.status_code==200,result.text
    identifier=result.json()['document_id'];assert publish(ctx,review).json()['document_id']==identifier
    assert ctx['client'].get('/v1/documents/search?q=pumpcsvneedle').json()['items'][0]['document_id']==identifier
    doc=ctx['client'].get('/v1/documents/'+identifier).json()
    assert doc['provenance']['original_sha256']==job['original_sha256']
    auth(ctx,'approver');assert ctx['client'].get('/v1/documents/'+identifier).status_code==404
    auth(ctx,'auditor');assert ctx['client'].get('/v1/documents/'+identifier).status_code==200
    assert ctx['client'].get('/v1/ingestion-jobs/'+job['id']).status_code==404
    auth(ctx,org='other');assert ctx['client'].get('/v1/documents/'+identifier).status_code==404
    with ctx['db']() as db:
        stored=db.get(IngestionJob,job['id']);assert not stored.original_data and not stored.extracted_text
        assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==1
        assert 'pumpcsvneedle' not in str([row.detail for row in db.scalars(select(Audit))])


def test_malformed_csv_worker_records_fixed_failure_and_archive_discards_source(ctx):
    job=create(ctx,payload(data=b'a,b\nPRIVATE-CSV-ROW\n',filename='bad.csv'))
    assert run_ingestion_once(ctx['db'],ctx['settings'])
    failed=detail(ctx,job['id']);assert failed['status']=='failed' and failed['error_code']=='CSV_COLUMN_MISMATCH'
    assert 'PRIVATE-CSV-ROW' not in str(failed) and 'extracted_text' not in failed
    assert publish(ctx,failed).status_code==409
    assert control(ctx,failed,'archive').status_code==200
    with ctx['db']() as db:
        assert not db.get(IngestionJob,job['id']).original_data
        assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==0


def test_csv_capabilities_and_ocr_rejection_without_enabling_any_worker(ctx):
    headers,_=auth(ctx);headers['Idempotency-Key']='csv-invalid-mode-0001'
    caps=ctx['client'].get('/v1/ingestion-capabilities').json()
    assert 'csv' in caps['formats'] and caps['csv_max_rows']==500 and caps['csv_max_columns']==32 and caps['csv_max_cell_bytes']==2048
    response=ctx['client'].post('/v1/ingestion-jobs',headers=headers,json=payload(data=b'a,b',filename='table.csv',extraction_mode='ocr'))
    assert response.status_code==422 and response.json()['error']['code']=='UNSUPPORTED_EXTRACTION_MODE'
    assert ctx['settings'].ingestion_ocr_enabled==0


@pytest.mark.parametrize('patch',[{'csv_rows':True},{'csv_rows':501},{'csv_columns':33},{'csv_columns':0},{'method':'pdf-text'},{'ocr_pages':1},{'extraction_mode':'ocr'}])
def test_csv_protocol_rejects_false_or_unbounded_metadata(patch):
    info={'method':'csv-text','pages':None,'ocr_pages':0,'review_required':True,'extraction_mode':'auto','csv_rows':1,'csv_columns':1,**patch}
    assert normalize_result({'text':'Row 1: ["safe"]','info':info})=={'error_code':'EXTRACTOR_RESULT_INVALID'}
