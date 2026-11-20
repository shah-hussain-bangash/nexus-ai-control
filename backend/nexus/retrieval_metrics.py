"""Retrieval metrics and explicit precision targets; no language inference."""
LANGUAGES = ('English', 'Arabic', 'Bilingual', 'Unlabelled')


def measure_case(case):
    expected = set(case['expected_document_ids'])
    retrieved = list(dict.fromkeys(case['retrieved_document_ids']))
    matched = len(expected.intersection(retrieved))
    precision = (matched/len(retrieved) if retrieved else 0) if case['expectation']=='retrieve' else None
    measured = {**case, 'document_precision_at_k': precision,
            'retrieved_document_count': len(retrieved), 'matched_expected_document_count': matched,
            'unexpected_document_ids': [identifier for identifier in retrieved if identifier not in expected]}
    measured.pop('precision_threshold_passed', None)
    minimum = case.get('minimum_precision_percent')
    if minimum is not None:
        if type(minimum) is not int or not 0 <= minimum <= 100 or case['expectation'] != 'retrieve':
            raise ValueError('Unsupported saved precision target.')
        # Integer comparison avoids deciding a target from rounded display scores.
        measured['precision_threshold_passed'] = matched*100 >= minimum*len(retrieved) if retrieved else minimum==0
    return measured


def result_with_precision(result):
    # Derive from saved identifiers; never rerun retrieval or mutate historical JSON.
    cases = [measure_case(case) for case in result['cases']]
    positives = [case for case in cases if case['expectation']=='retrieve']
    return {**result, 'cases': cases,
            'mean_document_precision_at_k': sum(case['document_precision_at_k'] for case in positives)/len(positives) if positives else None}


def language_metrics(cases):
    groups = {language: [] for language in LANGUAGES}
    for case in cases:
        language = case.get('query_language')
        language = 'Unlabelled' if language is None else language
        if type(language) is not str or language not in groups:
            raise ValueError('Unsupported saved query language.')
        groups[language].append(case)
    result = []
    for language, rows in groups.items():
        if not rows: continue
        positives = [measure_case(row) for row in rows if row['expectation'] == 'retrieve']
        negatives = [row for row in rows if row['expectation'] == 'no_results']
        result.append({'language': language, 'case_count': len(rows),
            'passed_cases': sum(row['passed'] for row in rows),
            'retrieve_cases': len(positives), 'no_results_cases': len(negatives),
            'mean_document_recall_at_k': sum(row['document_recall_at_k'] for row in positives)/len(positives) if positives else None,
            'mean_document_precision_at_k': sum(row['document_precision_at_k'] for row in positives)/len(positives) if positives else None,
            'mean_reciprocal_rank': sum(row['reciprocal_rank'] for row in positives)/len(positives) if positives else None,
            'no_results_pass_rate': sum(row['passed'] for row in negatives)/len(negatives) if negatives else None})
    return result
