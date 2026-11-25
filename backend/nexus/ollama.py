"""Opt-in local Ollama adapter. Fixed numeric loopback; never pulls models."""
import json
import re
import time

import httpx

from .security import fail


BASE_URL = 'http://127.0.0.1:11434'


def valid_model_tag(value):
    return (type(value) is str and len(value) <= 100 and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*:[A-Za-z0-9][A-Za-z0-9._-]*', value) is not None and
            not value.lower().endswith(('-cloud', ':cloud')))


def validate_config(config):
    if config['endpoint'] not in (BASE_URL, BASE_URL + '/') or config.get('credential_ref'):
        fail(422, 'OLLAMA_LOCAL_ENDPOINT_REQUIRED',
             'Use http://127.0.0.1:11434 without credentials for local Ollama.')
    if not valid_model_tag(config['model']):
        fail(422, 'OLLAMA_LOCAL_MODEL_REQUIRED', 'Choose an explicit local model:tag; cloud tags are not supported.')


def route(config, settings):
    validate_config(config)
    if settings.mode != 'local' or not settings.ollama_enabled:
        fail(503, 'OLLAMA_DISABLED', 'Local Ollama requires an explicit operator opt-in in local mode.')
    if config['model'] not in {item.strip() for item in settings.ollama_models.split(',')}:
        fail(422, 'OLLAMA_MODEL_NOT_ALLOWED', 'An operator must allow this exact installed local model:tag.')
    return BASE_URL + '/api/chat', {}, {'input': '0', 'output': '0'}


def response(app, model, messages, max_tokens, temperature, timeout, max_bytes):
    """Inspect local model metadata, then make one bounded non-streaming call."""
    deadline = time.monotonic() + timeout

    def request(client, path, payload):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('ollama_deadline')
        with client.stream('POST', BASE_URL + path, json=payload,
                           timeout=httpx.Timeout(remaining, connect=min(10, remaining))) as result:
            if result.status_code != 200:
                raise ValueError('ollama_non_success')
            parts = []; length = 0
            for part in result.iter_bytes():
                length += len(part)
                if time.monotonic() >= deadline or length > max_bytes:
                    raise ValueError('ollama_response_limit_or_deadline')
                parts.append(part)
            value = json.loads(b''.join(parts))
        if time.monotonic() >= deadline or type(value) is not dict:
            raise ValueError('ollama_invalid_or_late_response')
        return value

    transport = getattr(app.state, 'provider_transport', None)
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False) as client:
        info = request(client, '/api/show', {'model': model})
        # A local server can proxy cloud models. Refuse remote metadata and
        # require local weight metadata before transmitting question/evidence.
        if (info.get('remote_host') not in (None, '') or info.get('remote_model') not in (None, '') or
                type(info.get('model_info')) is not dict or not info['model_info'] or
                type(info.get('details')) is not dict or info['details'].get('format') != 'gguf'):
            raise ValueError('ollama_local_weights_required')
        capabilities = info.get('capabilities', [])
        if type(capabilities) is not list or any(type(item) is not str for item in capabilities):
            raise ValueError('ollama_invalid_capabilities')
        payload = {
            'model': model, 'messages': messages, 'stream': False,
            'options': {'num_predict': max_tokens, 'temperature': temperature},
        }
        # Keep the bounded output allowance for the answer on thinking models.
        if 'thinking' in capabilities:
            payload['think'] = False
        data = request(client, '/api/chat', payload)
    message = data.get('message')
    if (data.get('done') is not True or data.get('model') != model or type(message) is not dict or
            message.get('role') != 'assistant' or message.get('tool_calls')):
        raise ValueError('ollama_invalid_output')
    answer = message.get('content')
    ins, outs = data.get('prompt_eval_count'), data.get('eval_count')
    if (type(answer) is not str or not answer.strip() or len(answer) > 100000 or
            type(ins) is not int or not 0 <= ins <= 100000000 or
            type(outs) is not int or not 0 <= outs <= max_tokens):
        raise ValueError('ollama_invalid_output_or_usage')
    reason = data.get('done_reason', '')
    if type(reason) is not str or len(reason) > 60 or time.monotonic() >= deadline:
        raise ValueError('ollama_invalid_or_late_completion')
    return {'answer': answer, 'input_tokens': ins, 'output_tokens': outs,
            'provider_request_id': '', 'finish_reason': reason}
