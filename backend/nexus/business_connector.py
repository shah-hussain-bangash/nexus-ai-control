"""Operator-configured NEXUS Business v1 adapter. Never accepts request-supplied URLs.

No automatic HTTP retries. Ambiguous responses preserve outcome_unknown for
reconciliation. Customer deployments must enforce their own egress policy and
implement the documented idempotency/organization-isolation contract.
"""
import hashlib
import json
import os
import re
import ssl
from urllib.parse import urlsplit,quote
from pathlib import Path
import httpx
from .mock_connector import MockBusiness, UncertainOutcome

CONTRACT='nexus-business-v1'


def validate_business(settings, require_secret=True):
    if settings.business_connector not in ('synthetic','http'):raise RuntimeError('Unsupported business connector mode.')
    if not 1<=settings.business_timeout_seconds<=30 or not 4096<=settings.business_response_bytes<=1048576:raise RuntimeError('Invalid business connector bounds.')
    if settings.business_connector=='synthetic':return
    try:
        parsed=urlsplit(settings.business_base_url);host=(parsed.hostname or '').lower()
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None,443):raise ValueError()
        if not host or host!=settings.business_host.lower() or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host) or '..' in host:raise ValueError()
        if not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*/?',parsed.path):raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,63}',settings.business_tenant):raise ValueError()
        if not re.fullmatch(r'NEXUS_[A-Z0-9_]{3,80}',settings.business_token_env):raise ValueError()
    except (ValueError,TypeError):raise RuntimeError('Business HTTP requires an exact configured HTTPS host, safe base path, remote tenant and a named server secret.') from None
    if settings.business_ca_bundle and not Path(settings.business_ca_bundle).is_file():raise RuntimeError('Business connector CA bundle is missing.')
    if require_secret:
        token=os.environ.get(settings.business_token_env,'')
        if not 16<=len(token)<=4096 or any(ord(c)<33 or ord(c)>126 for c in token):raise RuntimeError('Provision a valid business API credential in the named server environment variable.')


def connector_identity(settings):
    if settings.business_connector=='synthetic':return 'mock-business-v1'
    validate_business(settings,False)
    binding='|'.join((CONTRACT,settings.business_base_url.rstrip('/'),settings.business_tenant))
    return 'http-business-v1:'+hashlib.sha256(binding.encode()).hexdigest()


def connector_profile(settings):
    return {'mode':settings.business_connector,'destination':connector_identity(settings),'contract':CONTRACT,'configured_host':settings.business_host if settings.business_connector=='http' else '',
            'external_effects_enabled':settings.business_connector=='http','automatic_retries':False,'tls_verification':True,
            'boundary':'HTTP requires the documented customer adapter contract and deployment egress/isolation acceptance.' if settings.business_connector=='http' else 'Local synthetic business connector; no customer system is contacted.'}


class HTTPBusiness:
    def __init__(self,settings,*,transport=None):
        validate_business(settings);self.settings=settings;self.transport=transport

    def binding(self,envelope):
        if not envelope or envelope.get('destination')!=connector_identity(self.settings):raise ValueError('Reviewed connector destination changed.')
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}',envelope.get('org_id','')):raise ValueError('Invalid scoped organization.')

    def request(self,method,path,envelope,intent,body=None):
        self.binding(envelope);validate_business(self.settings)
        headers={'Authorization':'Bearer '+os.environ[self.settings.business_token_env],
                 'X-Nexus-Tenant':self.settings.business_tenant,'X-Nexus-Organization':envelope['org_id'],
                 'X-Nexus-Contract':CONTRACT,'Accept':'application/json','Idempotency-Key':intent}
        verify=ssl.create_default_context(cafile=self.settings.business_ca_bundle or None)
        try:
            with httpx.Client(transport=self.transport,verify=verify,timeout=httpx.Timeout(self.settings.business_timeout_seconds),follow_redirects=False,trust_env=False) as client:
                with client.stream(method,self.settings.business_base_url.rstrip('/')+path,headers=headers,json=body) as response:
                    raw=bytearray()
                    for part in response.iter_bytes():
                        if len(raw)+len(part)>self.settings.business_response_bytes:raise UncertainOutcome('Business response exceeded its bound.')
                        raw.extend(part)
                    if method=='GET' and path.startswith('/operations/') and response.status_code==404:return None
                    if response.status_code not in (200,201):raise UncertainOutcome('Business operation needs authoritative reconciliation.')
                    if response.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':raise UncertainOutcome('Business response is not authoritative JSON.')
                    def reject(value):raise ValueError('Non-finite value')
                    result=json.loads(raw,parse_constant=reject)
                    if not isinstance(result,dict):raise ValueError('Object required')
                    # Bind every authoritative result to the immutable local operation and remote/local tenant.
                    if result.get('operation_id')!=intent or result.get('organization_id')!=envelope['org_id'] or result.get('tenant_id')!=self.settings.business_tenant:raise UncertainOutcome('Business result scope did not match.')
                    payload=result.get('result')
                    if not isinstance(payload,dict) or not isinstance(payload.get('external_ref'),str) or not 1<=len(payload['external_ref'])<=200:raise UncertainOutcome('Business result requires investigation.')
                    for key in ('external_ref','state','supplier_id','amount','currency','purpose'):
                        if key in payload and (not isinstance(payload[key],str) or len(payload[key])>500):raise UncertainOutcome('Business result shape did not match the contract.')
                    # Never retain arbitrary upstream fields, credentials, diagnostics or personal records.
                    return {k:payload[k] for k in ('external_ref','state','supplier_id','amount','currency','purpose') if k in payload}
        except UncertainOutcome:raise
        except (httpx.HTTPError,ValueError,RecursionError,UnicodeError):raise UncertainOutcome('Business response was uncertain; do not replay automatically.') from None

    def invoke(self,intent,envelope,simulation='normal'):
        self.binding(envelope)
        if simulation!='normal':raise ValueError('Synthetic fault injection is disabled for HTTP business adapters.')
        args=envelope['arguments'];supplier=args.get('supplier_id','')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}',supplier):raise ValueError('Invalid supplier reference.')
        if envelope['action']=='supplier:read':return self.verified_result(self.request('GET','/suppliers/'+quote(supplier,safe=''),envelope,intent),envelope)
        if envelope['action']=='purchase:create':return self.verified_result(self.request('POST','/purchase-requests',envelope,intent,{'operation_id':intent,'organization_id':envelope['org_id'],'tenant_id':self.settings.business_tenant,'arguments':args}),envelope)
        raise ValueError('Unsupported governed business action.')

    @staticmethod
    def verified_result(result,envelope):
        expected='created' if envelope['action']=='purchase:create' else 'found'
        if not result or result.get('state')!=expected or any(result.get(key)!=value for key,value in envelope['arguments'].items()):raise UncertainOutcome('Business result did not verify the immutable requested effect; authoritative investigation is required.')
        return result

    def lookup(self,intent,envelope=None):
        if not re.fullmatch(r'[A-Za-z0-9-]{1,64}',intent):raise ValueError('Invalid operation reference.')
        return self.request('GET','/operations/'+quote(intent,safe=''),envelope,intent)


def business_connector(settings):
    return HTTPBusiness(settings) if settings.business_connector=='http' else MockBusiness(settings.mock_database)
