"""Optional LangGraph adapter example. Install langgraph separately; not required for the local core.
No model-provider key is needed: this deterministic graph demonstrates the gateway boundary.
This optional dependency is not included in core verification results.
"""
import os
import uuid
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from nexus_client import NexusClient


class State(TypedDict):
    supplier_id: str
    request_key: str
    action_id: str
    status: str


def governed_lookup(state: State):
    client = NexusClient(os.environ.get('NEXUS_URL', 'http://localhost:8000'), os.environ['NEXUS_AGENT_ID'], os.environ['NEXUS_WORKLOAD_CREDENTIAL'])
    try:
        result = client.execute(os.environ['NEXUS_SUPPLIER_TOOL_ID'], 'supplier:read', 'suppliers',
                                {'supplier_id': state['supplier_id']}, state['request_key'])
        return {'action_id': result['id'], 'status': result['status']}
    finally: client.close()


graph = StateGraph(State); graph.add_node('lookup', governed_lookup); graph.add_edge(START, 'lookup'); graph.add_edge('lookup', END)
if __name__ == '__main__':
    print(graph.compile().invoke({'supplier_id': 'SUP-DEMO-104', 'request_key': str(uuid.uuid4())}))
