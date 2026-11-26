"""Exercise the real HTTPS connector against a disposable loopback purchase sandbox."""

import json
import secrets
import socket
import ssl
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from conftest import approve, auth, submit
from nexus.business_connector import CONTRACT, HTTPBusiness
from nexus.db import Action
from nexus.mock_connector import MockBusiness, UncertainOutcome
from nexus.worker import run_once
from test_keycloak_integration import make_certificates


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    ca, certificate, private_key = make_certificates(tmp_path)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, private_key)
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("NEXUS_BUSINESS_API_KEY", token)
    tenant = "disposable-sandbox"
    ledger = MockBusiness(tmp_path / "sandbox-ledger.db")
    requests = []

    class PurchaseSandbox(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body=None):
            content = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def operation(self):
            required_headers = {
                "Authorization": f"Bearer {token}",
                "X-Nexus-Contract": CONTRACT,
                "X-Nexus-Organization": "northstar",
                "X-Nexus-Tenant": tenant,
            }
            if any(self.headers.get(name) != value for name, value in required_headers.items()):
                self.reply(403)
                return None
            intent = self.headers.get("Idempotency-Key")
            if not intent:
                self.reply(400)
                return None
            return intent

        def response_scope(self, intent):
            return {"operation_id": intent, "organization_id": "northstar", "tenant_id": tenant}

        def do_POST(self):
            requests.append((self.command, self.path))
            if self.path != "/api/v1/purchase-requests":
                self.reply(404)
                return
            intent = self.operation()
            if intent is None:
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            arguments = body.pop("arguments")
            if body != self.response_scope(intent):
                self.reply(403)
                return
            existing = ledger.lookup(intent)
            if existing is not None:
                if any(existing.get(key) != value for key, value in arguments.items()):
                    self.reply(409)
                else:
                    self.reply(200, {**self.response_scope(intent), "result": existing})
                return
            ledger.invoke(intent, {"action": "purchase:create", "arguments": arguments})
            # Close the real TLS connection before sending any HTTP response.
            # The isolated business ledger has already committed the effect.
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)

        def do_GET(self):
            requests.append((self.command, self.path))
            intent = self.operation()
            if intent is None:
                return
            if self.path != f"/api/v1/operations/{intent}":
                self.reply(404)
                return
            result = ledger.lookup(intent)
            if result is None:
                self.reply(404)
            else:
                self.reply(200, {**self.response_scope(intent), "result": result})

    with HTTPServer(("127.0.0.1", 0), PurchaseSandbox) as server:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        port = server.server_port
        original = socket.getaddrinfo

        def resolve(host, service, *args, **kwargs):
            # Keep the real adapter's configured HTTPS hostname and certificate
            # checks. Route only this test's default HTTPS destination locally.
            if host == "localhost" and service == 443:
                return original("127.0.0.1", port, *args, **kwargs)
            return original(host, service, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", resolve)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield ca, tenant, requests, ledger
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_governed_purchase_recovers_lost_https_response_without_duplicate(ctx, sandbox):
    ca, tenant, requests, ledger = sandbox
    settings = ctx["settings"]
    settings.business_connector = "http"
    settings.business_base_url = "https://localhost/api/v1"
    settings.business_host = "localhost"
    settings.business_tenant = tenant
    settings.business_ca_bundle = str(ca)
    connector = HTTPBusiness(settings)
    ctx["app"].state.connector = connector

    denied = submit(ctx, amount="25000.01", key="sandbox-denied-0001")
    assert denied.status_code == 202
    assert denied.json()["status"] == "denied"
    assert not run_once(ctx["db"], settings, connector)
    assert requests == []

    key = "sandbox-purchase-0001"
    submitted = submit(ctx, key=key)
    assert submitted.status_code == 202
    action = submitted.json()
    assert action["status"] == "awaiting_approval"
    assert not run_once(ctx["db"], settings, connector)
    assert approve(ctx, role="owner").status_code == 403
    assert approve(ctx, {"request_hash": "0" * 64}).status_code == 409
    assert requests == []
    assert approve(ctx).status_code == 200

    # An untrusted certificate must fail before reaching the HTTP handler.
    untrusted = HTTPBusiness(replace(settings, business_ca_bundle=""))
    with pytest.raises(UncertainOutcome):
        untrusted.lookup(action["id"], action["envelope"])
    assert requests == []

    assert run_once(ctx["db"], settings, connector)
    with ctx["db"]() as db:
        assert db.get(Action, action["id"]).status == "outcome_unknown"
    assert ledger.count() == 1
    assert requests == [("POST", "/api/v1/purchase-requests")]

    repeated = submit(ctx, key=key)
    assert repeated.status_code == 202
    assert repeated.json()["id"] == action["id"]
    assert submit(ctx, amount="13000.00", key=key).status_code == 409
    assert not run_once(ctx["db"], settings, connector)

    headers, _ = auth(ctx)
    response = ctx["client"].post(f'/v1/actions/{action["id"]}/reconcile', headers=headers)
    assert response.status_code == 200
    reconciled = response.json()
    assert reconciled["status"] == "verified"
    assert reconciled["verification"]["reconciled"] is True
    assert reconciled["verification"]["result"] == ledger.lookup(action["id"])
    assert requests == [
        ("POST", "/api/v1/purchase-requests"),
        ("GET", f'/api/v1/operations/{action["id"]}'),
    ]
    assert ledger.count() == 1
