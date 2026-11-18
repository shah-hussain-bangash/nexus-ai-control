"""Package sanitized NEXUS source after checks; never include private runtime state."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib,json,sys,zipfile,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
RELEASE='0.16.0'
def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: python scripts/package_source.py /absolute/output.zip')
    out=Path(sys.argv[1]);assert out.is_absolute() and out.suffix=='.zip'
    d=ROOT/'docs';suite=ET.parse(d/'test-results-0.16.0.xml').getroot().find('testsuite')
    assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('303','0','0','15')
    assert 'ℹ pass 51' in (d/'frontend-test-results-0.16.0.txt').read_text()
    for n in ['frontend-build-results-0.16.0.txt','preview-build-results-0.16.0.txt']:assert 'built in' in (d/n).read_text()
    baseline=json.loads((d/'UI_BASELINE_0_16_0.json').read_text());assert len(baseline['modules'])==18 and sum(len(m['functions']) for m in baseline['modules'])==216
    verification=json.loads((d/'VERIFICATION.json').read_text());verification['backend']['duration_seconds']=float(suite.get('time'));verification['frontend']['entry_bundle_bytes']=next((ROOT/'frontend/dist/assets').glob('index-*.js')).stat().st_size
    verification['frontend']['production_build']='passed';verification['frontend']['synthetic_preview_build']='passed'
    (d/'VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
    sys.path.insert(0,str(ROOT/'backend'))
    from nexus.app import create_app
    from nexus.config import Settings
    with TemporaryDirectory() as temp:
        app=create_app(Settings(database_url='sqlite:///'+temp+'/schema.db',mock_database=temp+'/mock.db',secret='schema-export-only-'+'x'*48,agent_secret='schema-agent-only-'+'y'*48))
        (d/'openapi.json').write_text(json.dumps(app.openapi(),indent=2)+'\n');app.state.engine.dispose()
    excluded={'.venv','node_modules','__pycache__','.pytest_cache','.git','data','.mypy_cache','.ruff_cache','backups'}
    def allowed(p):
        rel=p.relative_to(ROOT)
        if any(part in excluded for part in rel.parts):return False
        if p.name=='.env' or p.name.endswith('.env') or (p.name.startswith('.env.') and p.name!='.env.example'):return False
        if p.suffix in {'.db','.sqlite','.sqlite3','.dump','.pyc','.tsbuildinfo','.log'} or p.name.endswith(('-wal','-shm')):return False
        return str(rel)!='docs/SOURCE_MANIFEST.json'
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and allowed(p))
    (d/'SOURCE_MANIFEST.json').write_text(json.dumps({'release':RELEASE,'schema':8,'files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]},indent=2)+'\n');files.append(d/'SOURCE_MANIFEST.json')
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in files:archive.write(p,'nexus-ai-control/'+str(p.relative_to(ROOT)))
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        manifest=json.loads(archive.read('nexus-ai-control/docs/SOURCE_MANIFEST.json'))
        assert all(hashlib.sha256(archive.read('nexus-ai-control/'+row['path'])).hexdigest()==row['sha256'] for row in manifest['files'])
        required=['backend/nexus/hybrid.py','backend/nexus/hybrid_worker.py','backend/nexus/membership.py','backend/tests/test_hybrid.py','backend/tests/test_membership.py','frontend/src/EnterpriseRuntime.tsx','docs/HYBRID_RETRIEVAL_0_16_0.md','docs/IDENTITY_LIFECYCLE_0_16_0.md','docs/UPGRADE_0_16_0.md','frontend/src/uiHandoff.ts','frontend/src/ProductBoundary.tsx','frontend/tests/uiHandoff.test.ts','docs/PRODUCTION_GAPS_0_16_0.md','frontend/src/ProductExperienceView.tsx','frontend/src/productExperience.ts','frontend/src/product.css','frontend/tests/productExperience.test.ts','docs/PRODUCTION_GAPS_0_16_0.md','docs/FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv','docs/IMPLEMENTATION_PHASES_0_14_0.md','backend/nexus/ingestion.py','backend/nexus/business_connector.py','frontend/dist/index.html','scripts/start.cmd']
        assert all('nexus-ai-control/'+p in archive.namelist() for p in required)
        assert not any('/node_modules/' in p or '/.venv/' in p or '/data/' in p or p.endswith('/.env') for p in archive.namelist())
    print(json.dumps({'file':str(out),'files':len(files),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'backend_passed':288,'frontend_passed':51,'skipped':15},indent=2))
if __name__=='__main__':main()
