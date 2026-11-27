"""Bounded neural ranking child; loopback embedding requests require pinned settings."""
import json,math,os,re,sys
from pathlib import Path
from .local_embeddings import embed_texts


def rank(payload,*,transport=None):
    if type(payload.get('embedding_digest')) is not str or not re.fullmatch(r'[a-f0-9]{64}',payload['embedding_digest']):raise ValueError('RANKING_FAILED')
    texts=payload['texts'];diverse=payload.get('one_per_document',False);groups=payload.get('groups')
    if type(texts) is not list or not 1<=len(texts)<=32 or any(type(t) is not str or len(t)>700 for t in texts):raise ValueError('CORPUS_LIMIT')
    if type(diverse) is not bool:raise ValueError('RANKING_FAILED')
    if diverse and (type(groups) is not list or len(groups)!=len(texts) or any(type(g) is not int or not 0<=g<20 for g in groups)):raise ValueError('RANKING_FAILED')
    if type(payload['top_k']) is not int or not 1<=payload['top_k']<=10:raise ValueError('RANKING_FAILED')
    threshold=payload['min_score']
    if type(threshold) not in (int,float) or not 0<=threshold<=1:raise ValueError('RANKING_FAILED')
    batch=embed_texts(payload['embedding_model'],[payload['query'],*texts],expected_digest=payload['embedding_digest'],transport=transport)
    query,*vectors=batch['vectors'];scores=[]
    for position,vector in enumerate(vectors):
        score=max(0.0,min(1.0,math.fsum(a*b for a,b in zip(query,vector))))
        if score>0 and score>=threshold:
            value=round(score,6);scores.append({'position':position,'score':value,'semantic_score':value,'lexical_score':0})
    scores.sort(key=lambda s:(-s['score'],s['position']))
    if diverse:
        seen=set();unique=[]
        for score in scores:
            group=groups[score['position']]
            if group not in seen:seen.add(group);unique.append(score)
        scores=unique
    return {'scores':scores[:payload['top_k']],'rank':0,'vocabulary':0,'embedding_model':payload['embedding_model'],
            'embedding_digest':payload['embedding_digest'],'embedding_dimensions':batch['dimensions'],
            'embedding_requests':1,'metadata_requests':3}


def main():
    if os.name=='posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
        resource.setrlimit(resource.RLIMIT_CPU,(6,6))
        resource.setrlimit(resource.RLIMIT_FSIZE,(2097152,2097152))
    source,out=map(Path,sys.argv[1:3])
    try:
        if source.stat().st_size>1048576:raise ValueError('CORPUS_LIMIT')
        payload=json.loads(source.read_text(encoding='utf-8'))
        result=embedding_batch(payload) if payload.get('task') in ('index_build','index_query') else rank(payload)
    except Exception:result={'error_code':'RANKING_FAILED'}
    out.write_text(json.dumps(result),encoding='utf-8')


def embedding_batch(payload,*,transport=None):
    if type(payload.get('embedding_digest')) is not str or not re.fullmatch(r'[a-f0-9]{64}',payload['embedding_digest']):raise ValueError('RANKING_FAILED')
    if payload.get('task')=='index_build':
        texts=payload['texts']
        if type(texts) is not list or not 1<=len(texts)<=32 or any(type(t) is not str or len(t)>700 for t in texts):raise ValueError('CORPUS_LIMIT')
    elif payload.get('task')=='index_query':texts=[payload['query']]
    else:raise ValueError('RANKING_FAILED')
    batch=embed_texts(payload['embedding_model'],texts,expected_digest=payload['embedding_digest'],transport=transport)
    return {'vectors':batch['vectors'],'dimensions':batch['dimensions'],'embedding_model':payload['embedding_model'],
            'embedding_digest':payload['embedding_digest'],'embedding_requests':1,'metadata_requests':3}


if __name__=='__main__':main()
