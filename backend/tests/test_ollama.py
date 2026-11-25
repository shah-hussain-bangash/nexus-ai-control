"""Local adapter contracts with disposable databases and HTTP mock transport."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from conftest import auth
from nexus.config import Settings
from nexus.db import InferenceBudget, InferenceCall, WorkspaceAsset
from nexus.inference import route
from nexus.ollama import BASE_URL, response, valid_model_tag
from nexus.workbench import validate_config


MODEL = 'synthetic-local:small'


def config(**changes):
    return dict(provider='Ollama', model=MODEL, endpoint=BASE_URL, credential_ref='',
                token_limit=4096, timeout_ms=2000, temperature=0.2, **changes)


def local_info():
    return {'model_info': {'general.architecture': 'synthetic'}, 'details': {'format': 'gguf'}}


def completion():
    return {'model': MODEL, 'done': True, 'done_reason': 'stop',
            'message': {'role': 'assistant', 'content': 'إجابة تجريبية / Synthetic answer'},
            'prompt_eval_count': 12, 'eval_count': 4}


def setup(ctx, handler=None):
    ctx['settings'].ollama_enabled = 1
    ctx['settings'].ollama_models = MODEL
    with ctx['db'].begin() as db:
        row = WorkspaceAsset(org_id='northstar', kind='model', name='Disposable local model',
                             status='validated', version=2, author_id='test', config=config())
        db.add(row); db.flush(); identifier = row.id
    sent = []

    def mock(request):
        sent.append(request)
        if handler: return handler(request)
        return httpx.Response(200, json=local_info() if request.url.path == '/api/show' else completion())

    ctx['app'].state.provider_transport = httpx.MockTransport(mock)
    headers, _ = auth(ctx)
    headers['Idempotency-Key'] = 'ollama-synthetic-intent-0001'
    return headers, {'model_id': identifier, 'expected_version': 2, 'query': 'سؤال تجريبي',
                     'max_output_tokens': 100}, sent


def test_opt_in_has_no_hosted_budget_or_secret_requirement():
    settings = Settings(secret='s' * 48, agent_secret='a' * 48, ollama_enabled=1, ollama_models=MODEL)
    settings.validate()
    assert settings.live_inference == 0 and settings.provider_prices == '{}' and settings.monthly_budget_usd == '0'
    assert route(config(), settings) == (BASE_URL + '/api/chat', {}, {'input': '0', 'output': '0'})


@pytest.mark.parametrize('changes', [dict(ollama_enabled=2), dict(ollama_enabled=1),
                                   dict(ollama_enabled=1, ollama_models=MODEL, mode='pilot'),
                                   dict(ollama_models='model:cloud'), dict(ollama_models=MODEL + ',' + MODEL),
                                   dict(ollama_models='untagged')])
def test_operator_settings_reject_unsafe_local_configuration(changes):
    with pytest.raises(RuntimeError): Settings(secret='s' * 48, agent_secret='a' * 48, **changes).validate()


@pytest.mark.parametrize('tag', ['untagged', 'x:cloud', 'x:1-cloud', 'X:1-CLOUD',
                               '../x:1', 'x/../y:1', 'https://host/x:1', 'x:tag?query', 'x:'])
def test_nonlocal_or_ambiguous_model_tags_rejected(tag):
    assert not valid_model_tag(tag)


@pytest.mark.parametrize('endpoint', ['http://localhost:11434', 'http://127.0.0.1:11435',
                                    'http://127.0.0.1:11434/api', 'http://127.0.0.1:11434?x=y',
                                    'http://user:pass@127.0.0.1:11434', 'http://127.0.0.1.evil.invalid:11434',
                                    'https://127.0.0.1:11434', 'http://169.254.169.254', 'http://[::1]:11434'])
def test_fixed_numeric_loopback_endpoint_is_required(endpoint):
    with pytest.raises(HTTPException): validate_config('model', {**config(), 'endpoint': endpoint})


def test_local_credentials_cannot_be_saved_or_forwarded():
    with pytest.raises(HTTPException): validate_config('model', {**config(), 'credential_ref': 'env:NEXUS_PROVIDER_TEST_KEY'})
    assert validate_config('model', config())['credential_ref'] == ''


def test_local_execution_uses_normal_api_and_zero_token_cost(ctx):
    headers, body, sent = setup(ctx)
    result = ctx['client'].post('/v1/inference', headers=headers, json=body)
    assert result.status_code == 200, result.text
    row = result.json()
    assert row['status'] == 'completed' and row['reserved'] == row['charged'] == 0
    assert row['result']['answer'] == completion()['message']['content']
    assert [str(request.url) for request in sent] == [BASE_URL + '/api/show', BASE_URL + '/api/chat']
    assert all('authorization' not in request.headers and 'api-key' not in request.headers for request in sent)
    assert json.loads(sent[0].content) == {'model': MODEL}  # No question sent to metadata inspection.
    payload = json.loads(sent[1].content)
    assert payload['stream'] is False and payload['options']['num_predict'] == 100
    assert payload['options']['temperature'] == 0.2 and 'tools' not in payload
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).json()['id'] == row['id']
    assert len(sent) == 2
    runtime = ctx['client'].get('/v1/runtime').json()
    assert runtime['enabled'] and runtime['local_ollama_enabled'] and not runtime['hosted_provider_enabled']
    assert runtime['spent_micro_usd'] == runtime['held_micro_usd'] == 0


def test_local_zero_cost_does_not_consume_or_reset_existing_paid_ledger(ctx):
    headers, body, _ = setup(ctx)
    with ctx['db'].begin() as db:
        from nexus.inference import period
        db.add(InferenceBudget(org_id='northstar', env='production', period=period(), held=900, spent=1000))
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).json()['status'] == 'completed'
    with ctx['db']() as db:
        ledger = db.scalar(select(InferenceBudget))
        assert ledger.held == 900 and ledger.spent == 1000


@pytest.mark.parametrize('changes', [dict(ollama_enabled=0), dict(ollama_models='other:model'), dict(mode='pilot')])
def test_local_route_is_disabled_or_unlisted_before_any_request(ctx, changes):
    headers, body, sent = setup(ctx)
    for key, value in changes.items(): setattr(ctx['settings'], key, value)
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).status_code in (422, 503)
    assert not sent


def test_enabling_local_does_not_enable_hosted_execution():
    settings = Settings(ollama_enabled=1, ollama_models=MODEL)
    with pytest.raises(HTTPException) as error:
        route({**config(), 'provider': 'OpenAI', 'endpoint': 'https://api.openai.com/v1'}, settings)
    assert error.value.status_code == 503


def test_opt_in_is_rechecked_before_admission_even_when_hosted_is_enabled(ctx, monkeypatch):
    import nexus.ollama as local
    headers, body, sent = setup(ctx)
    ctx['settings'].live_inference = 1
    original = local.route
    prepared = []
    def disable_after_preparation(config, settings):
        result = original(config, settings)
        prepared.append(True)
        settings.ollama_enabled = 0
        return result
    monkeypatch.setattr(local, 'route', disable_after_preparation)
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).status_code == 503
    assert len(prepared) == 1 and not sent
    with ctx['db']() as db: assert db.scalar(select(InferenceCall)) is None


def test_local_environment_opt_in_is_parsed_without_loading_operator_files(monkeypatch):
    import nexus.config as module
    values = {'NEXUS_OLLAMA_ENABLED': '1', 'NEXUS_OLLAMA_MODELS': MODEL}
    monkeypatch.setattr(module, 'load_env', lambda: None)
    monkeypatch.setattr(module.os, 'getenv', lambda key: values.get(key))
    settings = Settings.from_env()
    assert settings.ollama_enabled == 1 and settings.ollama_models == MODEL


@pytest.mark.parametrize('metadata', [dict(remote_host='https://ollama.com'), dict(remote_model='upstream'),
                                    dict(model_info={}), dict(details={'format': 'remote'}), dict(model_info=[]),
                                    dict(remote_host=[]), dict(remote_model=False)])
def test_cloud_or_missing_weight_metadata_never_receives_question(ctx, metadata):
    headers, body, sent = setup(ctx, lambda request: httpx.Response(200, json={**local_info(), **metadata}))
    result = ctx['client'].post('/v1/inference', headers=headers, json=body)
    assert result.status_code == 200 and result.json()['status'] == 'unknown'
    assert len(sent) == 1 and sent[0].url.path == '/api/show'
    assert body['query'].encode() not in sent[0].content
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).json()['status'] == 'unknown'
    assert len(sent) == 1


@pytest.mark.parametrize('changes', [dict(done=False), dict(done=1), dict(model='other:model'),
                                   dict(eval_count=True), dict(eval_count=101), dict(prompt_eval_count=-1),
                                   dict(message={'role': 'assistant', 'content': ''}),
                                   dict(message={'role': 'assistant', 'content': 'answer', 'tool_calls': [{}]})])
def test_invalid_local_completions_are_uncertain_without_retry(ctx, changes):
    headers, body, sent = setup(ctx, lambda request: httpx.Response(200, json=(
        local_info() if request.url.path == '/api/show' else {**completion(), **changes})))
    result = ctx['client'].post('/v1/inference', headers=headers, json=body)
    assert result.json()['status'] == 'unknown' and len(sent) == 2
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).json()['status'] == 'unknown'
    assert len(sent) == 2


def test_guardrails_and_role_boundary_prevent_even_metadata_requests(ctx):
    headers, body, sent = setup(ctx)
    with ctx['db'].begin() as db:
        db.add(WorkspaceAsset(org_id='northstar', kind='guardrail', name='Synthetic block', author_id='test',
                              config={'blocked_terms': ['blocked'], 'detect_email': False,
                                      'detect_override': False, 'mode': 'block'}))
    assert ctx['client'].post('/v1/inference', headers=headers, json={**body, 'query': 'blocked'}).status_code == 422
    headers, _ = auth(ctx, 'auditor'); headers['Idempotency-Key'] = 'ollama-unauthorized-0001'
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).status_code == 403
    assert not sent


def test_local_requests_keep_shared_rate_admission(ctx):
    headers, body, sent = setup(ctx)
    ctx['settings'].inference_requests_per_minute = 1
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).json()['status'] == 'completed'
    headers['Idempotency-Key'] = 'ollama-second-intent-0002'
    assert ctx['client'].post('/v1/inference', headers=headers, json=body).status_code == 429
    assert len(sent) == 2


@pytest.mark.parametrize('failure', ['redirect', 'oversize', 'timeout'])
def test_transport_is_bounded_and_does_not_follow_redirects(failure):
    sent = []
    def mock(request):
        sent.append(request)
        if failure == 'redirect': return httpx.Response(302, headers={'Location': 'https://evil.invalid'})
        if failure == 'oversize': return httpx.Response(200, content=b' ' * 5000)
        raise httpx.ReadTimeout('private raw failure', request=request)
    app = SimpleNamespace(state=SimpleNamespace(provider_transport=httpx.MockTransport(mock)))
    with pytest.raises((ValueError, httpx.ReadTimeout)):
        response(app, MODEL, [{'role': 'user', 'content': 'Synthetic'}], 100, 0.2, 2, 4096)
    assert len(sent) == 1


def test_inspection_and_generation_share_one_deadline(monkeypatch):
    import nexus.ollama as local
    clock = {'now': 0}
    monkeypatch.setattr(local, 'time', SimpleNamespace(monotonic=lambda: clock['now']))
    sent = []
    def mock(request):
        sent.append(request)
        if request.url.path == '/api/show':
            clock['now'] = 1.2
            return httpx.Response(200, json=local_info())
        assert request.extensions['timeout']['read'] == pytest.approx(0.8)
        clock['now'] = 2.1
        return httpx.Response(200, json=completion())
    app = SimpleNamespace(state=SimpleNamespace(provider_transport=httpx.MockTransport(mock)))
    with pytest.raises(ValueError, match='deadline'):
        response(app, MODEL, [{'role': 'user', 'content': 'Synthetic'}], 100, 0.2, 2, 4096)
    assert len(sent) == 2


@pytest.mark.parametrize('capabilities,expected', [(['completion', 'thinking'], False), (['completion'], None)])
def test_thinking_is_disabled_only_when_advertised(capabilities, expected):
    sent = []
    def mock(request):
        sent.append(request)
        return httpx.Response(200, json=({**local_info(), 'capabilities': capabilities}
                                         if request.url.path == '/api/show' else completion()))
    app = SimpleNamespace(state=SimpleNamespace(provider_transport=httpx.MockTransport(mock)))
    assert response(app, MODEL, [{'role': 'user', 'content': 'Synthetic'}], 100, 0.2, 2, 4096)['answer']
    payload = json.loads(sent[1].content)
    assert payload.get('think') == expected
    assert ('think' in payload) == ('thinking' in capabilities)
