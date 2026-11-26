"""Fixed supplier allowlist gate; no expressions, model calls or connector I/O."""
import re
from typing import Literal
from pydantic import Field, field_validator
from .schemas import Strict, ActionInput, SupplierArguments
from .security import digest
from .service import canonical, verify
from .check_evidence import require


class SupplierCondition(Strict):
    kind: Literal['supplier_allowlist']
    source_step: int = Field(strict=True,ge=0,le=11)
    supplier_ids: list[str] = Field(min_length=1,max_length=10)

    @field_validator('supplier_ids')
    @classmethod
    def bounded_ids(cls, values):
        if len(set(values))!=len(values) or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}',value) for value in values):
            raise ValueError('Choose one to ten unique supplier references.')
        return values


def condition_result(run, position, definition, source, action):
    condition=SupplierCondition.model_validate(definition['condition'])
    require(condition.source_step<position<len(run.definition['steps'])-1)
    prior=run.definition['steps'][condition.source_step]
    require(prior['kind']=='governed_action' and source is not None and action is not None)
    require(source.run_id==run.id and source.org_id==run.org_id and source.env==run.env)
    require(source.position==condition.source_step and source.kind=='governed_action' and source.status=='completed')
    require(source.action_id==action.id and action.org_id==run.org_id and action.env==run.env)
    require(action.agent_id==run.agent_id and action.generation==run.generation and action.status=='verified')
    require(action.requester_id==run.author_id and action.principal=='durable:'+run.author_id)
    require(action.idem_key=='run-'+run.id+'-'+str(condition.source_step) and action.tool_id==prior['tool_id'])
    body=ActionInput.model_validate(prior['request'])
    require(body.action=='supplier:read' and body.resource=='suppliers')
    arguments=SupplierArguments.model_validate(body.arguments).model_dump()
    envelope=action.envelope
    require(action.request_digest==digest(canonical({'agent':run.agent_id,'tool':action.tool_id,**body.model_dump()})))
    require(digest(canonical(envelope))==action.payload_hash)
    require(all(envelope[key]==value for key,value in {
        'org_id':run.org_id,'env':run.env,'agent_id':run.agent_id,'tool_id':action.tool_id,
        'action':body.action,'resource':body.resource,'arguments':arguments,'tool_version':body.tool_version,
        'schema_version':body.schema_version,'simulation':body.simulation,'policy_version':action.policy_version,
        'destination':run.definition.get('destination','mock-business-v1')}.items()))
    result=action.verification.get('result')
    require(action.verification.get('matched') is True and verify(envelope,result))
    require(action.external_ref==result['external_ref'])
    matched=result['supplier_id'] in condition.supplier_ids
    return {'kind':'supplier_allowlist','source_step':condition.source_step,'matched':matched,
            'next_step':position+1 if matched else len(run.definition['steps'])-1}
