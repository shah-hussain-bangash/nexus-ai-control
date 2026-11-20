"""Validate the bounded local ranking process protocol before saving it."""
import math

ERROR_CODES=frozenset({'SEARCH_TIMEOUT','RANKING_FAILED','VOCABULARY_LIMIT','CORPUS_LIMIT'})
SCORE_FIELDS=frozenset({'position','score','semantic_score','lexical_score'})


def normalize_result(value,chunk_count,top_k):
    invalid={'error_code':'RANKING_FAILED'}
    if type(value) is not dict or not set(value).issubset({'rank','vocabulary','scores','error_code'}):return invalid
    error=value.get('error_code')
    if error is not None:
        if type(error) is not str or (error and error not in ERROR_CODES):return invalid
        if error:return {'error_code':error}
    if not all(key in value for key in ('rank','vocabulary','scores')):return invalid
    rank=value['rank'];vocabulary=value['vocabulary'];scores=value['scores']
    if type(rank) is not int or not 0<=rank<=32 or type(vocabulary) is not int or not 0<=vocabulary<=1024:return invalid
    if type(scores) is not list or len(scores)>top_k:return invalid
    clean=[];seen=set()
    try:
        for score in scores:
            if type(score) is not dict or set(score)!=SCORE_FIELDS:return invalid
            position=score['position']
            if type(position) is not int or not 0<=position<chunk_count or position in seen:return invalid
            for field in ('score','semantic_score','lexical_score'):
                number=score[field]
                if type(number) not in (int,float) or not math.isfinite(number) or not 0<=number<=1:return invalid
            seen.add(position);clean.append(dict(score))
    except (TypeError,ValueError,OverflowError):return invalid
    return {'rank':rank,'vocabulary':vocabulary,'scores':clean}
