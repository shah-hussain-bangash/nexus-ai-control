import base64
import io
import zipfile
import shutil
import json
import pytest
from sqlalchemy import select,func,update,delete
from conftest import auth
from nexus.db import IngestionJob,KnowledgeDocument,DocumentChunk,User,SchemaVersion,migrate,now,Audit
from nexus.ingestion import run_ingestion_once,extract_file


def docx(text='Synthetic procurement evidence requires independent review.'):
    output=io.BytesIO()
    # Immutable intake retries must reuse identical bytes, including ZIP metadata.
    entry=zipfile.ZipInfo('word/document.xml',date_time=(2026,1,1,0,0,0))
    with zipfile.ZipFile(output,'w') as archive:archive.writestr(entry,'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>')
    return output.getvalue()

def payload(data=None,filename='source.docx',**changes):
    return {'title':'Procurement file intake','filename':filename,'content_base64':base64.b64encode(data if data is not None else docx()).decode(),'allowed_roles':['auditor'],**changes}

def create(ctx,body=None,key='intake-upload-key-001'):
    h,_=auth(ctx);h['Idempotency-Key']=key;r=ctx['client'].post('/v1/ingestion-jobs',headers=h,json=body or payload());assert r.status_code==201,r.text;return r.json()

def detail(ctx,id):return ctx['client'].get('/v1/ingestion-jobs/'+id).json()

def publish(ctx,job):
    h,_=auth(ctx);return ctx['client'].post('/v1/ingestion-jobs/'+job['id']+'/publish',headers=h,json={'expected_version':job['version'],'note':'Compared the extracted evidence with the original source.','reviewed':True})

def control(ctx,job,command):
    h,_=auth(ctx);return ctx['client'].post('/v1/ingestion-jobs/'+job['id']+'/control/'+command,headers=h,json={'expected_version':job['version'],'note':'Reviewed intake operator control.'})

def test_real_docx_extraction_review_publication_acl_and_provenance(ctx):
    job=create(ctx);assert job['status']=='queued' and 'original_data' not in job
    assert run_ingestion_once(ctx['db'],ctx['settings'])
    parsed=detail(ctx,job['id']);assert parsed['status']=='awaiting_review',parsed
    assert 'procurement' in parsed['extracted_text'] and parsed['extraction']['method']=='docx-text'
    assert ctx['client'].get('/v1/documents/search?q=procurement').json()['items']==[]
    response=publish(ctx,parsed);assert response.status_code==200,response.text
    source=response.json()['document_id'];assert publish(ctx,parsed).json()['document_id']==source
    doc=ctx['client'].get('/v1/documents/'+source).json();assert doc['provenance']['original_sha256']==job['original_sha256'] and doc['provenance']['current_version_matches']
    assert ctx['client'].get('/v1/documents/search?q=procurement').json()['items'][0]['document_id']==source
    auth(ctx,'auditor');assert ctx['client'].get('/v1/ingestion-jobs/'+job['id']).status_code==404
    assert ctx['client'].get('/v1/documents/'+source).status_code==200
    auth(ctx,org='other');assert ctx['client'].get('/v1/ingestion-jobs/'+job['id']).status_code==404
    with ctx['db']() as db:
        assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==1
        stored=db.get(IngestionJob,job['id']);assert not stored.original_data and not stored.extracted_text
        assert not any('Synthetic procurement' in str(a.detail) for a in db.scalars(select(Audit)).all())

def test_intake_idempotency_recovery_archive_and_no_resurrection(ctx):
    job=create(ctx);assert create(ctx)['id']==job['id']
    h,_=auth(ctx);h['Idempotency-Key']='intake-upload-key-001'
    assert ctx['client'].post('/v1/ingestion-jobs',headers=h,json=payload(title='Changed request')).status_code==409
    assert ctx['client'].post('/v1/ingestion-jobs/recover',headers=h,json={'key':'intake-upload-key-001'}).json()['id']==job['id']
    cancelled=control(ctx,job,'cancel').json();archived=control(ctx,cancelled,'archive');assert archived.status_code==200
    assert create(ctx)['status']=='archived'
    assert ctx['client'].get('/v1/ingestion-jobs').json()['items']==[]
    assert not run_ingestion_once(ctx['db'],ctx['settings'])

