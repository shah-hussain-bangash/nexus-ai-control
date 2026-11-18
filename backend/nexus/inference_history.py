"""Tenant/query-bound keyset pages. Prompt bodies are never searched."""
import hashlib
import hmac
import time
import jwt
from sqlalchemy import select, func, or_, and_
from .db import InferenceCall, WorkspaceAsset, public
from .security import fail


def page(db,settings,org_id,q='',status='all',limit=10,cursor=''):
    q=q.strip()
    key=hmac.new(settings.secret.encode(),b'nexus-inference-pages-v1',hashlib.sha256).digest()
    conditions=[InferenceCall.org_id==org_id,InferenceCall.env=='staging']
    if status!='all':conditions.append(InferenceCall.status==status)
    if q:
        models=select(WorkspaceAsset.id).where(WorkspaceAsset.org_id==org_id,WorkspaceAsset.env=='staging',func.lower(WorkspaceAsset.name).contains(q.lower(),autoescape=True))
        conditions.append(or_(func.lower(InferenceCall.id).contains(q.lower(),autoescape=True),func.lower(InferenceCall.asset_id).contains(q.lower(),autoescape=True),InferenceCall.asset_id.in_(models)))
    if cursor:
        try:
            c=jwt.decode(cursor,key,algorithms=['HS256'],audience='nexus-inference-history',options={'require':['exp','aud','org','q','status','created','id']})
            if c['org']!=org_id or c['q']!=q or c['status']!=status:raise ValueError()
            stamp=float(c['created']);row_id=str(c['id'])
        except (jwt.PyJWTError,ValueError,TypeError,KeyError):
            fail(400,'INVALID_CURSOR','This page cursor expired or belongs to a different search. Start at the first page.')
        conditions.append(or_(InferenceCall.created<stamp,and_(InferenceCall.created==stamp,InferenceCall.id<row_id)))
    rows=db.scalars(select(InferenceCall).where(*conditions).order_by(InferenceCall.created.desc(),InferenceCall.id.desc()).limit(limit+1)).all()
    more=len(rows)>limit;rows=rows[:limit];next_cursor=None
    if more:
        last=rows[-1]
        next_cursor=jwt.encode({'aud':'nexus-inference-history','org':org_id,'q':q,'status':status,'created':last.created,'id':last.id,'exp':int(time.time())+900},key,algorithm='HS256')
    return {'items':[public(row) for row in rows],'has_more':more,'next_cursor':next_cursor,'limit':limit}
