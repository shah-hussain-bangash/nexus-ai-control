"""Server-owned local neural search settings and strict worker result validation."""
import re
from .ollama import valid_model_tag
from .ranking_result import normalize_result

METHOD='Local Ollama embeddings / positive cosine similarity; no lexical blend'
NORMALIZATION_VERSION='local-neural-v1'


def configuration(settings):
    model=settings.ollama_embedding_model;digest=settings.ollama_embedding_digest
    if (settings.mode!='local' or settings.ollama_embedding_enabled!=1 or not valid_model_tag(model) or
            type(digest) is not str or not re.fullmatch(r'[a-f0-9]{64}',digest)):
        return None
    return {'embedding_model':model,'embedding_digest':digest}


def empty_result(model,digest):
    return {'scores':[],'rank':0,'vocabulary':0,'embedding_model':model,'embedding_digest':digest,
            'embedding_dimensions':0,'embedding_requests':0,'metadata_requests':0}


def checked_result(value,count,top_k,model,digest):
    invalid={'error_code':'RANKING_FAILED'}
    if type(value) is not dict:return invalid
    if set(value)=={'error_code'}:return normalize_result(value,count,top_k)
    fields={'rank','vocabulary','scores','embedding_model','embedding_digest','embedding_dimensions','embedding_requests','metadata_requests'}
    if set(value)!=fields or value['embedding_model']!=model or value['embedding_digest']!=digest:return invalid
    dimensions=value['embedding_dimensions'];requests=value['embedding_requests'];metadata=value['metadata_requests']
    if (type(dimensions) is not int or not (1<=dimensions<=4096 if count else dimensions==0) or
            type(requests) is not int or requests!=(1 if count else 0) or
            type(metadata) is not int or metadata!=(3 if count else 0)):
        return invalid
    cleaned=normalize_result({key:value[key] for key in ('rank','vocabulary','scores')},count,top_k)
    if cleaned.get('error_code') or cleaned['rank']!=0 or cleaned['vocabulary']!=0:return invalid
    if any(s['lexical_score']!=0 or s['semantic_score']!=s['score'] for s in cleaned['scores']):return invalid
    if cleaned['scores']!=sorted(cleaned['scores'],key=lambda s:(-s['score'],s['position'])):return invalid
    return {**cleaned,**{key:value[key] for key in fields-{'rank','vocabulary','scores'}}}
