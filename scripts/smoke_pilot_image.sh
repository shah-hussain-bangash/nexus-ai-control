#!/usr/bin/env bash
# Build and exercise the release image with disposable local data.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
run_id="$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
image="nexus-pilot-smoke:$run_id"
container="nexus-pilot-smoke-$run_id"
volume="nexus-pilot-smoke-$run_id"

cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    docker volume rm "$volume" >/dev/null 2>&1 || true
    docker image rm "$image" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build --tag "$image" .
docker volume create "$volume" >/dev/null
export NEXUS_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export NEXUS_AGENT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
runtime=(
    --env NEXUS_SECRET --env NEXUS_AGENT_SECRET
    --env NEXUS_MODE=local --env NEXUS_POLICY_MODE=reference
    --env NEXUS_BUSINESS_CONNECTOR=synthetic
    --volume "$volume:/app/backend/data"
)

# The one-shot initializer prints a disposable login password. Suppress stdout.
docker run --rm "${runtime[@]}" "$image" python -m nexus.cli init >/dev/null

docker run --detach --name "$container" "${runtime[@]}" \
    --publish 127.0.0.1::8000 --read-only --cap-drop ALL \
    --security-opt no-new-privileges --tmpfs /tmp:rw,noexec,nosuid,size=32m \
    "$image" >/dev/null

test "$(docker exec "$container" id -u)" = 10001
binding="$(docker port "$container" 8000/tcp)"
if ! [[ "$binding" =~ ^127\.0\.0\.1:[0-9]+$ ]]; then
    echo "Expected a single loopback-only port binding." >&2
    exit 1
fi

python3 - "http://$binding" <<'PY'
from html.parser import HTMLParser
from http.client import HTTPConnection
import json
import sys
import time
from urllib.parse import urlsplit


class AppShell(HTMLParser):
    script = None

    def handle_starttag(self, tag, attributes):
        attr = dict(attributes)
        source = attr.get("src") or ""
        if tag == "script" and attr.get("type") == "module" and source.startswith("/assets/"):
            self.script = source


def get(path):
    endpoint = urlsplit(sys.argv[1])
    client = HTTPConnection(endpoint.hostname, endpoint.port, timeout=3)
    try:
        client.request("GET", path)
        response = client.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        client.close()


deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    try:
        status, _, body = get("/health/ready")
        if status == 200:
            break
    except OSError:
        pass
    time.sleep(0.5)
else:
    raise SystemExit("Container did not become ready.")

ready = json.loads(body)
assert ready["status"] == "ready" and ready["mode"] == "local"
assert ready["policy_engine"] == "reference" and type(ready["schema_version"]) is int
assert ready["schema_version"] > 0
assert get("/v1/me")[0] == 401
assert get("/metrics")[0] == 404
status, content_type, body = get("/")
assert status == 200 and content_type.startswith("text/html")
shell = AppShell()
shell.feed(body.decode())
assert shell.script, "Built portal did not reference a module asset."
status, content_type, body = get(shell.script)
assert status == 200 and "javascript" in content_type and body
print("Container served the built portal and JavaScript with a ready synthetic database.")
PY

if [[ -n "${NEXUS_IMAGE_EVIDENCE_DIR:-}" ]]; then
    evidence="$NEXUS_IMAGE_EVIDENCE_DIR"
    mkdir "$evidence"
    "${NEXUS_SYFT:-syft}" "docker:$image" -o "json=$evidence/sbom.syft.json" \
        -o "spdx-json=$evidence/sbom.spdx.json"
    "${NEXUS_GRYPE:-grype}" "sbom:$evidence/sbom.syft.json" -o json > "$evidence/vulnerabilities.json"
    image_id="$(docker image inspect "$image" --format '{{.Id}}')"
    revision="$(git rev-parse HEAD)"
    python3 - "$evidence" "$image_id" "$revision" <<'PY'
from collections import Counter
import json
from pathlib import Path
import sys


destination = Path(sys.argv[1])
sbom = json.loads((destination / "sbom.syft.json").read_text())
packages = sbom["artifacts"]
assert any(package["name"].lower() == "fastapi" and package["type"] == "python"
           for package in packages), "Expected FastAPI in the image package inventory."
scan = json.loads((destination / "vulnerabilities.json").read_text())
counts = Counter(match["vulnerability"]["severity"] for match in scan["matches"])
receipt = {
    "source_revision": sys.argv[3],
    "local_image_id": sys.argv[2],
    "smoke_test": "passed",
    "scan_policy": "report-only",
    "packages": len(packages),
    "matches_by_severity": dict(sorted(counts.items())),
}
(destination / "build-evidence.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
PY
fi
