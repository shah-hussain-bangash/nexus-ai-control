"""Generate the current roadmap from the same definitions used by the API."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from nexus.readiness import GATES


def outputs():
    release=json.loads((ROOT/'package.json').read_text())['version']
    counts={state:sum(g[3]==state for g in GATES) for state in ('implemented','partial','not_implemented')}
    data={'release':release,'scope':'Production extension workstreams; source delivery and deployment acceptance are separate.',**counts,'production_ready':False,'accepted_by_default':0,
          'workstreams':[dict(zip(('id','title','area','delivery','required_evidence','workspace'),g)) for g in GATES]}
    lines=[f'# Production roadmap — {release}', '',
           'Generated from `backend/nexus/readiness.py` by `scripts/export_production_roadmap.py`. Update the source definitions, then regenerate these documents.', '',
           f"Source states: **{counts['implemented']} implemented awaiting acceptance, {counts['partial']} partial, {counts['not_implemented']} not implemented.** No deployment acceptance is granted by these source states. The 216 function previews describe the intended UI scope.", '',
           '| Workstream | Source state | Remaining evidence / scope |','| --- | --- | --- |']
    lines += [f'| {g[1]} | {g[3]} | {g[4]} |' for g in GATES]
    lines += ['', 'Implementation order for a team pilot:', '',
              '0. Establish reproducible builds, tests, current documentation and a recorded dependency review.',
              '1. Implement workspace/environment lifecycle and membership isolation.',
              '2. Connect one customer sandbox and validate approval-bound execution and recovery.',
              '3. Complete the selected ingestion, retrieval, permissions and answer-quality scope.',
              '4. Validate live provider behavior, budgets and cost reconciliation.',
              '5. Connect secrets, network controls, monitoring, audit retention and tested recovery.',
              '6. Deploy staging and complete security, load, accessibility and rollback acceptance.', '',
              'Use `PRODUCTION_GAPS_0_16_0.md` for detailed release boundaries and `FUNCTION_IMPLEMENTATION_MAP_0_16_0.csv` for individual planned functions. Historical verification reports retain their original dates; they do not prove acceptance of later revisions.', '']
    return {'docs/PRODUCTION_WORKSTREAMS.json':json.dumps(data,indent=2)+'\n',
            'docs/PRODUCTION_ROADMAP.md':'\n'.join(lines)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    stale=[]
    for name,content in outputs().items():
        target=ROOT/name
        if args.check:
            if not target.exists() or target.read_text(encoding='utf-8')!=content:stale.append(name)
        else:target.write_text(content,encoding='utf-8')
    if stale:raise SystemExit('Roadmap is stale: '+', '.join(stale)+'. Run python scripts/export_production_roadmap.py.')
    print('Current roadmap matches source definitions.' if args.check else 'Current production roadmap exported.')


if __name__=='__main__':main()
