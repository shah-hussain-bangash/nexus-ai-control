"""Disposable, in-process retrieval exercise; never reads operator configuration."""
import argparse
import base64
from datetime import datetime, timezone
import gc
import json
import logging
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select
from . import __version__
from .app import create_app
from .cli import seed
from .config import Settings
from .db import CURRENT_SCHEMA, Organization, Policy, User, RetrievalCheck, migrate
from .environments import assign_staging
from .mock_connector import MockBusiness
from .security import password_hash
from .service import canonical

BOUNDARY = ('Disposable synthetic keyword-retrieval exercise only. No customer system or model provider was contacted. '
            'This is not generated-answer evaluation, authenticated evidence or production readiness.')


class DrillFailure(RuntimeError):
    pass


def run_drill(directory):
    """Require a fresh directory; all identities and databases stay under it."""
    root = Path(directory).resolve()
    root.mkdir(exist_ok=False)
    settings = Settings(database_url='sqlite:///' + (root/'control.db').as_posix(),
        mock_database=str(root/'business.db'), secret=secrets.token_urlsafe(48),
        agent_secret=secrets.token_urlsafe(48), frontend_dir=str(root/'no-frontend'),
        mode='local', policy_mode='reference', business_connector='synthetic', live_inference=0)
    result = {'format':'nexus-synthetic-retrieval-drill', 'format_version':1,
        'release':__version__, 'schema_version':CURRENT_SCHEMA,
        'created_at_utc':datetime.now(timezone.utc).isoformat(), 'connector_mode':'synthetic',
        'passed':False, 'customer_acceptance':False, 'production_ready':False,
        'steps':[], 'boundary':BOUNDARY}
    app = None
    logger = logging.getLogger('nexus.http'); previously_disabled = logger.disabled
    logger.disabled = True

    def check(name, condition):
        result['steps'].append({'id':name, 'passed':bool(condition)})
        if not condition:raise DrillFailure(name)

    def expect(response, status):
        if response.status_code != status:raise DrillFailure('unexpected_api_response')
        return response.json()

    def login(email):
        expect(client.post('/auth/local/login', json={'email':email, 'password':password}), 200)

    def headers():
        me=expect(client.get('/v1/me'),200); context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'], 'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'], 'X-Nexus-Context-Revision':str(context['revision'])}

    def upload(key, text, roles):
        return expect(client.post('/v1/documents', headers={**headers(),'Idempotency-Key':key},
            json={'title':'Disposable retrieval source', 'filename':'synthetic.txt', 'language':'Bilingual',
                  'allowed_roles':roles,'content_base64':base64.b64encode(text.encode('utf-8')).decode()}),201)

    def run(body, key):
        return expect(client.post('/v1/retrieval-checks',headers={**headers(),'Idempotency-Key':key},json=body),201)

    def compare(left, right):
        return client.post('/v1/retrieval-checks/compare',headers=headers(),
            json={'baseline_id':left['id'],'candidate_id':right['id']})

    try:
        app=create_app(settings)
        check('synthetic_runtime_only', type(app.state.connector) is MockBusiness and settings.live_inference==0)
        migrate(app.state.engine,app.state.factory);password=secrets.token_urlsafe(32)
        seed(app.state.factory,password)
        with app.state.factory.begin() as db:
            engineer=User(org_id='northstar',name='Synthetic retrieval reviewer',email='engineer@drill.invalid',
                role='engineer',password_hash=password_hash(password))
            db.add(Organization(id='retrieval-other',name='Disposable isolation workspace'))
            other=User(org_id='retrieval-other',name='Synthetic isolated owner',email='other@drill.invalid',
                role='owner',password_hash=password_hash(password))
            db.add_all([engineer,other,Policy(org_id='retrieval-other',version=1)]);db.flush()
            assign_staging(db,engineer);assign_staging(db,other)
        with TestClient(app) as client:
            check('anonymous_evidence_blocked',client.get('/v1/retrieval-checks').status_code==401)
            login('owner@nexus.local')
            english=upload('retrieval-drill-english','Procurement invoices require independent review.',['engineer'])
            arabic_text='إِدَارَة المَشْتَرَيَات تَتَطَلَّب المُوَافَقَة.'
            arabic=upload('retrieval-drill-arabic',arabic_text,['engineer'])
            hidden=upload('retrieval-drill-hidden','Procurement private source must not affect reviewer scores.',[])
            login('engineer@drill.invalid')
            hits=expect(client.get('/v1/documents/search',params={'q':'ادارة المشتريات'},headers=headers()),200)['items']
            citation=expect(client.get('/v1/documents/'+arabic['id']+'/citations/1/1',headers=headers()),200)
            check('arabic_normalization_preserves_original',len(hits)==1 and hits[0]['document_id']==arabic['id'] and
                citation['verified_current'] and citation['excerpt']==arabic_text)
            check('private_source_excluded_before_retrieval',client.get('/v1/documents/'+hidden['id'],headers=headers()).status_code==404)
            body={'name':'Synthetic retrieval baseline','top_k':5,'cases':[
                {'query':'procurement','query_language':'English','expected_document_ids':[english['id']], 'minimum_precision_percent':100},
                {'query':'ادارة المشتريات','query_language':'Arabic','expected_document_ids':[arabic['id']]},
                {'query':'unmatchedsyntheticnegative','expectation':'no_results'}]}
            baseline=run(body,'retrieval-drill-baseline')
            check('baseline_and_no_result_case_pass',baseline['status']=='passed' and baseline['passed_cases']==3 and
                baseline['result']['cases'][0]['document_precision_at_k']==1 and
                baseline['result']['cases'][2]['retrieved_document_count']==0)
            groups={row['language']:row for row in baseline['language_metrics']}
            check('reviewer_language_breakdowns',set(groups)=={'English','Arabic','Unlabelled'} and
                groups['Arabic']['mean_document_recall_at_k']==1 and groups['Unlabelled']['mean_document_precision_at_k'] is None)
            login('owner@nexus.local')
            extra=upload('retrieval-drill-extra','Procurement unlisted training memo.',['engineer'])
            login('engineer@drill.invalid')
            old=expect(client.get('/v1/retrieval-checks/'+baseline['id'],headers=headers()),200)
            check('corpus_changes_mark_saved_evidence_stale',old['stale'] and old['result']['cases'][0]['document_precision_at_k']==1)
            candidate_body={**body,'name':'After synthetic corpus change'}
            candidate=run(candidate_body,'retrieval-drill-candidate');case=candidate['result']['cases'][0]
            check('precision_target_detects_unlisted_source',candidate['status']=='failed' and candidate['passed_cases']==2 and
                case['document_recall_at_k']==1 and case['document_precision_at_k']==.5 and not case['precision_threshold_passed'] and
                case['unexpected_document_ids']==[extra['id']])
            payload={'baseline_id':baseline['id'],'candidate_id':candidate['id']}
            check('comparison_requires_csrf',client.post('/v1/retrieval-checks/compare',json=payload).status_code==403)
            comparison=expect(compare(baseline,candidate),200)
            check('saved_comparison_detects_regression',comparison['case_changes']=={'improved':0,'regressed':1,'mixed':0,'unchanged':2} and
                comparison['delta']['passed_cases']==-1 and comparison['delta']['mean_document_precision_at_k']==-.25 and
                comparison['corpus_changed'] and comparison['baseline']['stale'] and not comparison['candidate']['stale'])
            with app.state.factory() as db:
                before={row.id:canonical(row.result) for row in db.scalars(select(RetrievalCheck)).all()}
            replay=run(candidate_body,'retrieval-drill-candidate')
            recovered=expect(client.post('/v1/retrieval-checks/recover',headers=headers(),json={'key':'retrieval-drill-candidate'}),200)
            expect(compare(baseline,candidate),200)
            with app.state.factory() as db:
                after={row.id:canonical(row.result) for row in db.scalars(select(RetrievalCheck)).all()}
            check('replay_recovery_comparison_preserve_saved_runs',replay['id']==recovered['id']==candidate['id'] and before==after)
            changed={**candidate_body,'top_k':4}
            check('changed_request_cannot_reuse_intent',client.post('/v1/retrieval-checks',headers={**headers(),
                'Idempotency-Key':'retrieval-drill-candidate'},json=changed).status_code==409)
            different=run(changed,'retrieval-drill-different')
            check('mismatched_definitions_cannot_be_compared',compare(baseline,different).status_code==409)
            login('owner@nexus.local')
            check('administrator_cannot_compare_another_author',compare(baseline,candidate).status_code==404)
            login('other@drill.invalid')
            check('workspace_evidence_and_source_isolation',client.get('/v1/retrieval-checks/'+baseline['id'],headers=headers()).status_code==404 and
                client.get('/v1/documents/'+english['id'],headers=headers()).status_code==404 and compare(baseline,candidate).status_code==404)
            login('owner@nexus.local')
            expect(client.put('/v1/documents/'+extra['id']+'/access',headers=headers(),json={
                'expected_version':1,'allowed_roles':[],'note':'Revoke disposable reviewer access.'}),200)
            login('engineer@drill.invalid')
            check('revoked_unlisted_source_blocks_saved_results',client.get('/v1/retrieval-checks/'+candidate['id'],headers=headers()).status_code==409 and
                compare(baseline,candidate).status_code==409)
            login('owner@nexus.local')
            expect(client.request('DELETE','/v1/documents/'+arabic['id'],headers=headers(),json={
                'expected_version':1,'note':'Remove disposable Arabic test source.'}),200)
            login('engineer@drill.invalid')
            check('deleted_expected_source_blocks_saved_results',client.get('/v1/retrieval-checks/'+baseline['id'],headers=headers()).status_code==409 and
                compare(baseline,candidate).status_code==409)
            with app.state.factory() as db:
                saved=db.scalars(select(RetrievalCheck)).all()
                check('no_model_calls_or_business_effects',len(saved)==3 and all(row.result['provider_calls']==0 for row in saved) and app.state.connector.count()==0)
            result['passed']=True
    except DrillFailure as exc:
        result['failure']=str(exc)
    except Exception:
        result['failure']='isolated_drill_could_not_finish'
    finally:
        if app is not None:app.state.engine.dispose()
        gc.collect()
        logger.disabled=previously_disabled
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run disposable synthetic retrieval checks; never loads operator settings.')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/drills')
    args=parser.parse_args(argv)
    try:
        destination=args.output_dir.resolve();destination.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.retrieval-',dir=destination) as scratch:
            if Path(scratch).resolve().parent!=destination:raise ValueError('Invalid temporary directory')
            result=run_drill(Path(scratch)/'workspace')
        report=destination/('synthetic-retrieval-'+uuid.uuid4().hex+'.json')
        with report.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2)
        print(json.dumps({'passed':result['passed'],'steps_passed':sum(step['passed'] for step in result['steps']),
            'report':str(report),'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError,ValueError):
        print(json.dumps({'passed':False,'failure':'Could not create or clean up the disposable drill report.','boundary':BOUNDARY}))
        return 1


if __name__=='__main__':raise SystemExit(main())