def test_cancellation_fences_a_running_parser_result(ctx):
    job=create(ctx)
    def cancelled(data,record,settings):
        current=detail(ctx,job['id']);assert current['status']=='processing'
        assert control(ctx,current,'cancel').status_code==200
        return {'text':'This late parser result must never publish.','info':{'method':'test'}}
    run_ingestion_once(ctx['db'],ctx['settings'],cancelled)
    assert detail(ctx,job['id'])['status']=='cancelled'
    with ctx['db']() as db:assert db.scalar(select(func.count()).select_from(KnowledgeDocument))==0

def test_retry_stale_controls_expiry_and_author_revocation(ctx):
    job=create(ctx)
    run_ingestion_once(ctx['db'],ctx['settings'],lambda *args:{'error_code':'OCR_ENGINE_UNAVAILABLE'})
    failed=detail(ctx,job['id']);assert failed['status']=='failed' and failed['attempts']==1
    assert control(ctx,job,'retry').status_code==409
    assert control(ctx,failed,'retry').status_code==200
    run_ingestion_once(ctx['db'],ctx['settings']);review=detail(ctx,job['id'])
    with ctx['db'].begin() as db:db.get(IngestionJob,job['id']).expires=now()-1
    assert publish(ctx,review).status_code==409
    run_ingestion_once(ctx['db'],ctx['settings']);assert detail(ctx,job['id'])['status']=='expired'
    with ctx['db']() as db:assert not db.get(IngestionJob,job['id']).original_data

def test_worker_interruption_is_explicit_and_retry_is_bounded(ctx):
    job=create(ctx)
    with ctx['db'].begin() as db:
        row=db.get(IngestionJob,job['id']);row.status='processing';row.lease_token='lost';row.lease_until=now()-1;row.attempts=3
    run_ingestion_once(ctx['db'],ctx['settings']);failed=detail(ctx,job['id'])
    assert failed['status']=='failed' and failed['error_code']=='WORKER_INTERRUPTED'
    assert control(ctx,failed,'retry').status_code==409

def test_input_role_csrf_member_format_and_payload_bounds(ctx):
    h,_=auth(ctx);h['Idempotency-Key']='intake-invalid-key-001'
    for body in [payload(filename='../source.docx'),payload(filename='source.exe'),payload(data=b'%PDF-not-a-docx'),payload(allowed_users=['other-user']),payload(data=b'x'*1048577),payload(data=b'\x89PNG\r\n\x1a\n',filename='scan.png')]:
        assert ctx['client'].post('/v1/ingestion-jobs',headers=h,json=body).status_code in (413,422)
    assert ctx['client'].post('/v1/ingestion-jobs',json=payload()).status_code==403
    h,_=auth(ctx,'auditor');h['Idempotency-Key']='intake-role-key-001';assert ctx['client'].post('/v1/ingestion-jobs',headers=h,json=payload()).status_code==403
    auth(ctx);assert ctx['client'].get('/v1/ingestion-capabilities').json()['review_before_publication']

def test_large_intake_route_keeps_other_request_limits(ctx):
    # A legitimate uncompressed DOCX above 64 KiB is admitted only to intake.
    data=docx('Evidence '*10000);assert len(data)>65536
    job=create(ctx,payload(data=data));assert job['original_bytes']==len(data)
    assert ctx['client'].post('/auth/local/login',content=b'x'*70000).status_code==413
    run_ingestion_once(ctx['db'],ctx['settings']);assert detail(ctx,job['id'])['status']=='failed'

def test_malformed_xml_and_large_archives_do_not_publish(ctx):
    data=docx('<!DOCTYPE x>')
    job=create(ctx,payload(data=data));run_ingestion_once(ctx['db'],ctx['settings'])
    assert detail(ctx,job['id'])['error_code']=='DOCX_XML_REJECTED'
    assert ctx['client'].get('/v1/documents').json()['items']==[]

def test_publication_requires_attestation_current_version_and_current_author(ctx):
    job=create(ctx);run_ingestion_once(ctx['db'],ctx['settings']);parsed=detail(ctx,job['id']);h,_=auth(ctx)
    assert ctx['client'].post('/v1/ingestion-jobs/'+job['id']+'/publish',headers=h,json={'expected_version':parsed['version'],'note':'I did not compare the source.','reviewed':False}).status_code==422
    assert publish(ctx,job).status_code==409
    with ctx['db'].begin() as db:db.get(User,job['author_id']).role='auditor'
    assert ctx['client'].post('/v1/ingestion-jobs/'+job['id']+'/publish',headers=h,json={'expected_version':parsed['version'],'note':'Reviewed after original author permission change.','reviewed':True}).status_code==403

