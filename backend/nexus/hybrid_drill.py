"""Extra local hybrid-search checks for the disposable knowledge exercise."""
import base64
from sqlalchemy import select
from .db import Organization, Policy, User, WorkbenchRun
from .environments import assign_staging
from .security import password_hash
from .service import canonical


def exercise(app, client, password, check, expect):
    # A separate disposable organization keeps the keyword exercise's corpus intact.
    with app.state.factory.begin() as db:
        db.add(Organization(id='hybrid-drill',name='Disposable hybrid workspace'))
        db.add(Policy(org_id='hybrid-drill',version=1))
        for role,email in [('owner','hybrid-owner@drill.invalid'),('engineer','hybrid-engineer@drill.invalid'),
                           ('engineer','hybrid-unrelated@drill.invalid')]:
            user=User(org_id='hybrid-drill',name='Synthetic hybrid reviewer',email=email,
                role=role,password_hash=password_hash(password))
            db.add(user);db.flush();assign_staging(db,user)

    def login(email):
        expect(client.post('/auth/local/login',json={'email':email,'password':password}),200)

    def headers():
        me=expect(client.get('/v1/me'),200);context=me['runtime_context']
        return {'X-CSRF-Token':me['csrf'],'X-Nexus-Environment':me['environment'],
            'X-Nexus-Context-ID':context['binding_id'],'X-Nexus-Context-Revision':str(context['revision'])}

    def upload(key,text,roles=None):
        return expect(client.post('/v1/documents',headers={**headers(),'Idempotency-Key':key},json={
            'title':'Disposable hybrid source','filename':'hybrid.txt','language':'Bilingual',
            'allowed_roles':roles or [],'content_base64':base64.b64encode(text.encode('utf-8')).decode()}),201)

    def search(body,key):
        return client.post('/v1/hybrid-search',headers={**headers(),'Idempotency-Key':key},json=body)

    def history(id):
        return client.get('/v1/hybrid-search/history/'+id,headers=headers())

    login('hybrid-owner@drill.invalid')
    docs=[upload('knowledge-corpus-'+str(i),text,['engineer']) for i,text in enumerate([
        'car vehicle engine road','automobile vehicle engine road','garden flower soil plants','garden roots soil plants'])]
    arabic_text='إِدَارَة المَشْتَرَيَات تَتَطَلَّب المُوَافَقَة.'
    arabic=upload('knowledge-arabic-source',arabic_text,['engineer'])
    private=upload('knowledge-private-source','car secret private corpus marker')
    login('hybrid-engineer@drill.invalid')
    config=expect(client.get('/v1/hybrid-search/capabilities',headers=headers()),200)
    check('hybrid_local_bounded_capabilities',not config['neural_embeddings'] and not config['persistent_vector_index'] and
        config['provider_calls']==0 and config['max_selected_sources']==20 and config['max_chunks']==128)
    body={'query':'car hybrid-private-query-marker','dimensions':2,'top_k':5}
    check('hybrid_requires_csrf',client.post('/v1/hybrid-search',json=body,
        headers={'Idempotency-Key':'knowledge-csrf-search'}).status_code==403)
    first=expect(search(body,'knowledge-hybrid-first'),201)
    car=next((hit for hit in first['items'] if hit['document_id']==docs[0]['id']),None)
    related=next((hit for hit in first['items'] if hit['document_id']==docs[1]['id']),None)
    check('hybrid_real_cooccurrence_retrieval',first['status']=='completed' and car is not None and related is not None and
        car['lexical_score']>0 and related['lexical_score']==0 and related['semantic_score']>.5 and first['rank']==2)
    check('hybrid_private_source_excluded_before_fit',first['source_count']==5 and first['corpus_chunks']==5 and
        all(hit['document_id']!=private['id'] for hit in first['items']))
    citation=expect(client.get('/v1/documents/'+docs[1]['id']+'/citations/1/1',headers=headers()),200)
    check('hybrid_current_citation_matches_source',citation['verified_current'] and citation['excerpt']=='automobile vehicle engine road')
    absent=expect(search({**body,'query':'unmatchedsyntheticnegative'},'knowledge-hybrid-no-match'),201)
    check('hybrid_unknown_query_returns_no_results',absent['status']=='completed' and absent['items']==[])
    arabic_body={**body,'query':'ادارة المشتريات','sources':[{'id':arabic['id'],'version':1}]}
    arabic_run=expect(search(arabic_body,'knowledge-hybrid-arabic'),201)
    check('hybrid_arabic_normalization',arabic_run['status']=='completed' and len(arabic_run['items'])==1 and
        arabic_run['items'][0]['document_id']==arabic['id'] and arabic_run['items'][0]['excerpt']==arabic_text)
    with app.state.factory() as db:
        before={row.id:canonical(row.result) for row in db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind=='hybrid_search')).all()}
    replay=expect(search(body,'knowledge-hybrid-first'),201)
    recovered=expect(client.post('/v1/hybrid-search/recover',headers=headers(),json={'key':'knowledge-hybrid-first'}),200)
    with app.state.factory() as db:
        after={row.id:canonical(row.result) for row in db.scalars(select(WorkbenchRun).where(WorkbenchRun.kind=='hybrid_search')).all()}
    check('hybrid_replay_and_recovery_preserve_receipts',first['id']==replay['id']==recovered['id'] and before==after)
    check('hybrid_queries_and_excerpts_not_persisted',all(text not in canonical(after) for text in [
        body['query'],'hybrid-private-query-marker','car vehicle engine road',arabic_text]))
    check('hybrid_changed_intent_rejected',search({**body,'top_k':4},'knowledge-hybrid-first').status_code==409)
    check('hybrid_selected_source_permissions_and_versions',search({**body,'sources':[{'id':private['id'],'version':1}]},
        'knowledge-hybrid-private').status_code==404 and search({**body,'sources':[{'id':docs[0]['id'],'version':99}]},
        'knowledge-hybrid-old-version').status_code==409)
    login('hybrid-unrelated@drill.invalid')
    check('hybrid_other_author_history_blocked',history(first['id']).status_code==404 and
        client.post('/v1/hybrid-search/recover',headers=headers(),json={'key':'knowledge-hybrid-first'}).status_code==404)
    login('other@drill.invalid')
    check('hybrid_other_workspace_history_blocked',history(first['id']).status_code==404 and
        search({**body,'sources':[{'id':docs[0]['id'],'version':1}]},'knowledge-hybrid-other-workspace').status_code==404)
    login('hybrid-owner@drill.invalid')
    expect(client.put('/v1/documents/'+docs[0]['id']+'/access',headers=headers(),json={
        'expected_version':1,'allowed_roles':[],'note':'Revoke disposable hybrid source access.'}),200)
    login('hybrid-engineer@drill.invalid')
    revoked=expect(history(first['id']),200)
    check('hybrid_history_withholds_revoked_source',revoked['withheld_stale_or_inaccessible']>=1 and
        all(hit['document_id']!=docs[0]['id'] for hit in revoked['items']) and
        client.get('/v1/documents/'+docs[0]['id']+'/citations/1/1',headers=headers()).status_code==404)
    login('hybrid-owner@drill.invalid')
    expect(client.request('DELETE','/v1/documents/'+docs[1]['id'],headers=headers(),json={
        'expected_version':1,'note':'Remove disposable hybrid source.'}),200)
    replacement=arabic_text+' نسخة محدثة.'
    expect(client.put('/v1/documents/'+arabic['id']+'/content',headers={**headers(),'Idempotency-Key':'knowledge-arabic-replacement'},json={
        'expected_version':1,'title':'Updated disposable Arabic source','filename':'updated.txt','language':'Arabic',
        'content_base64':base64.b64encode(replacement.encode('utf-8')).decode(),'note':'Replace disposable source text.'}),200)
    login('hybrid-engineer@drill.invalid')
    deleted=expect(history(first['id']),200)
    check('hybrid_history_withholds_deleted_source',deleted['withheld_stale_or_inaccessible']>=2 and
        all(hit['document_id'] not in [docs[0]['id'],docs[1]['id']] for hit in deleted['items']) and
        client.get('/v1/documents/'+docs[1]['id']+'/citations/1/1',headers=headers()).status_code==404)
    stale=expect(history(arabic_run['id']),200)
    refreshed=expect(search({**arabic_body,'sources':[{'id':arabic['id'],'version':2}]},'knowledge-hybrid-refreshed'),201)
    check('hybrid_replaced_source_requires_fresh_citation',stale['items']==[] and stale['withheld_stale_or_inaccessible']==1 and
        client.get('/v1/documents/'+arabic['id']+'/citations/1/1',headers=headers()).status_code==409 and
        refreshed['status']=='completed' and len(refreshed['items'])==1 and refreshed['items'][0]['document_version']==2 and
        refreshed['items'][0]['excerpt']==replacement)
    login('hybrid-owner@drill.invalid')
    oversized=upload('knowledge-vocabulary-source',' '.join('term'+str(i) for i in range(1050)),['engineer'])
    login('hybrid-engineer@drill.invalid')
    bounded=expect(search({**body,'query':'term1','sources':[{'id':oversized['id'],'version':1}]},'knowledge-hybrid-vocabulary'),201)
    check('hybrid_vocabulary_limit_fails_without_hits',bounded['status']=='failed' and bounded['error_code']=='VOCABULARY_LIMIT' and bounded['items']==[])
    check('hybrid_no_provider_calls_or_business_effects',all(row['provider_calls']==0 for row in [first,absent,arabic_run,refreshed,bounded]) and
        app.state.connector.count()==0)
