"""Bounded, network-free corpus LSA and lexical ranking in an isolated process."""
from collections import Counter
import json,math,os,re,sys
from pathlib import Path
from .search_text import search_tokens

def rank(payload):
 import numpy as np
 texts=payload['texts'];query=payload['query'];counts=[Counter(search_tokens(t)) for t in texts]
 if not 1<=len(texts)<=128 or any(len(t)>700 for t in texts):raise ValueError('CORPUS_LIMIT')
 vocab=sorted(set().union(*(c.keys() for c in counts)))
 if len(vocab)>1024:raise ValueError('VOCABULARY_LIMIT')
 if not vocab:return {'scores':[],'rank':0,'vocabulary':0}
 n=len(texts);df={t:sum(t in c for c in counts) for t in vocab};idf={t:math.log((1+n)/(1+df[t]))+1 for t in vocab}
 matrix=np.array([[(1+math.log(c[t]))*idf[t] if c[t] else 0 for t in vocab] for c in counts],dtype=np.float64)
 norms=np.linalg.norm(matrix,axis=1);matrix/=np.where(norms==0,1,norms)[:,None]
 terms=Counter(search_tokens(query));q=np.array([(1+math.log(terms[t]))*idf[t] if terms[t] else 0 for t in vocab]);qn=float(np.linalg.norm(q))
 if not qn:return {'scores':[],'rank':0,'vocabulary':len(vocab)}
 q/=qn
 # A low-rank, corpus-fitted space: no pretrained embeddings or language model.
 _,s,vt=np.linalg.svd(matrix,full_matrices=False)
 k=min(payload['dimensions'],max(1,min(matrix.shape)//2),sum(s>1e-10));basis=vt[:k];vectors=matrix@basis.T;projected=q@basis.T
 denominator=np.linalg.norm(vectors,axis=1)*float(np.linalg.norm(projected));lsa=np.divide(vectors@projected,denominator,out=np.zeros(n),where=denominator>1e-12);lsa=np.clip(lsa,0,1)
 avg=sum(sum(c.values()) for c in counts)/n or 1;lex=[]
 for c in counts:
  score=0
  for t in terms:
   if t in df and c[t]:score+=math.log(1+(n-df[t]+.5)/(df[t]+.5))*c[t]*2.2/(c[t]+1.2*(.25+.75*sum(c.values())/avg))
  lex.append(score)
 ceiling=max(lex) or 1;weight=payload['semantic_weight'];scores=[]
 for i in range(n):
  lexical=lex[i]/ceiling;semantic=float(lsa[i]);combined=weight*semantic+(1-weight)*lexical
  if combined>0 and combined>=payload['min_score']:scores.append({'position':i,'score':round(combined,6),'semantic_score':round(semantic,6),'lexical_score':round(lexical,6)})
 return {'scores':sorted(scores,key=lambda r:(-r['score'],r['position']))[:payload['top_k']],'rank':int(k),'vocabulary':len(vocab)}

def main():
 if os.name=='posix':
  import resource
  resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824));resource.setrlimit(resource.RLIMIT_CPU,(6,6));resource.setrlimit(resource.RLIMIT_FSIZE,(8388608,8388608))
 source,out=map(Path,sys.argv[1:3])
 try:
  if source.stat().st_size>1048576:raise ValueError('CORPUS_LIMIT')
  result=rank(json.loads(source.read_text(encoding='utf-8')))
 except ValueError as exc:result={'error_code':str(exc) if str(exc) in ('CORPUS_LIMIT','VOCABULARY_LIMIT') else 'RANKING_FAILED'}
 except Exception:result={'error_code':'RANKING_FAILED'}
 out.write_text(json.dumps(result),encoding='utf-8')
if __name__=='__main__':main()
