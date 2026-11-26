"""Explicit synthetic local-embedding exercise. Default check makes no requests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from nexus.local_embeddings import EmbeddingError, rank_texts

BOUNDARY = ('Synthetic local embedding transport/ranking exercise only. No application '
            'records or customer system are read. Similarity is not calibrated confidence '
            'or semantic quality acceptance. No model is downloaded; no vector index, '
            'dashboard integration, customer acceptance or production readiness is established.')


def exercise(model, output, *, transport=None):
    start = time.monotonic()
    # Fixed synthetic text only. No file/intake/query argument is accepted.
    query = 'Independent approval for procurement / موافقة مستقلة للمشتريات'
    texts = ['Synthetic policy: purchases need independent approval.',
             'سياسة اصطناعية: تتطلب المشتريات موافقة مستقلة.',
             'Synthetic cafeteria menu: tea and coffee.']
    result = rank_texts(model, query, texts, top_k=3, transport=transport)
    report = {'format': 'nexus-local-embedding-exercise', 'format_version': 1,
              'completed': True, 'model': result['model'], 'dimensions': result['dimensions'],
              'input_tokens': result['input_tokens'], 'embedding_requests': result['embedding_requests'],
              'corpus_passages': len(texts), 'ranked_passages': len(result['scores']),
              'elapsed_ms': round((time.monotonic()-start)*1000, 3),
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': hashlib.sha256((ROOT/'backend/nexus/local_embeddings.py').read_bytes()).hexdigest(),
              'semantic_quality_accepted': False, 'production_ready': False, 'boundary': BOUNDARY}
    output = Path(output);output.mkdir(parents=True, exist_ok=True)
    target = output/('synthetic-local-embeddings-'+uuid.uuid4().hex+'.json')
    # Publish only a complete unsigned receipt; no raw vectors/texts are retained.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output, prefix='.embedding-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(report, indent=2)+'\n');stream.flush()
        temporary.replace(target)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return {**report, 'report': str(target)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-local', action='store_true')
    parser.add_argument('--model', default='')
    args = parser.parse_args(argv)
    if not args.run_local:
        print(json.dumps({'completed': False, 'local_call_requested': False, 'model_downloaded': False,
                          'message': 'No request made. Explicit --run-local and an installed local model:tag are required.', 'boundary': BOUNDARY}))
        return 0
    try:
        report = exercise(args.model, ROOT/'backend/data/drills')
    except EmbeddingError as error:
        print(json.dumps({'completed': False, 'error_code': str(error), 'boundary': BOUNDARY}));return 1
    except (OSError, ValueError):
        print(json.dumps({'completed': False, 'error_code': 'EMBEDDING_EXERCISE_FAILED', 'boundary': BOUNDARY}));return 1
    print(json.dumps(report));return 0


if __name__ == '__main__':
    raise SystemExit(main())
