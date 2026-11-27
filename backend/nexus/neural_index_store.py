"""Bounded persistent vector storage for trusted server-side embedding results.

No HTTP routes, provider calls or vector-file imports. Runtime build/search
integration must supply operator-bound model identity and authorized snapshots.
"""
import math
import re
from sqlalchemy import select,update,delete,func
from .db import NeuralIndex,NeuralVector,KnowledgeDocument,DocumentChunk,Organization,User
from .documents import can_read
from .local_embeddings import finite_number
from .ollama import valid_model_tag
from .runtime_context import runtime_environment,environment_user_allowed
from .security import fail,digest,PERMISSIONS
from .service import canonical,audit

MAX_INDEXES=20
MAX_ENTRIES=32


def model_identity(model,model_digest):
    if not valid_model_tag(model) or type(model_digest) is not str or not re.fullmatch(r'[a-f0-9]{64}',model_digest):
        fail(422,'INDEX_MODEL_INVALID','Use an explicit local model tag and digest.')


def vector_values(value,dimensions=None,*,normalize=True):
    if (type(value) is not list or not 1<=len(value)<=4096 or dimensions is not None and len(value)!=dimensions or
            any(not finite_number(item) for item in value)):
        fail(422,'INDEX_VECTOR_INVALID','Vector dimensions or values are unsupported.')
    copied=value.copy();norm=math.hypot(*copied)
    if not norm or not normalize and abs(norm-1)>1e-9:fail(422,'INDEX_VECTOR_INVALID','Use nonzero normalized vector values.')
    return [v/norm for v in copied] if normalize else copied


def prepare_entries(entries):
    if type(entries) is not list or not 1<=len(entries)<=MAX_ENTRIES:
        fail(422,'INDEX_CAPACITY','An index snapshot supports 1–32 passages.')
    result=[];seen=set();dimensions=None
    for entry in entries.copy():
        if type(entry) is not dict or set(entry)!={'document_id','document_version','position','sha256','vector'}:
            fail(422,'INDEX_ENTRY_INVALID','Use complete server-side chunk snapshots.')
        entry=entry.copy();id=entry['document_id'];version=entry['document_version'];position=entry['position'];sha=entry['sha256']
        if (type(id) is not str or not 1<=len(id)<=64 or type(version) is not int or version<1 or
                type(position) is not int or not 0<=position<=10000 or type(sha) is not str or not re.fullmatch(r'[a-f0-9]{64}',sha) or
                (id,position) in seen):fail(422,'INDEX_ENTRY_INVALID','Use distinct valid server-side chunk snapshots.')
        vector=vector_values(entry['vector'],dimensions);dimensions=len(vector);seen.add((id,position))
        result.append({'document_id':id,'document_version':version,'position':position,'sha256':sha,'vector':vector})
    if len({e['document_id'] for e in result})>20:fail(422,'INDEX_CAPACITY','Select at most 20 readable documents.')
    result.sort(key=lambda e:(e['document_id'],e['position']))
    if len(canonical(result).encode('utf-8'))>2*1024*1024:fail(422,'INDEX_CAPACITY','The vector snapshot exceeds 2 MiB.')
    return result,dimensions


def current_actor(db,user):
    environment=runtime_environment(db,user.org_id)
    db.execute(update(Organization).where(Organization.id==user.org_id).values(name=Organization.name))
    current=db.scalar(select(User).where(User.id==user.id,User.org_id==user.org_id).execution_options(populate_existing=True))
    if not current or not current.active or not environment_user_allowed(db,current.id,current.org_id,environment,allow_non_staging=True):
        fail(404,'INDEX_NOT_FOUND','Index is unavailable in your authorized scope.')
    return current,environment


def owned(db,id,user,environment):
    row=db.scalar(select(NeuralIndex).where(NeuralIndex.id==id,NeuralIndex.org_id==user.org_id,NeuralIndex.env==environment).execution_options(populate_existing=True))
    if not row or row.author_id!=user.id and 'policy' not in PERMISSIONS.get(user.role,set()):
        fail(404,'INDEX_NOT_FOUND','Index is unavailable in your authorized scope.')
    return row


def metadata(row):
    return {key:getattr(row,key) for key in ('id','name','model','model_digest','dimensions','entry_count','status','version','created')}


