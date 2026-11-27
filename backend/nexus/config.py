"""Environment configuration with optional operator-mounted secret files."""
import os
from dataclasses import dataclass,field
from pathlib import Path


def load_env(path: str = '.env') -> None:
    if Path(path).is_file():
        for line in Path(path).read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Settings:
    database_url: str = 'sqlite:///./data/nexus.db'
    mock_database: str = './data/mock_business.db'
    secret: str = ''
    agent_secret: str = ''
    mode: str = 'local'
    policy_mode: str = 'reference'
    opa_url: str = 'http://127.0.0.1:8181/v1/data/nexus/decision'
    origin: str = 'http://localhost:8000'
    oidc_issuer: str = ''
    oidc_client_id: str = 'nexus-console'
    oidc_client_secret: str = ''
    oidc_required_acr: str = ''
    oidc_ca_bundle: str = ''
    frontend_dir: str = '../frontend/dist'
    session_seconds: int = 28800
    inference_requests_per_minute: int = 30
    inference_max_inflight: int = 4
    live_inference: int = 0
    ollama_enabled: int = 0
    ollama_models: str = ''
    ollama_embedding_enabled: int = 0
    ollama_embedding_model: str = ''
    ollama_embedding_digest: str = ''
    ollama_rerank_enabled: int = 0
    ollama_rerank_model: str = ''
    ollama_rerank_digest: str = ''
    provider_hosts: str = ''
    provider_prices: str = '{}'
    monthly_budget_usd: str = '0'
    inference_max_output: int = 4096
    inference_response_bytes: int = 1048576
    business_connector: str = 'synthetic'
    business_base_url: str = ''
    business_host: str = ''
    business_tenant: str = ''
    business_token_env: str = 'NEXUS_BUSINESS_API_KEY'
    business_ca_bundle: str = ''
    business_timeout_seconds: int = 10
    business_response_bytes: int = 262144
    ingestion_in_action_worker: int = 1
    ingestion_ocr_enabled: int = 0
    tesseract_command: str = 'tesseract'
    ingestion_ocr_languages: str = 'eng'
    ingestion_timeout_seconds: int = 30
    audit_signing_key_file: str = ''
    metrics_token: str = ''  
    _secret_input_sources: dict = field(default_factory=dict,init=False,repr=False)

    @classmethod
    def from_env(cls):
        load_env()
        from .secret_inputs import STARTUP_SECRETS,read_secret,source
        keys = {key for key,value in cls.__dataclass_fields__.items() if value.init}
        values = {}
        for k in keys:
            if k in STARTUP_SECRETS:
                values[k]=read_secret('NEXUS_'+k.upper())
                continue
            v = os.getenv('NEXUS_' + k.upper())
            if v is not None:
                values[k] = int(v) if k in ('session_seconds', 'live_inference', 'ollama_enabled', 'ollama_embedding_enabled', 'ollama_rerank_enabled', 'inference_max_output', 'inference_response_bytes', 'inference_requests_per_minute', 'inference_max_inflight', 'business_timeout_seconds', 'business_response_bytes', 'ingestion_ocr_enabled', 'ingestion_timeout_seconds', 'ingestion_in_action_worker') else v
        settings=cls(**values)
        settings._secret_input_sources={key:source('NEXUS_'+key.upper()) for key in STARTUP_SECRETS}
        return settings

    def validate(self):
        import re
        if self.ingestion_in_action_worker not in (0,1) or self.ingestion_ocr_enabled not in (0,1) or not 5<=self.ingestion_timeout_seconds<=60:raise RuntimeError('Invalid document extraction bounds.')
        if not re.fullmatch(r'(eng|ara)(\+(eng|ara))?',self.ingestion_ocr_languages):raise RuntimeError('OCR languages must be eng, ara or eng+ara.')
        if not self.tesseract_command or len(self.tesseract_command)>500 or any(ord(c)<32 for c in self.tesseract_command):raise RuntimeError('Invalid operator Tesseract command.')
        from .business_connector import validate_business
        validate_business(self)
        if self.metrics_token and len(self.metrics_token)<32:raise RuntimeError('Metrics token must contain at least 32 characters.')
        if len(self.secret) < 32 or len(self.agent_secret) < 32 or self.secret == self.agent_secret:
            raise RuntimeError('Generate distinct runtime secrets first: python -m nexus.cli init')
        if self.oidc_ca_bundle and not Path(self.oidc_ca_bundle).is_file():
            raise RuntimeError('Configured OIDC CA bundle does not exist.')
        if self.mode not in ('local', 'pilot') or self.policy_mode not in ('reference', 'opa'):
            raise RuntimeError('Unsupported mode or policy engine')
        if not 1 <= self.inference_requests_per_minute <= 10000 or not 1 <= self.inference_max_inflight <= 100:
            raise RuntimeError('Invalid inference request/concurrency limits.')
        if self.live_inference not in (0, 1) or not 1 <= self.inference_max_output <= 32768 or not 4096 <= self.inference_response_bytes <= 4194304:
            raise RuntimeError('Invalid inference runtime limits.')
        from .ollama import valid_model_tag
        embedding_pair = bool(self.ollama_embedding_model or self.ollama_embedding_digest)
        if (self.ollama_embedding_enabled not in (0, 1) or
                embedding_pair and (not valid_model_tag(self.ollama_embedding_model) or type(self.ollama_embedding_digest) is not str or not re.fullmatch(r'[a-f0-9]{64}',self.ollama_embedding_digest)) or
                self.ollama_embedding_enabled and (self.mode != 'local' or not embedding_pair)):
            raise RuntimeError('Local neural search requires local mode, an explicit embedding model:tag and its 64-character digest.')
        rerank_pair=bool(self.ollama_rerank_model or self.ollama_rerank_digest)
        if (self.ollama_rerank_enabled not in (0,1) or
            rerank_pair and (not valid_model_tag(self.ollama_rerank_model) or type(self.ollama_rerank_digest) is not str or not re.fullmatch(r'[a-f0-9]{64}',self.ollama_rerank_digest)) or
            self.ollama_rerank_enabled and (self.mode!='local' or not rerank_pair)):
            raise RuntimeError('Local reranking requires local mode, an explicit model:tag and its 64-character digest.')
        if self.ollama_enabled not in (0, 1):
            raise RuntimeError('OLLAMA_ENABLED must be 0 or 1.')
        local_models = [item.strip() for item in self.ollama_models.split(',') if item.strip()]
        if (len(local_models) > 100 or len(local_models) != len(set(local_models)) or
                any(not valid_model_tag(item) for item in local_models)):
            raise RuntimeError('OLLAMA_MODELS requires at most 100 distinct explicit local model:tag values.')
        if self.ollama_enabled and (self.mode != 'local' or not local_models):
            raise RuntimeError('Ollama opt-in requires local mode and an explicit installed-model allowlist.')
        from decimal import Decimal, InvalidOperation
        import json
        try:
            amount = Decimal(self.monthly_budget_usd)
            prices = json.loads(self.provider_prices)
            if not amount.is_finite() or amount < 0 or amount > 1000000 or not isinstance(prices, dict): raise ValueError()
            for rates in prices.values():
                if set(rates) != {'input', 'output'}: raise ValueError()
                for value in rates.values():
                    rate = Decimal(str(value))
                    if not rate.is_finite() or rate <= 0 or rate > 100000: raise ValueError()
        except (ValueError, TypeError, InvalidOperation):
            raise RuntimeError('Provider rates and monthly budget must be finite nonnegative operator configuration; rates must be positive.')
        if self.live_inference and (amount <= 0 or not prices or not self.provider_hosts.strip()):
            raise RuntimeError('Live inference requires an explicit host allowlist, operator rates and a positive monthly budget.')
        if self.mode == 'pilot':
            from sqlalchemy.engine import make_url
            if make_url(self.database_url).query.get('sslmode') != 'verify-full':
                raise RuntimeError('Pilot PostgreSQL requires sslmode=verify-full and a trusted CA.')
            if not self.oidc_required_acr:
                raise RuntimeError('Pilot mode requires an explicit, IdP-verified MFA authentication context (OIDC_REQUIRED_ACR).')
            if not self.origin.startswith('https://') or not self.oidc_issuer.startswith('https://'):
                raise RuntimeError('Pilot mode requires HTTPS origin and OIDC issuer')
            if self.policy_mode != 'opa' or self.database_url.startswith('sqlite'):
                raise RuntimeError('Pilot mode requires OPA and PostgreSQL; customer readiness review still required')
