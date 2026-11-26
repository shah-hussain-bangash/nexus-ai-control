"""Run a disposable in-process developer example; never starts a server."""
import argparse
import json
import logging
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
import uuid
import warnings

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
with warnings.catch_warnings():
    warnings.filterwarnings('ignore',message=r'Using `httpx` with `starlette\.testclient` is deprecated;.*')
    from fastapi.testclient import TestClient
from nexus.business_reference import ReferenceBusinessStore, ReferenceCredential, create_reference_gateway

BOUNDARY = ('Disposable in-process synthetic reference example only. No network listener, '
    'customer system, active NEXUS database or operator credential is used. '
    'This is development evidence, not TLS, customer acceptance or production readiness.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=BOUNDARY)
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'backend/data/drills')
    args=parser.parse_args(argv)
    logger=logging.getLogger('nexus.http');original=logger.disabled;logger.disabled=True
    report={'format':'nexus-business-reference-example','format_version':1,'completed':False,
            'customer_acceptance':False,'production_ready':False,'boundary':BOUNDARY}
    try:
        output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.business-reference-',dir=output) as temporary:
            workspace=Path(temporary)/'reference';store=ReferenceBusinessStore.create(workspace)
            token=secrets.token_urlsafe(32)
            grants=(ReferenceCredential(token,'demo-tenant','northstar'),)
            headers={'Authorization':'Bearer '+token,'X-Nexus-Tenant':'demo-tenant',
                'X-Nexus-Organization':'northstar','X-Nexus-Contract':'nexus-business-v1'}
            body={'operation_id':'developer-purchase-0001','tenant_id':'demo-tenant','organization_id':'northstar',
                'arguments':{'supplier_id':'SUP-DEMO-104','amount':'12500.00','currency':'USD','purpose':'Synthetic developer purchase'}}
            with TestClient(create_reference_gateway(store,grants)) as client:
                supplier=client.get('/api/v1/suppliers/SUP-DEMO-104',
                    headers={**headers,'Idempotency-Key':'developer-supplier-0001'})
                if supplier.status_code!=200:raise RuntimeError('supplier_example_failed')
                purchase_headers={**headers,'Idempotency-Key':body['operation_id']}
                created=client.post('/api/v1/purchase-requests',headers=purchase_headers,json=body)
                replay=client.post('/api/v1/purchase-requests',headers=purchase_headers,json=body)
                if created.status_code!=201 or replay.status_code!=200 or created.json()!=replay.json():
                    raise RuntimeError('idempotency_example_failed')
            reopened=ReferenceBusinessStore.open(workspace)
            with TestClient(create_reference_gateway(reopened,grants)) as client:
                recovered=client.get('/api/v1/operations/'+body['operation_id'],headers=purchase_headers)
                if recovered.status_code!=200 or recovered.json()!=created.json():
                    raise RuntimeError('receipt_example_failed')
            with reopened.connect() as db:
                count=db.execute('SELECT count(*) FROM synthetic_purchases').fetchone()[0]
            if count!=1:raise RuntimeError('effect_example_failed')
            report.update(supplier_state=supplier.json()['result']['state'],
                purchase_state=created.json()['result']['state'],duplicate_returned_same_receipt=True,
                receipt_survived_reopen=True,synthetic_purchase_count=count)
        report.update(completed=True,temporary_workspace_removed=True)
        target=output/('business-reference-example-'+uuid.uuid4().hex+'.json')
        with target.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
        print(json.dumps({'completed':True,'report':str(target),'boundary':BOUNDARY}))
        return 0
    except Exception:
        print(json.dumps({'completed':False,'failure':'reference_example_could_not_complete','boundary':BOUNDARY}))
        return 1
    finally:logger.disabled=original


if __name__=='__main__':raise SystemExit(main())
