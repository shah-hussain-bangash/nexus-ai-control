"""Minimal synchronous workload client. Credentials come from the environment, never prompts."""
import os
import uuid
import time
import httpx


class NexusClient:
    def __init__(self, base_url, agent_id, credential):
        self.agent_id, self.credential = agent_id, credential
        self.http = httpx.Client(base_url=base_url.rstrip('/'), timeout=15)
        self.token, self.expiry = '', 0

    def authenticate(self):
        r = self.http.post('/v1/workload/token/' + self.agent_id, headers={'Authorization': 'Bearer ' + self.credential})
        r.raise_for_status(); result = r.json(); self.token = result['access_token']; self.expiry = time.time() + result['expires_in'] - 20

    def execute(self, tool_id, action, resource, arguments, idempotency_key):
        """Persist/reuse idempotency_key at the caller for one logical business intent."""
        if time.time() >= self.expiry: self.authenticate()
        r = self.http.post('/v1/gateway/tools/' + tool_id + ':execute', headers={'Authorization': 'Bearer ' + self.token,
            'Idempotency-Key': idempotency_key}, json={'tool_version': '1.0', 'schema_version': '1',
            'action': action, 'resource': resource, 'arguments': arguments})
        # No automatic retry of side effects. Inspect 403/409 or network uncertainty explicitly.
        r.raise_for_status(); return r.json()

    def get_action(self, action_id):
        if time.time() >= self.expiry: self.authenticate()
        response = self.http.get('/v1/gateway/actions/' + action_id,
                                 headers={'Authorization': 'Bearer ' + self.token})
        response.raise_for_status(); return response.json()

    def close(self): self.http.close()


if __name__ == '__main__':
    client = NexusClient(os.environ.get('NEXUS_URL', 'http://localhost:8000'), os.environ['NEXUS_AGENT_ID'], os.environ['NEXUS_WORKLOAD_CREDENTIAL'])
    try:
        result = client.execute(os.environ['NEXUS_SUPPLIER_TOOL_ID'], 'supplier:read', 'suppliers',
                                {'supplier_id': 'SUP-DEMO-104'}, idempotency_key=str(uuid.uuid4()))
        print({'action_id': result['id'], 'status': result['status']})
    finally: client.close()
