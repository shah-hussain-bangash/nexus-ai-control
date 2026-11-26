"""Read-only checks for an operator-selected NEXUS staging origin."""

import argparse
from datetime import datetime, timezone
import json
import os
import re
import ssl
from urllib.parse import urlsplit

import httpx


METRICS_SECRET = "NEXUS_STAGING_METRICS_TOKEN"
BOUNDARY = (
    "Point-in-time HTTPS and application checks. SSO configuration is visible, "
    "while MFA, secret custody, alert delivery and restore acceptance require separate evidence."
)


def https_origin(value):
    try:
        url = urlsplit(value)
        if (
            url.scheme == "https"
            and url.hostname
            and url.username is None
            and url.password is None
            and url.path in ("", "/")
            and not url.query
            and not url.fragment
            and (url.port is None or 1 <= url.port <= 65535)
            and not any(char.isspace() or ord(char) < 32 for char in value)
            and "\\" not in url.netloc
        ):
            return f"https://{url.netloc}"
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Provide one HTTPS origin without a path, credentials, query or fragment.")


def probe(client, origin, name, path, statuses, *, validate=None, headers=None):
    result = {"id": name, "passed": False}
    try:
        client.cookies.clear()
        response = client.get(origin + path, headers=headers)
        result["http_status"] = response.status_code
        result["passed"] = response.status_code in statuses and (
            validate is None or validate(response)
        )
    except (httpx.HTTPError, ValueError):
        result["failure"] = "unavailable_or_invalid_response"
    return result


def json_fields(response, expected):
    body = response.json()
    return isinstance(body, dict) and all(
        type(body.get(key)) is type(value) and body[key] == value
        for key, value in expected.items()
    )


def check_staging(client, origin, expected_schema, metrics_token=None):
    def ready(response):
        hsts = response.headers.get("strict-transport-security", "")
        has_positive_max_age = re.match(r"^\s*max-age\s*=\s*0*[1-9][0-9]*(?:\s*;|\s*$)", hsts, re.I)
        return bool(has_positive_max_age) and json_fields(
            response,
            {"status": "ready", "mode": "pilot", "policy_engine": "opa", "schema_version": expected_schema},
        )

    def metrics(response):
        return (
            response.headers.get("content-type", "").split(";", 1)[0].strip() == "text/plain"
            and f"nexus_schema_version {expected_schema}" in response.text.splitlines()
        )

    checks = [
        probe(client, origin, "liveness", "/health/live", {200},
              validate=lambda response: json_fields(response, {"status": "ok"})),
        probe(client, origin, "pilot_readiness_opa_schema_hsts", "/health/ready", {200}, validate=ready),
        probe(client, origin, "oidc_enabled_local_login_disabled", "/auth/config", {200},
              validate=lambda response: json_fields(response, {"mode": "pilot", "oidc": True, "local_login": False})),
        probe(client, origin, "anonymous_identity_denied", "/v1/me", {401}),
        probe(client, origin, "anonymous_metrics_denied_or_disabled", "/metrics",
              {403} if metrics_token else {403, 404}),
    ]
    if metrics_token:
        checks.append(probe(
            client, origin, "authenticated_metrics_scrape", "/metrics", {200}, validate=metrics,
            headers={"X-Nexus-Metrics-Token": metrics_token},
        ))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=BOUNDARY)
    parser.add_argument("origin", type=https_origin)
    parser.add_argument("--expected-schema", type=int, required=True)
    parser.add_argument("--ca-bundle", help="Optional trusted private CA PEM. TLS verification remains enabled.")
    parser.add_argument("--check-metrics", action="store_true", help=f"Read the scrape token from {METRICS_SECRET}.")
    args = parser.parse_args(argv)
    if args.expected_schema < 1:
        parser.error("--expected-schema must be positive.")
    token = os.environ.get(METRICS_SECRET, "") if args.check_metrics else ""
    if args.check_metrics and (len(token) < 32 or any(not 33 <= ord(char) <= 126 for char in token)):
        parser.error(f"Set a valid scrape token in {METRICS_SECRET}.")
    try:
        tls = ssl.create_default_context(cafile=args.ca_bundle)
    except OSError:
        parser.error("Could not load the configured CA trust.")
    with httpx.Client(verify=tls, timeout=5, follow_redirects=False, trust_env=False) as client:
        checks = check_staging(client, args.origin, args.expected_schema, token or None)
    receipt = {
        "format": "nexus-staging-preflight",
        "format_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_schema": args.expected_schema,
        "passed": all(check["passed"] for check in checks),
        "deployment_accepted": False,
        "checks": checks,
        "boundary": BOUNDARY,
    }
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
