"""Disposable real-parser file intake exercise; never reads operator configuration."""
import argparse
import base64
from datetime import datetime, timezone
import gc
import hashlib
import io
import json
import logging
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
import uuid
import zipfile
from xml.sax.saxutils import escape
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from . import __version__
from .app import create_app
from .cli import seed
from .config import Settings
from .db import CURRENT_SCHEMA, Organization, Policy, User, IngestionJob, KnowledgeDocument, DocumentChunk, migrate
from .environments import assign_staging
from .ingestion import run_ingestion_once
from .mock_connector import MockBusiness
from .retrieval_drill import DrillFailure
from .security import password_hash

BOUNDARY = ('Disposable synthetic DOCX/PDF intake exercise with local parsers only. No customer system or model provider was contacted. '
            'This is not OCR acceptance, malware scanning, authenticated evidence or production readiness.')
DOCX_TEXT = 'Synthetic procurement evidence requires independent review.\nإِدَارَة المَشْتَرَيَات تَتَطَلَّب المُوَافَقَة.'
PDF_TEXT = 'Synthetic PDF procurement evidence requires review.'


def docx_fixture():
    """Minimal deterministic OOXML package with synthetic text only."""
    parts={
        '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml':'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join('<w:p><w:r><w:t>'+escape(line)+'</w:t></w:r></w:p>' for line in DOCX_TEXT.splitlines())+'</w:body></w:document>'}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for name,text in parts.items():archive.writestr(zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0)),text.encode('utf-8'))
    return stream.getvalue()


def pdf_fixture(pages=1):
    objects=[b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'',b'<< /Type /Catalog /Pages 2 0 R >>'];kids=[]
    for _ in range(pages):
        page=len(objects)+1;content_id=page+1;kids.append(f'{page} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 1 0 R >> >> /Contents {content_id} 0 R >>'.encode())
        content=f'BT /F1 18 Tf 50 700 Td ({PDF_TEXT}) Tj ET'.encode('ascii')
        objects.append(b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream')
    objects[1]=f'<< /Type /Pages /Count {pages} /Kids [{" ".join(kids)}] >>'.encode()
    data=bytearray(b'%PDF-1.4\n');offsets=[]
    for index,obj in enumerate(objects,1):offsets.append(len(data));data.extend(f'{index} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(data);data.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets:data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(objects)+1} /Root 3 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(data)


def run_drill(directory):
    root=Path(directory).resolve();root.mkdir(exist_ok=False)
    settings=Settings(database_url='sqlite:///'+(root/'control.db').as_posix(),mock_database=str(root/'business.db'),
        secret=secrets.token_urlsafe(48),agent_secret=secrets.token_urlsafe(48),frontend_dir=str(root/'no-frontend'),
        mode='local',policy_mode='reference',business_connector='synthetic',live_inference=0,ingestion_ocr_enabled=0)
    result={'format':'nexus-synthetic-ingestion-drill','format_version':1,'release':__version__,'schema_version':CURRENT_SCHEMA,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'connector_mode':'synthetic','passed':False,
        'customer_acceptance':False,'production_ready':False,'steps':[],'boundary':BOUNDARY}
    app=None;logger=logging.getLogger('nexus.http');previously_disabled=logger.disabled;logger.disabled=True
    def check(name,condition):
        result['steps'].append({'id':name,'passed':bool(condition)})
        if not condition:raise DrillFailure(name)
    def expect(response,status):
        if response.status_code!=status:raise DrillFailure('unexpected_api_response')
        return response.json()
    def login(email):expect(client.post('/auth/local/login',json={'email':email,'password':password}),200)
    def headers():
        me=expect(client.get('/v1/me'),200);context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'],'X-Nexus-Context-Revision':str(context['revision'])}
    def body(data,filename):return {'title':'Disposable file intake','filename':filename,'language':'Bilingual',
        'allowed_roles':['auditor'],'content_base64':base64.b64encode(data).decode()}
    def create(request,key):return client.post('/v1/ingestion-jobs',headers={**headers(),'Idempotency-Key':key},json=request)
    def detail(job):return expect(client.get('/v1/ingestion-jobs/'+job['id'],headers=headers()),200)
    def publish(job,**changes):return client.post('/v1/ingestion-jobs/'+job['id']+'/publish',headers=headers(),json={
        'expected_version':job['version'],'reviewed':True,'note':'Compared disposable extraction to its synthetic source.',**changes})
    def control(job,command):return expect(client.post('/v1/ingestion-jobs/'+job['id']+'/control/'+command,headers=headers(),json={
        'expected_version':job['version'],'note':'Reviewed disposable intake control.'}),200)
    def search(query):return expect(client.get('/v1/documents/search',params={'q':query},headers=headers()),200)['items']
    try:
        app=create_app(settings)
        check('synthetic_runtime_with_ocr_disabled',type(app.state.connector) is MockBusiness and settings.live_inference==0 and settings.ingestion_ocr_enabled==0)
        migrate(app.state.engine,app.state.factory);password=secrets.token_urlsafe(32);seed(app.state.factory,password)
        with app.state.factory.begin() as db:
            db.add(Organization(id='intake-other',name='Disposable isolated workspace'));db.add(Policy(org_id='intake-other',version=1))
            other=User(org_id='intake-other',name='Synthetic intake owner',email='other@drill.invalid',role='owner',password_hash=password_hash(password))
            db.add(other);db.flush();assign_staging(db,other)
        with TestClient(app) as client:
            check('anonymous_intake_blocked',client.get('/v1/ingestion-jobs').status_code==401)
            login('owner@nexus.local');raw=docx_fixture();request=body(raw,'synthetic.docx')
            check('intake_requires_csrf',client.post('/v1/ingestion-jobs',headers={'Idempotency-Key':'ingestion-no-csrf'},json=request).status_code==403)
            job=expect(create(request,'ingestion-docx-source'),201)
            check('queued_file_not_searchable',job['status']=='queued' and search('procurement')==[])
            replay=expect(create(request,'ingestion-docx-source'),201)
            recovered=expect(client.post('/v1/ingestion-jobs/recover',headers=headers(),json={'key':'ingestion-docx-source'}),200)
            check('intake_replay_and_recovery',job['id']==replay['id']==recovered['id'])
            check('changed_file_intent_rejected',create({**request,'title':'Changed disposable title'},'ingestion-docx-source').status_code==409)
            check('queued_file_cannot_publish',publish(job).status_code==409)
            worked=run_ingestion_once(app.state.factory,settings);parsed=detail(job)
            check('real_docx_extraction_requires_review',worked and parsed['status']=='awaiting_review' and parsed['extracted_text']==DOCX_TEXT and parsed['extraction']['method']=='docx-text')
            check('unreviewed_extraction_not_searchable',search('procurement')==[])
            check('review_and_current_version_required',publish(parsed,reviewed=False).status_code==422 and publish(job).status_code==409)
            published=expect(publish(parsed),200);duplicate=expect(publish(parsed),200);source=published['document_id']
            with app.state.factory() as db:count=db.scalar(select(func.count()).select_from(KnowledgeDocument))
            check('reviewed_publication_is_idempotent',published['status']=='indexed' and duplicate['document_id']==source and count==1)
            with app.state.factory() as db:stored=db.get(IngestionJob,job['id']);erased=not stored.original_data and not stored.extracted_text
            check('published_intake_discards_file_and_review_text',erased)
            document=expect(client.get('/v1/documents/'+source,headers=headers()),200)
            check('source_provenance_matches_original',document['provenance']['original_sha256']==hashlib.sha256(raw).hexdigest() and
                document['provenance']['original_bytes']==len(raw) and document['provenance']['current_version_matches'])
            login('auditor@nexus.local');hits=search('ادارة المشتريات')
            citation=expect(client.get('/v1/documents/'+source+'/citations/1/1',headers=headers()),200)
            check('authorized_reader_gets_source_not_intake',any(hit['document_id']==source for hit in hits) and
                citation['verified_current'] and 'إِدَارَة' in citation['excerpt'] and
                client.get('/v1/ingestion-jobs/'+job['id'],headers=headers()).status_code==404)
            login('other@drill.invalid')
            check('other_workspace_cannot_read_intake_or_source',client.get('/v1/ingestion-jobs/'+job['id'],headers=headers()).status_code==404 and
                client.get('/v1/documents/'+source,headers=headers()).status_code==404 and search('procurement')==[])
            login('owner@nexus.local');pdf=expect(create(body(pdf_fixture(),'synthetic.pdf'),'ingestion-pdf-source'),201)
            worked=run_ingestion_once(app.state.factory,settings);pdf_parsed=detail(pdf)
            check('real_pdf_text_extraction_requires_review',worked and pdf_parsed['status']=='awaiting_review' and PDF_TEXT in pdf_parsed['extracted_text'] and
                pdf_parsed['extraction']['method']=='pdf-text' and pdf_parsed['extraction']['ocr_pages']==0)
            pdf_published=expect(publish(pdf_parsed),200)
            check('reviewed_pdf_is_searchable',pdf_published['status']=='indexed' and any(hit['document_id']==pdf_published['document_id'] for hit in search('PDF')))
            over=expect(create(body(pdf_fixture(13),'too-many.pdf'),'ingestion-page-limit'),201)
            run_ingestion_once(app.state.factory,settings);over=detail(over)
            check('pdf_page_limit_blocks_publication',over['status']=='failed' and over['error_code']=='PDF_PAGE_LIMIT' and publish(over).status_code==409)
            over=control(control(over,'cancel'),'archive')
            check('disabled_ocr_cannot_be_requested',create({**body(pdf_fixture(),'ocr.pdf'),'extraction_mode':'ocr'},'ingestion-ocr-disabled').status_code==422)
            cancelled=expect(create(request,'ingestion-cancel-source'),201);cancelled=control(cancelled,'cancel');cancelled=control(cancelled,'archive')
            cancelled_replay=expect(create(request,'ingestion-cancel-source'),201)
            check('cancel_archive_and_replay_do_not_resurrect',cancelled_replay['id']==cancelled['id'] and cancelled_replay['status']=='archived' and not run_ingestion_once(app.state.factory,settings))
            malformed=expect(create(body(b'PK\x03\x04invalid-container','invalid.docx'),'ingestion-malformed-source'),201)
            run_ingestion_once(app.state.factory,settings);malformed=detail(malformed)
            check('malformed_file_fails_without_document',malformed['status']=='failed' and malformed['error_code']=='UNSUPPORTED_OR_MALFORMED_FILE' and publish(malformed).status_code==409)
            retry=control(malformed,'retry');run_ingestion_once(app.state.factory,settings);retried=detail(retry)
            check('retry_retains_identity_and_increments_attempt',retried['id']==malformed['id'] and retried['status']=='failed' and retried['attempts']==2)
            control(control(retried,'cancel'),'archive')
            expect(client.request('DELETE','/v1/documents/'+source,headers=headers(),json={'expected_version':1,'note':'Remove disposable published DOCX source.'}),200)
            check('source_deletion_removes_search_and_citation',all(hit['document_id']!=source for hit in search('procurement')) and
                client.get('/v1/documents/'+source+'/citations/1/1',headers=headers()).status_code==404)
            again=expect(publish(parsed),200);replayed=expect(create(request,'ingestion-docx-source'),201)
            with app.state.factory() as db:
                records=db.scalars(select(KnowledgeDocument)).all()
                chunks=db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id==source))
            check('deleted_source_cannot_be_resurrected_by_replay',again['document_id']==replayed['document_id']==source and len(records)==2 and chunks==0 and
                next(row for row in records if row.id==source).status=='deleted')
            with app.state.factory() as db:jobs=db.scalars(select(IngestionJob)).all()
            check('terminal_files_erased_without_business_effects',len(jobs)==5 and all(not row.original_data and not row.extracted_text for row in jobs) and app.state.connector.count()==0)
            result['passed']=True
    except DrillFailure as exc:result['failure']=str(exc)
    except Exception:result['failure']='isolated_drill_could_not_finish'
    finally:
        if app is not None:app.state.engine.dispose()
        gc.collect();logger.disabled=previously_disabled
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Exercise disposable synthetic DOCX/PDF intake without operator settings.')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/drills')
    args=parser.parse_args(argv)
    try:
        destination=args.output_dir.resolve();destination.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.ingestion-',dir=destination) as scratch:
            if Path(scratch).resolve().parent!=destination:raise ValueError('Invalid temporary directory')
            result=run_drill(Path(scratch)/'workspace')
        report=destination/('synthetic-ingestion-'+uuid.uuid4().hex+'.json')
        with report.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2)
        print(json.dumps({'passed':result['passed'],'steps_passed':sum(row['passed'] for row in result['steps']),'report':str(report),'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError,ValueError):
        print(json.dumps({'passed':False,'failure':'Could not create or clean up the disposable drill report.','boundary':BOUNDARY}));return 1


if __name__=='__main__':raise SystemExit(main())