def checked_sources(db,user,environment,entries):
    docs={};chunks={}
    for entry in entries:
        id=entry['document_id']
        if id not in docs:
            doc=db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id==id,KnowledgeDocument.org_id==user.org_id,KnowledgeDocument.env==environment).execution_options(populate_existing=True))
            if not doc or not can_read(doc,user,environment):fail(409,'INDEX_SOURCE_CHANGED','A source is no longer current and readable.')
            if digest(doc.content)!=doc.content_hash:fail(409,'INDEX_SOURCE_CHANGED','A source is no longer current and readable.')
            docs[id]=doc
        doc=docs[id]
        if doc.version!=entry['document_version']:fail(409,'INDEX_SOURCE_CHANGED','A source is no longer current and readable.')
        chunk=db.scalar(select(DocumentChunk).where(DocumentChunk.org_id==user.org_id,DocumentChunk.env==environment,
            DocumentChunk.document_id==id,DocumentChunk.document_version==doc.version,DocumentChunk.position==entry['position']).execution_options(populate_existing=True))
        if not chunk or chunk.content_hash!=entry['sha256'] or digest(chunk.text)!=chunk.content_hash:
            fail(409,'INDEX_SOURCE_CHANGED','A source is no longer current and readable.')
        chunks[(id,entry['position'])]=chunk
    sources=[{'id':id,'version':doc.version,'sha256':doc.content_hash} for id,doc in sorted(docs.items())]
    return sources,docs,chunks


def snapshot_hash(model,model_digest,sources,entries):
    return digest(canonical({'model':model,'model_digest':model_digest,'sources':sources,'entries':entries}))


def create_index(db,user,*,name,model,model_digest,entries,key):
    """Caller owns the transaction; validated server results only, never HTTP input."""
    model_identity(model,model_digest)
    if type(name) is not str or not 2<=len(name.strip())<=120 or type(key) is not str or not 8<=len(key)<=128:
        fail(422,'INDEX_REQUEST_INVALID','Use a visible name and an 8–128 character intent key.')
    prepared,dimensions=prepare_entries(entries)
    fingerprint=digest(canonical({'name':name.strip(),'model':model,'model_digest':model_digest,'entries':prepared}))
    user,environment=current_actor(db,user)
    previous=db.scalar(select(NeuralIndex).where(NeuralIndex.org_id==user.org_id,NeuralIndex.env==environment,
        NeuralIndex.author_id==user.id,NeuralIndex.idem_key==key))
    if previous:
        if previous.request_digest!=fingerprint:fail(409,'IDEMPOTENCY_CONFLICT','This key belongs to another index build.')
        return metadata(previous)
    count=db.scalar(select(func.count()).select_from(NeuralIndex).where(NeuralIndex.org_id==user.org_id,NeuralIndex.env==environment))
    if count>=MAX_INDEXES:fail(429,'INDEX_CAPACITY','Remove obsolete index metadata before creating another snapshot.')
    sources,_,_=checked_sources(db,user,environment,prepared)
    row=NeuralIndex(org_id=user.org_id,env=environment,author_id=user.id,name=name.strip(),model=model,model_digest=model_digest,
        dimensions=dimensions,entry_count=len(prepared),sources=sources,content_hash=snapshot_hash(model,model_digest,sources,prepared),
        idem_key=key,request_digest=fingerprint)
    db.add(row);db.flush()
    for entry in prepared:
        db.add(NeuralVector(org_id=user.org_id,env=environment,index_id=row.id,document_id=entry['document_id'],
            document_version=entry['document_version'],position=entry['position'],chunk_hash=entry['sha256'],vector=entry['vector']))
    db.flush();audit(db,user.org_id,user.id,'retrieval.index.created',detail={'index_id':row.id,'entries':len(prepared),'dimensions':dimensions})
    return metadata(row)


def describe_index(db,user,id):
    user,environment=current_actor(db,user)
    return metadata(owned(db,id,user,environment))


def load_index(db,user,id,*,model,model_digest):
    """Validated private snapshot; never serialize this return value to clients."""
    model_identity(model,model_digest)
    user,environment=current_actor(db,user);row=owned(db,id,user,environment)
    if row.status=='building':fail(409,'INDEX_BUILD_ACTIVE','Wait for the background build to publish its snapshot.')
    if row.status!='ready':fail(409,'INDEX_INVALIDATED','The snapshot was invalidated; build a new index intent.')
    if row.model!=model or row.model_digest!=model_digest:fail(409,'INDEX_MODEL_CHANGED','The query model does not match this snapshot.')
    vectors=db.scalars(select(NeuralVector).where(NeuralVector.index_id==row.id,NeuralVector.org_id==user.org_id,NeuralVector.env==environment)
        .order_by(NeuralVector.document_id,NeuralVector.position).execution_options(populate_existing=True)).all()
    if not 1<=len(vectors)==row.entry_count<=MAX_ENTRIES:fail(409,'INDEX_INTEGRITY_FAILED','The stored snapshot is incomplete.')
    entries=[]
    for vector in vectors:
        try:values=vector_values(vector.vector,row.dimensions,normalize=False)
        except Exception:fail(409,'INDEX_INTEGRITY_FAILED','The stored snapshot cannot be verified.')
        entries.append({'document_id':vector.document_id,'document_version':vector.document_version,'position':vector.position,'sha256':vector.chunk_hash,'vector':values})
    sources,docs,chunks=checked_sources(db,user,environment,entries)
    if sources!=row.sources or snapshot_hash(row.model,row.model_digest,sources,entries)!=row.content_hash:
        fail(409,'INDEX_INTEGRITY_FAILED','The stored snapshot cannot be verified.')
    return row,entries,docs,chunks


