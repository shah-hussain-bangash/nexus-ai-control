"""Offline Ed25519 audit-metadata verification; no app settings, database or network."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

FORMAT='nexus-audit-metadata-v1'
DOMAIN=b'NEXUS-AUDIT-METADATA-V1\x00'
MAX_BYTES=1048576
BOUNDARY='A successful signature check authenticates this bounded audit-metadata snapshot against a separately trusted public key. It does not establish database completeness, pre-export immutability, independent timestamping, current state, retention or production readiness.'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def key_id(key):
    return hashlib.sha256(key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).hexdigest()


def require(condition):
    if not condition:raise ValueError('Invalid signed audit metadata or trusted-key/scope mismatch.')


def unique(pairs):
    result={}
    for name,value in pairs:
        require(name not in result);result[name]=value
    return result


def text(value,maximum=256,nullable=False):
    if value is None and nullable:return
    require(type(value) is str and 0<len(value)<=maximum and not any(ord(c)<32 or ord(c)==127 for c in value))


def timestamp(value):
    require(type(value) is int and 0<=value<=9007199254740991)


def verify(raw,public_pem,workspace,environment):
    require(type(raw) is bytes and 0<len(raw)<=MAX_BYTES)
    require(type(public_pem) is bytes and len(public_pem)<=4096)
    try:envelope=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda _:require(False))
    except (UnicodeError,json.JSONDecodeError,RecursionError):raise ValueError('Invalid signed audit JSON.') from None
    require(type(envelope) is dict and set(envelope)=={'format','algorithm','key_id','payload','signature'})
    require(envelope['format']==FORMAT and envelope['algorithm']=='Ed25519')
    try:key=serialization.load_pem_public_key(public_pem)
    except (ValueError,TypeError,UnsupportedAlgorithm):raise ValueError('Unsupported trusted public key.') from None
    require(isinstance(key,Ed25519PublicKey) and envelope['key_id']==key_id(key))
    payload=envelope['payload']
    require(type(payload) is dict and set(payload)=={'id','workspace_id','environment','created_at_us','selection','limit','truncated','records','note'})
    text(payload['id'],64);text(payload['workspace_id']);text(payload['environment'],32);text(payload['note'],500)
    require(payload['workspace_id']==workspace and payload['environment']==environment)
    timestamp(payload['created_at_us']);require(payload['selection']=='latest_audit_metadata')
    require(type(payload['limit']) is int and 1<=payload['limit']<=1000 and type(payload['truncated']) is bool)
    records=payload['records'];require(type(records) is list and len(records)<=payload['limit'])
    require(not payload['truncated'] or len(records)==payload['limit'])
    seen=set();order=[]
    for row in records:
        require(type(row) is dict and set(row)=={'id','event','actor','action_id','trace_id','created_at_us'})
        for name in ('id','event','actor'):text(row[name])
        for name in ('action_id','trace_id'):text(row[name],nullable=True)
        timestamp(row['created_at_us']);require(row['created_at_us']<=payload['created_at_us'])
        require(row['id'] not in seen);seen.add(row['id']);order.append((row['created_at_us'],row['id']))
    require(order==sorted(order))
    signature=envelope['signature'];require(type(signature) is str and len(signature)==88)
    try:
        decoded=base64.b64decode(signature,validate=True);require(len(decoded)==64)
        key.verify(decoded,DOMAIN+canonical(payload))
    except (InvalidSignature,ValueError):raise ValueError('Audit signature verification failed.') from None
    return {'authenticated_signature':True,'key_id':envelope['key_id'],'records':len(records),'truncated':payload['truncated'],
        'workspace_id':workspace,'environment':environment,'snapshot_id':payload['id'],'boundary':BOUNDARY}


def read_file(path,maximum):
    path=Path(path)
    require(path.is_file() and not path.is_symlink())
    with path.open('rb') as stream:value=stream.read(maximum+1)
    require(len(value)<=maximum);return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',required=True);parser.add_argument('--public-key',required=True)
    parser.add_argument('--workspace',required=True);parser.add_argument('--environment',required=True)
    args=parser.parse_args()
    try:result=verify(read_file(args.evidence,MAX_BYTES),read_file(args.public_key,4096),args.workspace,args.environment)
    except (OSError,ValueError,TypeError,OverflowError,RecursionError):
        print(json.dumps({'authenticated_signature':False,'message':'Invalid file, signature, trusted key or expected scope.'}));return 1
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
