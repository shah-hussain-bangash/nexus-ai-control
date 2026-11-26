"""Read-only Windows loopback pilot checks; no login, keys or configuration reads."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid
import httpx

BOUNDARY = ('Point-in-time local health, anonymous access and listener checks only. '
    'No login, database mutation or configuration change. Not vulnerability scanning, alert delivery, '
    'worker liveness, external network isolation or production certification.')


def loopback_only(rows, ports):
    return all(any(row.get('LocalPort')==port for row in rows) and
        all(row.get('LocalAddress') in ('127.0.0.1','::1') for row in rows if row.get('LocalPort')==port)
        for port in ports)


def listener_rows(output, ports):
    rows=[]
    for line in output.splitlines():
        fields=line.split()
        if len(fields)!=5 or fields[0]!='TCP' or fields[3]!='LISTENING':
            continue
        address,separator,port=fields[1].rpartition(':')
        if separator and port.isdecimal() and int(port) in ports:
            rows.append({'LocalPort':int(port),'LocalAddress':address.strip('[]')})
    return rows


def check_http(client, port):
    base='http://127.0.0.1:'+str(port)
    results=[]
    for name,path,statuses in (
        ('app_live','/health/live',{200}),('app_ready','/health/ready',{200}),
        ('anonymous_runtime_denied','/v1/runtime',{401}),
        ('anonymous_metrics_denied_or_disabled','/metrics',{403,404}),
    ):
        try:
            response=client.get(base+path)
            result={'id':name,'passed':response.status_code in statuses,'http_status':response.status_code}
            if path=='/health/ready' and response.status_code==200:
                body=response.json()
                schema=body.get('schema_version') if isinstance(body,dict) else None
                result['schema_version']=schema
                result['passed']=(result['passed'] and isinstance(body,dict) and
                    body.get('status')=='ready' and body.get('mode')=='local' and type(schema) is int and schema>0)
            results.append(result)
        except (httpx.HTTPError,ValueError):
            results.append({'id':name,'passed':False,'failure':'unavailable_or_invalid_response'})
    return results


def main(argv=None):
    parser=argparse.ArgumentParser(description=BOUNDARY)
    parser.add_argument('--port',type=int,default=62346)
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'backend/data/drills')
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535 or args.port==11434:
        parser.error('Choose a valid app port different from the Ollama port.')
    report={'format':'nexus-local-pilot-check','format_version':1,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'port':args.port,
        'passed':False,'production_ready':False,'checks':[],'boundary':BOUNDARY}
    with httpx.Client(timeout=3,follow_redirects=False,trust_env=False) as client:
        report['checks']=check_http(client,args.port)
    try:
        # Windows' read-only socket table needs no CIM permissions. Retain only
        # selected listener addresses/ports; never publish PIDs or other sockets.
        result=subprocess.run(['netstat.exe','-ano','-p','tcp'],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,check=True)
        rows=listener_rows(result.stdout,(args.port,11434))
        report['checks'].append({'id':'app_and_ollama_listen_only_on_loopback',
            'passed':loopback_only(rows,(args.port,11434))})
    except (OSError,ValueError,subprocess.SubprocessError):
        report['checks'].append({'id':'app_and_ollama_listen_only_on_loopback','passed':False,
                                'failure':'listener_metadata_unavailable'})
    report['passed']=all(row['passed'] for row in report['checks'])
    try:
        destination=args.output_dir.resolve(); destination.mkdir(parents=True,exist_ok=True)
        target=destination/('local-pilot-check-'+uuid.uuid4().hex+'.json')
        with target.open('x',encoding='utf-8') as stream: json.dump(report,stream,indent=2)
        print(json.dumps({'passed':report['passed'],'checks_passed':sum(r['passed'] for r in report['checks']),
            'report':str(target),'boundary':BOUNDARY}))
        return 0 if report['passed'] else 1
    except OSError:
        print(json.dumps({'passed':False,'failure':'could_not_publish_receipt','boundary':BOUNDARY}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