def rank_index(db,user,id,query_vector,*,model,model_digest,top_k=5,min_score=0,one_per_document=False):
    """Internal query primitive. It neither embeds text nor persists queries."""
    if type(top_k) is not int or not 1<=top_k<=10 or type(one_per_document) is not bool or not finite_number(min_score) or not 0<=min_score<=1:
        fail(422,'INDEX_QUERY_INVALID','Use bounded ranking controls.')
    row,entries,docs,chunks=load_index(db,user,id,model=model,model_digest=model_digest)
    query=vector_values(query_vector,row.dimensions)
    hits=[]
    for entry in entries:
        score=max(0.0,min(1.0,math.fsum(a*b for a,b in zip(query,entry['vector']))))
        if score<=0 or score<min_score:continue
        doc=docs[entry['document_id']];chunk=chunks[(doc.id,entry['position'])]
        hits.append({'document_id':doc.id,'document_version':doc.version,'position':entry['position'],'score':round(score,6),
            'sha256':chunk.content_hash,'citation':f'{doc.id}:v{doc.version}:chunk{entry["position"]+1}','excerpt':chunk.text})
    hits.sort(key=lambda h:(-h['score'],h['document_id'],h['position']))
    if one_per_document:
        seen=set();unique=[]
        for hit in hits:
            if hit['document_id'] not in seen:seen.add(hit['document_id']);unique.append(hit)
        hits=unique
    return {'index':metadata(row),'items':hits[:top_k],'provider_calls':0,'query_vector_stored':False,
            'boundary':'Internal stored-vector ranking only. Caller must produce a model-bound query vector; no generated answers or quality acceptance.'}


def invalidate_source(db,org,environment,document_id):
    """Called in the same transaction as a document content/access/delete update."""
    if runtime_environment(db,org)!=environment:raise RuntimeError('Index invalidation scope mismatch.')
    ids=list(db.scalars(select(NeuralVector.index_id).where(NeuralVector.org_id==org,NeuralVector.env==environment,NeuralVector.document_id==document_id).distinct()))
    staged=db.scalars(select(NeuralIndex).where(NeuralIndex.org_id==org,NeuralIndex.env==environment,NeuralIndex.status=='building')).all()
    ids=list(set(ids)|{row.id for row in staged if any(s.get('id')==document_id for s in row.sources)})
    if not ids:return
    db.execute(delete(NeuralVector).where(NeuralVector.org_id==org,NeuralVector.env==environment,NeuralVector.index_id.in_(ids)))
    db.execute(update(NeuralIndex).where(NeuralIndex.org_id==org,NeuralIndex.env==environment,NeuralIndex.id.in_(ids)).values(status='invalidated',version=NeuralIndex.version+1))


def remove_index(db,user,id,*,expected_version,note):
    if type(expected_version) is not int or expected_version<1 or type(note) is not str or not 5<=len(note.strip())<=500:
        fail(422,'INDEX_REQUEST_INVALID','Use a reviewed version and removal note.')
    user,environment=current_actor(db,user);row=owned(db,id,user,environment)
    if row.status=='building':fail(409,'INDEX_BUILD_ACTIVE','Cancel the unfinished build before removing its snapshot.')
    if row.version!=expected_version:fail(409,'STALE_VERSION','The index changed; review it before removal.')
    db.execute(delete(NeuralVector).where(NeuralVector.index_id==row.id,NeuralVector.org_id==user.org_id,NeuralVector.env==environment))
    db.delete(row);audit(db,user.org_id,user.id,'retrieval.index.removed',detail={'index_id':id,'note':note.strip()})
    return {'id':id,'status':'removed','boundary':'Active vectors removed; backup and database-storage erasure remain separate retention responsibilities.'}
