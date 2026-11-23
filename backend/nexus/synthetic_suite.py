"""Run the fixed disposable drills in separate processes and retain safe totals."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import uuid
from . import __version__
from .db import CURRENT_SCHEMA

DRILLS=(
    ('connector','connector',()),('retrieval','retrieval',()),
    ('knowledge','retrieval',('--include-hybrid',)),('ingestion','ingestion',()),
    ('agents','agent',()),('inference','inference',()),
    ('backup','backup',()),('recovery','recovery',()),
)
TIMEOUT_SECONDS=60
BOUNDARY=('Disposable synthetic checks only. No active application database was restored or overwritten. '
    'No customer system or live model provider was contacted. This unsigned summary is not customer acceptance, '
    'authenticated evidence, deployment recovery, measured RPO/RTO or production readiness.')


def verified_count(completed,directory,kind):
    """Accept only a consistent successful report inside this child's directory."""
    if len(completed.stdout)>65536:raise ValueError()
    summary=json.loads(completed.stdout)
    if not isinstance(summary,dict) or summary.get('passed') is not True:raise ValueError()
    count=summary.get('steps_passed')
    if type(count) is not int or not 1<=count<=1000:raise ValueError()
    path=Path(summary['report'])
    if directory.is_symlink() or path.is_symlink():raise ValueError()
    path=path.resolve()
    if path.parent!=directory or not path.is_file() or path.stat().st_size>262144:raise ValueError()
    report=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(report,dict) or report.get('format')!='nexus-synthetic-'+kind+'-drill' or report.get('passed') is not True:raise ValueError()
    if type(report.get('format_version')) is not int or report['format_version']!=1 or report.get('release')!=__version__:raise ValueError()
    if type(report.get('schema_version')) is not int or report['schema_version']!=CURRENT_SCHEMA:raise ValueError()
    steps=report.get('steps')
    if not isinstance(steps,list) or len(steps)!=count:raise ValueError()
    names=set()
    for step in steps:
        if not isinstance(step,dict) or step.get('passed') is not True:raise ValueError()
        name=step.get('id')
        if not isinstance(name,str) or not name or len(name)>200 or name in names:raise ValueError()
        names.add(name)
    return count


def run_suite(directory):
    root=Path(directory).resolve();root.mkdir(exist_ok=False)
    scripts=Path(__file__).resolve().parents[2]/'scripts'
    rows=[]
    for name,entry,extra in DRILLS:
        output=root/name;output.mkdir()
        row={'id':name,'passed':False,'checks_passed':0,'status':'could_not_run'}
        try:
            completed=subprocess.run([sys.executable,str(scripts/('run_synthetic_'+entry+'_drill.py')),*extra,
                '--output-dir',str(output)],cwd=output,capture_output=True,text=True,encoding='utf-8',timeout=TIMEOUT_SECONDS)
            if completed.returncode!=0:row['status']='drill_failed'
            else:
                try:
                    row['checks_passed']=verified_count(completed,output,'agent' if name=='agents' else name)
                    row['passed']=True;row['status']='passed'
                except (OSError,ValueError,KeyError,TypeError):row['status']='invalid_report'
        except subprocess.TimeoutExpired:row['status']='timed_out'
        except (OSError,UnicodeError):row['status']='could_not_run'
        rows.append(row)
    return {'format':'nexus-synthetic-suite','format_version':1,'release':__version__,'schema_version':CURRENT_SCHEMA,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'passed':bool(rows) and all(row['passed'] for row in rows),
        'drills_total':len(rows),'drills_passed':sum(row['passed'] for row in rows),
        'checks_passed':sum(row['checks_passed'] for row in rows),'per_drill_timeout_seconds':TIMEOUT_SECONDS,'drills':rows,
        'active_database_restored':False,'customer_acceptance':False,'production_ready':False,'boundary':BOUNDARY}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run all eight disposable synthetic drills without operator settings.')
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data/drills')
    args=parser.parse_args(argv)
    try:
        destination=args.output_dir.resolve();destination.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(prefix='.synthetic-suite-',dir=destination) as scratch:
            if Path(scratch).resolve().parent!=destination:raise ValueError('Invalid temporary directory')
            result=run_suite(Path(scratch)/'workspace')
        report=destination/('synthetic-suite-'+uuid.uuid4().hex+'.json')
        with report.open('x',encoding='utf-8') as target:json.dump(result,target,indent=2)
        print(json.dumps({'passed':result['passed'],'drills_passed':result['drills_passed'],'checks_passed':result['checks_passed'],
            'report':str(report),'boundary':BOUNDARY}))
        return 0 if result['passed'] else 1
    except (OSError,ValueError):
        print(json.dumps({'passed':False,'failure':'Could not create or clean up the disposable suite report.','boundary':BOUNDARY}));return 1


if __name__=='__main__':raise SystemExit(main())
