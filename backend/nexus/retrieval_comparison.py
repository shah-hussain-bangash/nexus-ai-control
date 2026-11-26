"""Compare saved measurements only; authorization and definition checks precede this helper."""
import math


def score(value):
    if value is None: return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Unsupported saved retrieval score.')
    return value


def delta(before, after):
    return round(after-before, 12) if before is not None and after is not None else None


def classify(values):
    higher = any(value > 0 for value in values if value is not None)
    lower = any(value < 0 for value in values if value is not None)
    return 'mixed' if higher and lower else 'improved' if higher else 'regressed' if lower else 'unchanged'


def frame(case):
    if type(case['passed']) is not bool: raise ValueError('Unsupported saved outcome.')
    positive = case['expectation'] == 'retrieve'
    return {'passed': case['passed'],
        'document_recall_at_k': score(case['document_recall_at_k']) if positive else None,
        'document_precision_at_k': score(case['document_precision_at_k']) if positive else None,
        'reciprocal_rank': score(case['reciprocal_rank']) if positive else None,
        'unexpected_document_count': len(case['unexpected_document_ids'])}


def snapshot(detail):
    cases = detail['result']['cases']; positives = [frame(row) for row in cases if row['expectation']=='retrieve']
    passed = sum(row['passed'] for row in cases)
    if detail['case_count'] != len(cases) or detail['passed_cases'] != passed or detail['status'] != ('passed' if passed==len(cases) else 'failed'):
        raise ValueError('Saved outcome totals are inconsistent.')
    def mean(key):return sum(row[key] for row in positives)/len(positives) if positives else None
    return {'id': detail['id'], 'name': detail['name'], 'created': detail['created'],
        'status': detail['status'], 'case_count': len(cases), 'passed_cases': passed,
        'mean_document_recall_at_k': mean('document_recall_at_k'),
        'mean_document_precision_at_k': mean('document_precision_at_k'),
        'mean_reciprocal_rank': mean('reciprocal_rank'), 'stale': detail['stale'],
        'normalization_version': detail['result'].get('normalization_version','legacy-unversioned'),
        'corpus_fingerprint': detail['result']['corpus_fingerprint'],
        'one_per_document':detail['result'].get('one_per_document',False)}


def compare_details(baseline, candidate):
    before, after = snapshot(baseline), snapshot(candidate)
    if before['case_count'] != after['case_count']:raise ValueError('Saved case counts differ.')
    rows=[];counts={key:0 for key in ('improved','regressed','mixed','unchanged')}
    for index,(left,right) in enumerate(zip(baseline['result']['cases'],candidate['result']['cases'])):
        a,b=frame(left),frame(right)
        changes={key:delta(a[key],b[key]) for key in ('document_recall_at_k','document_precision_at_k','reciprocal_rank')}
        changes['passed']=int(b['passed'])-int(a['passed'])
        changes['unexpected_document_count']=b['unexpected_document_count']-a['unexpected_document_count']
        direction=classify([changes['passed'],changes['document_recall_at_k'],changes['document_precision_at_k'],
                            changes['reciprocal_rank'],-changes['unexpected_document_count']])
        counts[direction]+=1
        rows.append({'index':index,'change':direction,'baseline':a,'candidate':b,'delta':changes,
            'returned_sources_changed':list(dict.fromkeys(left['retrieved_document_ids'])) != list(dict.fromkeys(right['retrieved_document_ids']))})
    return {'baseline':before,'candidate':after,'case_changes':counts,'cases':rows,
        'delta':{**{key:delta(before[key],after[key]) for key in ('mean_document_recall_at_k','mean_document_precision_at_k','mean_reciprocal_rank')},
            'passed_cases':after['passed_cases']-before['passed_cases']},
        'corpus_changed':before['corpus_fingerprint']!=after['corpus_fingerprint'],
        'normalization_changed':before['normalization_version']!=after['normalization_version'],
        'boundary':'Saved keyword-retrieval metrics only. Source or method changes can affect scores. No reranking, generated-answer grading or deployment acceptance.'}
