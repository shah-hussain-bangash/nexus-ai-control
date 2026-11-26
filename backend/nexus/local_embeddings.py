"""Opt-in local embedding client and bounded cosine ranking foundation.

No application routes, source reads, settings loads, model pulls or listeners.
Callers must authorize text before passing it here; vectors are not persisted.
"""
import json
import math
import time

import httpx

from .ollama import BASE_URL, valid_model_tag

MAX_INPUTS = 33  # One query plus at most 32 explicitly selected passages.
MAX_TEXT_BYTES = 4096
MAX_TOTAL_BYTES = 65536
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_DIMENSIONS = 4096


class EmbeddingError(ValueError):
    """Stable public code only; never includes submitted/provider values."""


def reject(code):
    raise EmbeddingError(code) from None


def finite_number(value):
    return type(value) in (int, float) and abs(value) <= 1000000 and math.isfinite(value)


def validate_texts(texts):
    if type(texts) is not list or not 1 <= len(texts) <= MAX_INPUTS:
        reject('EMBEDDING_INPUT_LIMIT')
    size = 0
    for text in texts:
        if type(text) is not str or not text.strip() or '\x00' in text:
            reject('EMBEDDING_INPUT_INVALID')
        try:
            length = len(text.encode('utf-8'))
        except UnicodeError:
            reject('EMBEDDING_INPUT_INVALID')
        if length > MAX_TEXT_BYTES:
            reject('EMBEDDING_INPUT_LIMIT')
        size += length
    if size > MAX_TOTAL_BYTES:
        reject('EMBEDDING_INPUT_LIMIT')


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            reject('EMBEDDING_RESPONSE_INVALID')
        value[key] = item
    return value


def invalid_constant(_):
    reject('EMBEDDING_RESPONSE_INVALID')


def embed_texts(model, texts, *, transport=None, timeout_seconds=10):
    """Use only fixed numeric loopback; metadata is checked before text is sent.

    Transport injection is for trusted in-process tests, never request input.
    The elapsed deadline rejects late responses, including custom transports;
    socket timeouts bound ordinary I/O, not an untrusted blocking transport.
    """
    if not valid_model_tag(model):
        reject('EMBEDDING_MODEL_INVALID')
    texts = texts.copy() if type(texts) is list else texts
    validate_texts(texts)
    if not finite_number(timeout_seconds) or not 0 < timeout_seconds <= 30:
        reject('EMBEDDING_TIMEOUT_INVALID')
    deadline = time.monotonic() + timeout_seconds

    def request(client, path, payload):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            reject('EMBEDDING_DEADLINE')
        with client.stream('POST', BASE_URL + path, json=payload,
                           timeout=httpx.Timeout(remaining, connect=min(2, remaining))) as response:
            if response.status_code != 200:
                reject('EMBEDDING_HTTP_ERROR')
            length = 0; parts = []
            for part in response.iter_bytes():
                length += len(part)
                if length > MAX_RESPONSE_BYTES:
                    reject('EMBEDDING_RESPONSE_LIMIT')
                if time.monotonic() >= deadline:
                    reject('EMBEDDING_DEADLINE')
                parts.append(part)
            data = json.loads(b''.join(parts).decode('utf-8'), object_pairs_hook=unique_object,
                              parse_constant=invalid_constant)
        if time.monotonic() >= deadline:
            reject('EMBEDDING_DEADLINE')
        if type(data) is not dict:
            reject('EMBEDDING_RESPONSE_INVALID')
        return data

    try:
        with httpx.Client(transport=transport, trust_env=False, follow_redirects=False) as client:
            info = request(client, '/api/show', {'model': model})
            # Reject remote proxies and require local weight metadata plus the
            # embedding capability before transmitting any source/query text.
            capabilities = info.get('capabilities')
            if (info.get('remote_host') not in (None, '') or info.get('remote_model') not in (None, '') or
                    type(info.get('model_info')) is not dict or not info['model_info'] or
                    type(info.get('details')) is not dict or info['details'].get('format') != 'gguf' or
                    type(capabilities) is not list or any(type(c) is not str for c in capabilities) or
                    'embedding' not in capabilities):
                reject('EMBEDDING_LOCAL_WEIGHTS_REQUIRED')
            result = request(client, '/api/embed', {'model': model, 'input': texts, 'truncate': False})
    except EmbeddingError:
        raise
    except httpx.TimeoutException:
        reject('EMBEDDING_DEADLINE')
    except (httpx.HTTPError, ValueError, UnicodeError, RecursionError, OverflowError):
        reject('EMBEDDING_RESPONSE_INVALID')
    vectors = result.get('embeddings');tokens = result.get('prompt_eval_count')
    if (result.get('model') != model or type(vectors) is not list or len(vectors) != len(texts) or
            type(tokens) is not int or not 0 <= tokens <= 100000000):
        reject('EMBEDDING_RESPONSE_INVALID')
    dimensions = None; normalized = []
    for vector in vectors:
        if (type(vector) is not list or not 1 <= len(vector) <= MAX_DIMENSIONS or
                any(not finite_number(v) for v in vector) or
                dimensions is not None and len(vector) != dimensions):
            reject('EMBEDDING_VECTOR_INVALID')
        dimensions = len(vector);norm = math.hypot(*vector)
        if not norm:
            reject('EMBEDDING_VECTOR_INVALID')
        normalized.append([value / norm for value in vector])
    if time.monotonic() >= deadline:
        reject('EMBEDDING_DEADLINE')
    return {'model': model, 'vectors': normalized, 'dimensions': dimensions,
            'input_tokens': tokens, 'embedding_requests': 1}


def rank_texts(model, query, texts, *, top_k=5, min_score=0, transport=None, timeout_seconds=10):
    """Rank explicitly supplied authorized passages; no access-control decision."""
    if type(texts) is not list:
        reject('EMBEDDING_INPUT_LIMIT')
    texts = texts.copy()
    if not 1 <= len(texts) < MAX_INPUTS:
        reject('EMBEDDING_INPUT_LIMIT')
    if type(top_k) is not int or not 1 <= top_k <= 10:
        reject('EMBEDDING_RANKING_INVALID')
    if not finite_number(min_score) or not 0 <= min_score <= 1:
        reject('EMBEDDING_RANKING_INVALID')
    batch = embed_texts(model, [query, *texts], transport=transport, timeout_seconds=timeout_seconds)
    query_vector, *vectors = batch['vectors'];scores = []
    for position, vector in enumerate(vectors):
        score = max(-1.0, min(1.0, math.fsum(a*b for a, b in zip(query_vector, vector))))
        if score > 0 and score >= min_score:
            scores.append({'position': position, 'score': round(score, 6)})
    return {'scores': sorted(scores, key=lambda r: (-r['score'], r['position']))[:top_k],
            'model': batch['model'], 'dimensions': batch['dimensions'], 'input_tokens': batch['input_tokens'],
            'embedding_requests': batch['embedding_requests'], 'corpus_passages': len(texts),
            'method': 'Local model embeddings with cosine ranking; uncalibrated similarity'}
