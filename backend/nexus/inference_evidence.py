"""Document-library evidence selection and current-access checks on answer reads."""
import hashlib
from sqlalchemy import select
from .db import KnowledgeDocument, DocumentChunk, public
from .documents import search_documents, can_read
from .runtime_context import runtime_environment


def retrieve_evidence(db, user, query):
    hits = search_documents(db, user, query, 5)
    return [{**hit, 'source_kind': 'document_library', 'text': hit['excerpt']} for hit in hits]


def sources_current(db, citations, user):
    if type(citations) is not list:
        return False
    documents = [hit for hit in citations if type(hit) is dict and hit.get('source_kind') == 'document_library']
    if not documents:
        return True
    if user is None:
        return False
    environment = runtime_environment(db, user.org_id)
    for hit in documents:
        if (type(hit.get('document_id')) is not str or
                type(hit.get('document_version')) is not int or hit['document_version'] < 1 or
                type(hit.get('chunk')) is not int or hit['chunk'] < 1 or
                type(hit.get('text')) is not str or type(hit.get('sha256')) is not str):
            return False
        doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == hit['document_id'],
            KnowledgeDocument.org_id == user.org_id, KnowledgeDocument.env == environment))
        if not doc or not can_read(doc, user, environment) or doc.version != hit['document_version']:
            return False
        chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.org_id == user.org_id,
            DocumentChunk.env == environment, DocumentChunk.document_id == doc.id,
            DocumentChunk.document_version == doc.version, DocumentChunk.position == hit['chunk']-1,
            DocumentChunk.content_hash == hit['sha256']))
        if (not chunk or chunk.text != hit['text'] or hit.get('excerpt') != hit['text'] or
                hashlib.sha256(hit['text'].encode()).hexdigest() != hit['sha256']):
            return False
    return True


def visible_call(db, row, user=None):
    result = public(row)
    saved = result.get('result')
    if type(saved) is not dict:
        return result
    citations = saved.get('citations', [])
    library = saved.get('evidence_source') == 'document_library' or (
        type(citations) is list and any(type(hit) is dict and hit.get('source_kind') == 'document_library'
                                       for hit in citations))
    if not library:
        return result
    valid_shape = (type(citations) is list and bool(citations) and
                   all(type(hit) is dict and hit.get('source_kind') == 'document_library' for hit in citations))
    if (not valid_shape or user is None or row.org_id != user.org_id or
            row.env != runtime_environment(db, user.org_id) or not sources_current(db, citations, user)):
        # Redacting only citations still leaks facts learned from a revoked source.
        result = {**result, 'result': {
            'message': 'Answer and source excerpts withheld: source access or version changed. '
                       'Run a new request using currently authorized evidence.',
            'citations': [], 'withheld': True,
        }}
    return result
