"""Descriptive metrics for explicitly labelled retrieval cases; no language inference."""
LANGUAGES = ('English', 'Arabic', 'Bilingual', 'Unlabelled')


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
        positives = [row for row in rows if row['expectation'] == 'retrieve']
        negatives = [row for row in rows if row['expectation'] == 'no_results']
        result.append({'language': language, 'case_count': len(rows),
            'passed_cases': sum(row['passed'] for row in rows),
            'retrieve_cases': len(positives), 'no_results_cases': len(negatives),
            'mean_document_recall_at_k': sum(row['document_recall_at_k'] for row in positives)/len(positives) if positives else None,
            'mean_reciprocal_rank': sum(row['reciprocal_rank'] for row in positives)/len(positives) if positives else None,
            'no_results_pass_rate': sum(row['passed'] for row in negatives)/len(negatives) if negatives else None})
    return result
