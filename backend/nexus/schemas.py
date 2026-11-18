from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Strict):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class AgentInput(Strict):
    name: str = Field(min_length=2, max_length=80)
    framework: str = Field(default='Python SDK', max_length=50)
    risk: Literal['low', 'medium', 'high'] = 'medium'


class Reason(Strict):
    reason: str = Field(min_length=5, max_length=500)


class GrantInput(Strict):
    tool_id: str
    scope: Literal['supplier:read', 'purchase:create']


class ActionInput(Strict):
    tool_version: Literal['1.0'] = '1.0'
    schema_version: Literal['1'] = '1'
    action: Literal['supplier:read', 'purchase:create']
    resource: Literal['suppliers', 'purchase_requests']
    arguments: dict
    # A fault mode is local synthetic tooling, not a business argument.
    simulation: Literal['normal', 'timeout_after_commit', 'fail_before_commit', 'mismatch'] = 'normal'


class PurchaseArguments(Strict):
    supplier_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')
    amount: str = Field(pattern=r'^[0-9]{1,8}\.[0-9]{2}$')
    currency: Literal['USD']
    purpose: str = Field(min_length=3, max_length=300)

    @field_validator('amount')
    @classmethod
    def positive(cls, value):
        if Decimal(value) <= 0: raise ValueError('Amount must be positive')
        return f'{Decimal(value):.2f}'


class SupplierArguments(Strict):
    supplier_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')


class ConsoleAction(Strict):
    agent_id: str
    tool_id: str
    request: ActionInput


class ApprovalDecision(Strict):
    decision: Literal['approve', 'reject', 'request_changes']
    expected_version: int = Field(ge=1)
    request_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    comment: str = Field(min_length=5, max_length=500)


class PolicyInput(Strict):
    expected_version: int = Field(ge=1)
    threshold: str = Field(pattern=r'^[0-9]{1,8}\.[0-9]{2}$')
    maximum: str = Field(pattern=r'^[0-9]{1,8}\.[0-9]{2}$')
    reason: str = Field(min_length=5, max_length=500)
