import argparse
import importlib.util
import json
import ssl
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest

from test_keycloak_integration import make_certificates


script = Path(__file__).resolve().parents[2] / "scripts" / "check_staging.py"
spec = importlib.util.spec_from_file_location("check_staging", script)
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


ORIGIN = "https://staging.example.test"
READY = {
    "status": "ready",
    "mode": "pilot",
    "policy_engine": "opa",
    "schema_version": 11,
}
AUTH = {"mode": "pilot", "oidc": True, "local_login": False}
HSTS = {"Strict-Transport-Security": "max-age=31536000"}


def run_checks(overrides=None, token=None):
    routes = {
        "/health/live": httpx.Response(200, json={"status": "ok"}, headers={"Set-Cookie": "test=ignore; Path=/"}),
        "/health/ready": httpx.Response(200, json=READY, headers=HSTS),
        "/auth/config": httpx.Response(200, json=AUTH),
        "/v1/me": httpx.Response(401),
        "/metrics": httpx.Response(403 if token else 404),
    }
    routes.update(overrides or {})
    seen = []

    def response(request):
        assert request.url.path in routes
        assert request.url.host == "staging.example.test"
        assert request.method == "GET"
        assert "cookie" not in request.headers
        seen.append(request)
        if request.url.path == "/metrics" and "X-Nexus-Metrics-Token" in request.headers:
            assert request.headers["X-Nexus-Metrics-Token"] == token
            return httpx.Response(200, text="nexus_schema_version 11\n")
        assert "X-Nexus-Metrics-Token" not in request.headers
        return routes[request.url.path]

    with httpx.Client(transport=httpx.MockTransport(response), follow_redirects=False) as client:
        checks = staging.check_staging(client, ORIGIN, 11, token)
    return {check["id"]: check for check in checks}, seen


@pytest.mark.parametrize("value", [
    "http://host",
    "https://example.test/private",
    "https://user:password@example.test",
    "https://example.test/#internal",
    "https://example.test/?token=private",
    "https://example.test:99999",
    "https:///missing-host",
    "https://ex ample.test",
])
def test_staging_origin_rejects_insecure_or_non_origin_urls(value):
    with pytest.raises(argparse.ArgumentTypeError):
        staging.https_origin(value)


def test_origin_normalizes_optional_trailing_slash():
    assert staging.https_origin(ORIGIN + "/") == ORIGIN


def test_staging_and_optional_metrics_checks_pass():
    without_metrics, _ = run_checks()
    assert len(without_metrics) == 5 and all(item["passed"] for item in without_metrics.values())
    token = "x" * 48
    with_metrics, seen = run_checks(token=token)
    assert len(with_metrics) == 6 and all(item["passed"] for item in with_metrics.values())
    assert len(seen) == 6
    assert token not in str(with_metrics)


@pytest.mark.parametrize(("path", "status", "data", "headers", "check"), [
    ("/health/live", 302, None, {"Location": "https://other.example.test/"}, "liveness"),
    ("/health/ready", 503, None, HSTS, "pilot_readiness_opa_schema_hsts"),
    ("/health/ready", 200, READY, {}, "pilot_readiness_opa_schema_hsts"),
    ("/health/ready", 200, READY, {"Strict-Transport-Security": "max-age=0"}, "pilot_readiness_opa_schema_hsts"),
    ("/health/ready", 200, {**READY, "schema_version": 10}, HSTS, "pilot_readiness_opa_schema_hsts"),
    ("/health/ready", 200, {**READY, "policy_engine": "reference"}, HSTS, "pilot_readiness_opa_schema_hsts"),
    ("/auth/config", 200, {**AUTH, "local_login": True}, {}, "oidc_enabled_local_login_disabled"),
    ("/v1/me", 200, {"private": "must not enter receipt"}, {}, "anonymous_identity_denied"),
    ("/metrics", 200, None, {}, "anonymous_metrics_denied_or_disabled"),
])
def test_staging_reports_misconfiguration_without_recording_response_body(path, status, data, headers, check):
    results, seen = run_checks({path: httpx.Response(status, json=data, headers=headers)})
    assert len(seen) == 5
    assert results[check] == {"id": check, "passed": False, "http_status": status}
    assert "must not enter receipt" not in str(results)


def test_invalid_json_cannot_pass_readiness():
    results, _ = run_checks({"/health/ready": httpx.Response(200, text="invalid JSON", headers=HSTS)})
    assert results["pilot_readiness_opa_schema_hsts"]["failure"] == "unavailable_or_invalid_response"


def test_cli_requires_trusted_tls_and_writes_a_secret_free_receipt(tmp_path, capsys):
    ca, certificate, key = make_certificates(tmp_path)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    routes = {
        "/health/live": (200, {"status": "ok"}),
        "/health/ready": (200, READY),
        "/auth/config": (200, AUTH),
        "/v1/me": (401, {}),
        "/metrics": (404, {}),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            status, body = routes[self.path]
            self.send_response(status)
            self.send_header("Strict-Transport-Security", HSTS["Strict-Transport-Security"])
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"https://127.0.0.1:{server.server_port}"
            args = [origin, "--expected-schema", "11"]
            assert staging.main(args) == 1
            failed = json.loads(capsys.readouterr().out)
            assert all(not check["passed"] and "http_status" not in check for check in failed["checks"])
            assert staging.main([*args, "--ca-bundle", str(ca)]) == 0
            output = capsys.readouterr().out
            receipt = json.loads(output)
            assert receipt["passed"] and not receipt["deployment_accepted"]
            assert origin not in output and str(ca) not in output
        finally:
            server.shutdown()
            thread.join(timeout=5)
