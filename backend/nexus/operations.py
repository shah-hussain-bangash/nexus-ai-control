"""Bounded housekeeping and tenant-bound audit pagination. Never deletes audit evidence."""
import hashlib
import hmac
import time
import jwt
from sqlalchemy import select, delete, func, or_, and_, cast, String
from .db import SessionRecord, OIDCTransaction, Export, Audit, public
from .security import fail


def housekeeping(factory, *, apply=False, cutoff=None):
    timestamp = time.time() if cutoff is None else cutoff
    targets = [("sessions", SessionRecord, timestamp),
               ("oidc_transactions", OIDCTransaction, timestamp - 3600),
               ("exports", Export, timestamp)]
    with factory.begin() as db:
        counts = {}
        for name, model, boundary in targets:
            condition = model.expires <= boundary
            if apply:
                counts[name] = db.execute(delete(model).where(condition)).rowcount
            else:
                counts[name] = db.scalar(select(func.count()).select_from(model).where(condition))
    return {"applied": apply, "cutoff": timestamp, "expired_records": counts,
            "audit_evidence_deleted": False, "oidc_grace_seconds": 3600}


def audit_page(db, settings, org_id, q="", limit=50, cursor=""):
    q = q.strip()
    key = hmac.new(settings.secret.encode(), b"nexus-audit-cursor-v1", hashlib.sha256).digest()
    conditions = [Audit.org_id == org_id]
    if q:
        term = q.lower()
        conditions.append(or_(*[func.lower(cast(col, String)).contains(term, autoescape=True)
            for col in [Audit.id, Audit.event, Audit.actor, Audit.action_id, Audit.trace_id, Audit.detail]]))
    if cursor:
        try:
            data = jwt.decode(cursor, key, algorithms=["HS256"], audience="nexus-audit-page",
                              options={"require": ["exp", "aud", "org", "q", "created", "id"]})
            if data["org"] != org_id or data["q"] != q: raise ValueError("Cursor scope mismatch")
            created = float(data["created"]); row_id = str(data["id"])
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            fail(400, "INVALID_CURSOR", "The page cursor expired or does not match this search. Start a new search.")
        conditions.append(or_(Audit.created < created, and_(Audit.created == created, Audit.id < row_id)))
    rows = db.scalars(select(Audit).where(*conditions).order_by(Audit.created.desc(), Audit.id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if more:
        last = rows[-1]
        next_cursor = jwt.encode({"aud": "nexus-audit-page", "org": org_id, "q": q,
            "created": last.created, "id": last.id, "exp": int(time.time()) + 900}, key, algorithm="HS256")
    return {"items": [public(row) for row in rows], "next_cursor": next_cursor, "has_more": more}
