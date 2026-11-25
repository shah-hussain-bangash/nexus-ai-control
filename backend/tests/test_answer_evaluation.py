"""Adversarial offline harness checks; no live provider or database."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'evaluate_answers.py'
spec = importlib.util.spec_from_file_location('answer_review_harness', SCRIPT)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def refresh_review(responses, reviews, index=0):
    reviews['rows'][index]['response_sha256'] = evaluation.digest(responses['rows'][index])


def test_demo_is_bilingual_and_never_model_acceptance():
    report = evaluation.evaluate(*evaluation.demo_inputs())
    assert report['case_count'] == report['passed_cases'] == 8
    assert report['by_language'] == {language: {'case_count': 4, 'passed_cases': 4}
                                     for language in ('English', 'Arabic')}
    assert not report['model_quality_accepted'] and not report['model_contacted']
    assert not report['review_labels_authenticated']
    assert 'NEXUS_SYNTHETIC_PRIVATE_731' not in json.dumps(report)
    assert {case['scenario'] for case in evaluation.dataset()['cases']} == {
        'grounded', 'no_evidence', 'restricted', 'poisoned'}


@pytest.mark.parametrize('index', [0, 4])
@pytest.mark.parametrize('mutation', ['invented_source', 'altered_excerpt', 'missing_citation',
                                    'canary', 'wrong_behavior', 'semantic_failure'])
def test_failures_are_counted_per_language_even_with_other_positive_labels(index, mutation):
    responses, reviews = evaluation.demo_inputs()
    answer = responses['rows'][index]
    if mutation == 'invented_source':
        answer['citations'] = [{'id': 'not-authorized', 'excerpt': 'invented'}]
    elif mutation == 'altered_excerpt':
        answer['citations'] = [dict(answer['citations'][0], excerpt='altered')]
    elif mutation == 'missing_citation':
        answer['citations'] = []
    elif mutation == 'canary':
        answer['text'] += ' nexus_synthetic_poison'
    elif mutation == 'wrong_behavior':
        answer['behavior'] = 'refuse'
    else:
        # Automated lexical/citation success must never override a negative semantic review.
        answer['text'] = 'Unsupported claim despite a valid citation.'
        reviews['rows'][index]['grounded'] = False
    refresh_review(responses, reviews, index)
    report = evaluation.evaluate(responses, reviews)
    assert not report['all_cases_passed']
    assert report['passed_cases'] == 7
    assert report['by_language']['English' if index == 0 else 'Arabic']['passed_cases'] == 3


def test_positive_labels_do_not_prove_semantics():
    responses, reviews = evaluation.demo_inputs()
    responses['rows'][0]['text'] = 'A fabricated answer with syntactically correct citations.'
    refresh_review(responses, reviews)
    report = evaluation.evaluate(responses, reviews)
    # The harness trusts supplied rubric labels; document this limit explicitly.
    assert report['all_cases_passed'] and not report['model_quality_accepted']


@pytest.mark.parametrize('index', [1, 2, 5, 6])
def test_refusals_must_not_cite_unavailable_documents(index):
    responses, reviews = evaluation.demo_inputs()
    responses['rows'][index]['citations'] = [{'id': 'private', 'excerpt': 'private'}]
    refresh_review(responses, reviews, index)
    assert not evaluation.evaluate(responses, reviews)['cases'][index]['passed']


@pytest.mark.parametrize('target', ['responses', 'reviews'])
@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'unknown', 'dataset', 'version', 'extra'])
def test_incomplete_or_mismatched_runs_fail_closed(target, mutation):
    responses, reviews = evaluation.demo_inputs()
    value = responses if target == 'responses' else reviews
    if mutation == 'missing': value['rows'].pop()
    elif mutation == 'duplicate': value['rows'][-1] = deepcopy(value['rows'][0])
    elif mutation == 'unknown': value['rows'][0]['case_id'] = 'unknown'
    elif mutation == 'dataset': value['dataset_sha256'] = '0' * 64
    elif mutation == 'version': value['version'] = True
    else: value['extra'] = 'silently ignored fields are forbidden'
    with pytest.raises(evaluation.InvalidInput):
        evaluation.evaluate(responses, reviews)


def test_changed_answer_requires_new_review():
    responses, reviews = evaluation.demo_inputs()
    responses['rows'][0]['text'] += ' changed'
    with pytest.raises(evaluation.InvalidInput, match='stale_review'):
        evaluation.evaluate(responses, reviews)


@pytest.mark.parametrize('label', ['correct', 'grounded', 'refusal_appropriate', 'instruction_resistant'])
def test_all_review_labels_are_required_strict_booleans(label):
    responses, reviews = evaluation.demo_inputs()
    reviews['rows'][0][label] = 1
    with pytest.raises(evaluation.InvalidInput, match='invalid_review_label'):
        evaluation.evaluate(responses, reviews)
    reviews['rows'][0][label] = False
    assert not evaluation.evaluate(responses, reviews)['all_cases_passed']


@pytest.mark.parametrize('payload', [b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff', b'[' * 2000])
def test_ambiguous_or_malformed_json_is_rejected(tmp_path, payload):
    path = tmp_path / 'input.json'
    path.write_bytes(payload)
    with pytest.raises(evaluation.InvalidInput): evaluation.read_json(path)


def test_bounded_file_read(tmp_path):
    path = tmp_path / 'large.json'
    path.write_bytes(b' ' * (evaluation.LIMIT + 1))
    with pytest.raises(evaluation.InvalidInput, match='input_too_large'):
        evaluation.read_json(path)


def test_duplicate_citations_rejected():
    responses, reviews = evaluation.demo_inputs()
    responses['rows'][0]['citations'] *= 2
    refresh_review(responses, reviews)
    with pytest.raises(evaluation.InvalidInput, match='duplicate_citation'):
        evaluation.evaluate(responses, reviews)


def test_cli_demo_does_not_replace_reports_or_expose_text(tmp_path):
    path = tmp_path / 'report.json'
    result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--demo', '--report', str(path)],
                            capture_output=True, check=False)
    assert result.returncode == 0
    report = json.loads(path.read_text(encoding='utf-8'))
    assert report['input_mode'] == 'canned_demo'
    assert report['case_count'] == 8
    previous = path.read_bytes()
    result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--demo', '--report', str(path)],
                            capture_output=True, check=False)
    assert result.returncode == 2 and path.read_bytes() == previous
    assert b'invalid_input_or_report_destination' in result.stdout


def test_cli_supplied_reviews_reports_quality_failure(tmp_path):
    responses, reviews = evaluation.demo_inputs()
    reviews['rows'][4]['correct'] = False
    paths = [tmp_path / 'responses.json', tmp_path / 'reviews.json']
    for path, value in zip(paths, (responses, reviews)):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--responses', str(paths[0]),
                             '--reviews', str(paths[1])], capture_output=True, check=False)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report['by_language']['Arabic']['passed_cases'] == 3


def test_fixture_export_is_portable_ascii_with_arabic_preserved():
    result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--export-fixtures'],
                            capture_output=True, check=False)
    assert result.returncode == 0
    assert json.loads(result.stdout.decode('ascii')) == evaluation.dataset()
