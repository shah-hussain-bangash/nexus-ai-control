"""Build public synthetic UI fixtures from a disposable real backend.

No runtime database, account credential, cookie or signing key is exported.
This supports visual QA only; it is not an alternate authentication path.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import base64
import io
import zipfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from sqlalchemy import select
from nexus.app import create_app
from nexus.config import Settings
from nexus.db import database,migrate,User,DurableRun
from nexus.cli import seed
from nexus.security import issue_session
from nexus.workbench_templates import templates
from nexus.durable import run_flow_once
from nexus.worker import run_once
from nexus.ingestion import run_ingestion_once

root=Path(__file__).resolve().parents[1]
with TemporaryDirectory() as temp:
    settings=Settings(database_url='sqlite:///'+temp+'/control.db',mock_database=temp+'/mock.db',secret='snapshot-session-fixture-'+'x'*40,agent_secret='snapshot-agent-fixture-'+'y'*40)
    app=create_app(settings);factory=app.state.factory
    migrate(app.state.engine,factory);seed(factory,'Disposable-snapshot-password-not-exported')
    with factory.begin() as db:
        owner=db.scalar(select(User).where(User.role=='owner'))
        token,csrf=issue_session(db,owner,settings)
    snapshot={}
    with TestClient(app) as client:
        client.cookies.set('nexus_session',token);headers={'X-CSRF-Token':csrf}
        assert client.post('/v1/workbench-starter',headers=headers).status_code==200
        assert client.post('/v1/interface-starter',headers=headers).status_code==200
        assets=client.get('/v1/workbench').json()['assets']
        for kind in ['workflow','prompt','knowledge','guardrail','benchmark','budget','model']:
            asset=next(a for a in assets if a['kind']==kind)
            run=client.post('/v1/workbench/'+asset['id']+'/run',headers=headers,json={'query':'purchase approval supplier threshold','variables':{'context':'Synthetic source evidence.'}})
            assert run.status_code==200,run.text
        # Execute a real bounded supplier-read workflow in the disposable fixture database.
        agents=client.get('/v1/agents').json();tools=client.get('/v1/tools').json()
        agent=next(a for a in agents if a['name']=='Procurement Atlas')
        lookup=next(t for t in tools if t['kind']=='supplier')
        run_body={'name':'Supervised supplier review','agent_id':agent['id'],'steps':[{'kind':'checkpoint','label':'Validate inputs'},{'kind':'governed_action','label':'Verify supplier directory','tool_id':lookup['id'],'request':{'action':'supplier:read','resource':'suppliers','arguments':{'supplier_id':'SUP-DEMO-104'}}},{'kind':'approval','label':'Independent workflow checkpoint'},{'kind':'output','label':'Collect evidence'}]}
        created=client.post('/v1/agent-runs',headers={**headers,'Idempotency-Key':'snapshot-durable-run-001'},json=run_body);assert created.status_code==201,created.text
        for _ in range(8):
            with factory.begin() as db:
                run=db.get(DurableRun,created.json()['id']);run.next_poll=0
            run_flow_once(factory,settings);run_once(factory,settings,app.state.connector)
        doc_body={'title':'Synthetic purchasing evidence','filename':'purchasing-evidence.txt','content_base64':base64.b64encode(b'SYNTHETIC EVIDENCE: Purchase approval above USD 5,000 requires independent review. Supplier SUP-DEMO-104 provides replacement equipment.').decode(),'allowed_roles':['auditor']}
        document=client.post('/v1/documents',headers={**headers,'Idempotency-Key':'snapshot-document-001'},json=doc_body);assert document.status_code==201,document.text
        snapshot['/v1/documents/'+document.json()['id']]=client.get('/v1/documents/'+document.json()['id']).json()
        check_body={'name':'Synthetic purchasing retrieval checks','top_k':5,'cases':[{'query':'purchase approval','expected_document_ids':[document.json()['id']]},{'query':'unmatchablewordxyz','expectation':'no_results','expected_document_ids':[]}]}
        checked=client.post('/v1/retrieval-checks',headers={**headers,'Idempotency-Key':'snapshot-retrieval-check-001'},json=check_body);assert checked.status_code==201,checked.text
        snapshot['/v1/retrieval-checks/'+checked.json()['id']]=checked.json()
        snapshot['/v1/documents/'+document.json()['id']+'/citations/1/1']=client.get('/v1/documents/'+document.json()['id']+'/citations/1/1').json()
        # Real DOCX extraction creates pending-review and published synthetic sources.
        for number in [1,2]:
            packed=io.BytesIO()
            with zipfile.ZipFile(packed,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>SYNTHETIC SOURCE: Procurement evidence above USD 5,000 requires independent review. Compare supplier SUP-DEMO-104, amount and purchase purpose before approving.</w:t></w:r></w:p></w:body></w:document>')
            body={'title':'Supplier evidence — '+('pending review' if number==1 else 'published source'),'filename':'supplier-evidence.docx','content_base64':base64.b64encode(packed.getvalue()).decode(),'allowed_roles':['auditor']}
            job=client.post('/v1/ingestion-jobs',headers={**headers,'Idempotency-Key':'snapshot-intake-'+str(number)},json=body);assert job.status_code==201,job.text
            run_ingestion_once(factory,settings)
            path='/v1/ingestion-jobs/'+job.json()['id'];review=client.get(path).json();assert review['status']=='awaiting_review',review
            if number==2:
                published=client.post(path+'/publish',headers=headers,json={'expected_version':review['version'],'note':'Compared this synthetic extracted text with the source.','reviewed':True});assert published.status_code==200,published.text
                document_id=published.json()['document_id'];snapshot['/v1/documents/'+document_id]=client.get('/v1/documents/'+document_id).json()
            snapshot[path]=client.get(path).json()
        hybrid=client.post('/v1/hybrid-search',headers={**headers,'Idempotency-Key':'snapshot-hybrid-search-001'},json={'query':'supplier procurement approval','top_k':5,'min_score':0})
        assert hybrid.status_code==201 and hybrid.json()['status']=='completed',hybrid.text
        snapshot['/v1/hybrid-search/history/'+hybrid.json()['id']]=hybrid.json()
        for path in ['me','overview','agents','tools','policies','approvals','actions','audit-events','evaluations','incidents','settings','operations','workbench','runtime','production-readiness','interface-catalog','agent-runs','documents','retrieval-checks','runtime-operations','ingestion-capabilities','ingestion-jobs','hybrid-search/capabilities','hybrid-search/history','member-admin','my-sessions']:
            response=client.get('/v1/'+path);assert response.status_code==200
            snapshot['/v1/'+path]=response.json()
        snapshot['/v1/me']['csrf']='read-only-preview'
        snapshot['/v1/me']['mode']='local'
        for asset in assets:
            snapshot['/v1/workbench/'+asset['id']+'/history']=client.get('/v1/workbench/'+asset['id']+'/history').json()
    app.state.engine.dispose()
(root/'demo-preview/src/demo-data.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
print('Synthetic interface UI fixtures generated from disposable backend records.')