def test_schema_seven_upgrade_preserves_existing_documents(ctx):
    from test_documents import upload
    doc=upload(ctx)
    with ctx['app'].state.engine.begin() as conn:
        IngestionJob.__table__.drop(conn);conn.execute(delete(SchemaVersion).where(SchemaVersion.version==8))
    migrate(ctx['app'].state.engine,ctx['db']);migrate(ctx['app'].state.engine,ctx['db'])
    with ctx['db']() as db:assert db.get(KnowledgeDocument,doc['id']) and db.get(SchemaVersion,8)


def make_pdf(text='Synthetic PDF procurement evidence',pages=1):
    objects=[b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'',b'<< /Type /Catalog /Pages 2 0 R >>'];kids=[]
    for _ in range(pages):
        page_id=len(objects)+1;stream_id=page_id+1;kids.append(str(page_id)+' 0 R')
        objects.append(('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 1 0 R >> >> /Contents '+str(stream_id)+' 0 R >>').encode())
        content=('BT /F1 18 Tf 50 700 Td ('+text+') Tj ET').encode('ascii');objects.append(b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream')
    objects[1]=('<< /Type /Pages /Count '+str(pages)+' /Kids ['+' '.join(kids)+'] >>').encode();data=bytearray(b'%PDF-1.4\n');offsets=[]
    for i,obj in enumerate(objects,1):offsets.append(len(data));data.extend(str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
    xref=len(data);data.extend(('xref\n0 '+str(len(objects)+1)+'\n0000000000 65535 f \n').encode())
    for offset in offsets:data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(('trailer\n<< /Size '+str(len(objects)+1)+' /Root 3 0 R >>\nstartxref\n'+str(xref)+'\n%%EOF\n').encode());return bytes(data)

def test_real_pdf_text_and_page_limit(ctx):
    job=create(ctx,payload(data=make_pdf(),filename='evidence.pdf'));run_ingestion_once(ctx['db'],ctx['settings']);parsed=detail(ctx,job['id'])
    assert parsed['status']=='awaiting_review' and 'procurement' in parsed['extracted_text'] and parsed['extraction']['method']=='pdf-text',parsed
    over=create(ctx,payload(data=make_pdf(pages=13),filename='many.pdf'),key='intake-many-pages-001');run_ingestion_once(ctx['db'],ctx['settings']);assert detail(ctx,over['id'])['error_code']=='PDF_PAGE_LIMIT'

@pytest.mark.skipif(not shutil.which('tesseract'),reason='Tesseract binary required for real OCR acceptance')
def test_real_image_ocr_and_scanned_pdf(ctx):
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGB',(1400,320),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=44)
    draw.text((40,70),'NEXUS SYNTHETIC SUPPLIER REVIEW',font=font,fill='black')
    b=io.BytesIO();image.save(b,format='PNG');ctx['settings'].ingestion_ocr_enabled=1
    job=create(ctx,payload(data=b.getvalue(),filename='review.png'));run_ingestion_once(ctx['db'],ctx['settings']);parsed=detail(ctx,job['id'])
    assert parsed['status']=='awaiting_review' and 'SUPPLIER' in parsed['extracted_text'].upper(),parsed
    pdf=io.BytesIO();image.save(pdf,format='PDF',resolution=150)
    scan=create(ctx,payload(data=pdf.getvalue(),filename='scan.pdf',extraction_mode='ocr'),key='intake-scanned-pdf-001');run_ingestion_once(ctx['db'],ctx['settings']);parsed=detail(ctx,scan['id'])
    assert parsed['status']=='awaiting_review' and parsed['extraction']['ocr_pages']==1 and 'NEXUS' in parsed['extracted_text'].upper(),parsed


def test_missing_arabic_ocr_configuration_fails_without_english_fallback(ctx):
    from PIL import Image
    b=io.BytesIO();Image.new('RGB',(100,100),'white').save(b,format='PNG');ctx['settings'].ingestion_ocr_enabled=1
    job=create(ctx,payload(data=b.getvalue(),filename='arabic.png',language='Arabic'));run_ingestion_once(ctx['db'],ctx['settings'])
    assert detail(ctx,job['id'])['error_code']=='OCR_LANGUAGE_UNAVAILABLE'
