"""Compare saved labelled measurements with private, scope-bound query equality."""
import hashlib,hmac,re
from .service import canonical
from .security import fail
from .retrieval_comparison import frame,delta,classify


def query_identity(secret,org,environment,author,query):
    return hmac.new(secret.encode('utf-8'),canonical([org,environment,author,query]).encode('utf-8'),hashlib.sha256).hexdigest()


def compare_reviews(baseline,candidate,left_run,right_run,left_receipt,right_receipt):
    if left_run.id==right_run.id:fail(409,'INDEX_COMPARE_SAME_SEARCH','Choose reviews of two distinct saved searches.')
    identities=[row.result.get('query_identity') for row in (left_run,right_run)]
    if any(type(value) is not str or not re.fullmatch(r'[a-f0-9]{64}',value) for value in identities):
        fail(409,'INDEX_COMPARE_QUERY_UNAVAILABLE','Older searches lack a private query identity. Run both searches again before comparing.')
    if left_run.author_id!=right_run.author_id or not hmac.compare_digest(*identities):
        fail(409,'INDEX_COMPARE_QUERY_DIFFERENT','Compare the same query under the same original actor and query-identity key.')
    def labels(detail):
        value={k:v for k,v in detail['labels'].items() if k not in ('note','search_id')}
        value['expected_document_ids']=sorted(value['expected_document_ids'])
        return value
    if labels(baseline)!=labels(candidate):fail(409,'INDEX_COMPARE_LABELS_DIFFERENT','Use matching expected sources, outcome, language and precision target.')
    if left_run.result.get('normalization_version')!=right_run.result.get('normalization_version'):
        fail(409,'INDEX_COMPARE_METHOD_DIFFERENT','Use searches with matching retrieval-method versions.')
    controls=('top_k','min_score','one_per_document')
    if any(baseline['parameters'].get(k)!=candidate['parameters'].get(k) for k in controls):
        fail(409,'INDEX_COMPARE_CONTROLS_DIFFERENT','Use matching result limit, threshold and document-diversity controls.')
    try:
        before=frame(baseline['measurements']);after=frame(candidate['measurements'])
        changes={k:delta(before[k],after[k]) for k in ('document_recall_at_k','document_precision_at_k','reciprocal_rank')}
        changes['passed']=int(after['passed'])-int(before['passed'])
        changes['unexpected_document_count']=after['unexpected_document_count']-before['unexpected_document_count']
        direction=classify([changes['passed'],changes['document_recall_at_k'],changes['document_precision_at_k'],
            changes['reciprocal_rank'],-changes['unexpected_document_count']])
    except (ValueError,TypeError,KeyError):fail(409,'INDEX_COMPARE_EVIDENCE_INVALID','Saved measurements cannot be compared safely.')
    def side(detail,metrics):return {'id':detail['id'],'search_id':detail['search_id'],'index_id':detail['index_id'],
        'created':detail['created'],'status':detail['status'],'stale':detail['stale'],'parameters':detail['parameters'],'metrics':metrics}
    return {'baseline':side(baseline,before),'candidate':side(candidate,after),'delta':changes,'change':direction,
        'query_verified_same':True,'corpus_changed':left_receipt.result['source_versions']!=right_receipt.result['source_versions'],
        'model_changed':any(baseline['parameters'].get(k)!=candidate['parameters'].get(k) for k in ('embedding_model','embedding_digest')),
        'index_changed':left_receipt.result['index']!=right_receipt.result['index'],
        'stale':baseline['stale'] or candidate['stale'],'provider_calls':0,
        'boundary':'Saved reviewer-labelled retrieval measurements only. Same-query and control checks do not establish representative quality, causal attribution, generated-answer quality or production acceptance.'}
