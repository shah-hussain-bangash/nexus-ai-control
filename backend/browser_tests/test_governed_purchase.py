"""Authenticated Chromium regression test against the built console and a real worker."""

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread

import httpx
import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from nexus.app import create_app
from nexus.cli import seed
from nexus.config import Settings
from nexus.db import migrate


BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "dist"


@pytest.fixture
def workspace(tmp_path):
    assert (FRONTEND / "index.html").is_file(), "Build the frontend before running the browser test."
    password = secrets.token_urlsafe(24)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        settings = Settings(
            database_url=f"sqlite:///{(tmp_path / 'control.db').as_posix()}",
            mock_database=str(tmp_path / "business.db"),
            secret=secrets.token_urlsafe(48),
            agent_secret=secrets.token_urlsafe(48),
            origin=origin,
            frontend_dir=str(FRONTEND),
        )
        app = create_app(settings)
        migrate(app.state.engine, app.state.factory)
        assert seed(app.state.factory, password)

        env = {name: value for name, value in os.environ.items() if not name.startswith("NEXUS_")}
        env.update(
            PYTHONPATH=str(BACKEND),
            NEXUS_DATABASE_URL=settings.database_url,
            NEXUS_MOCK_DATABASE=settings.mock_database,
            NEXUS_SECRET=settings.secret,
            NEXUS_AGENT_SECRET=settings.agent_secret,
            NEXUS_ORIGIN=origin,
            NEXUS_MODE="local",
            NEXUS_POLICY_MODE="reference",
            NEXUS_BUSINESS_CONNECTOR="synthetic",
        )
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=5))
        api = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        with subprocess.Popen([sys.executable, "-m", "nexus.worker"], cwd=tmp_path, env=env) as worker:
            api.start()
            try:
                with httpx.Client(trust_env=False, timeout=1) as client:
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        assert api.is_alive() and worker.poll() is None, "API or worker exited during startup."
                        try:
                            if client.get(f"{origin}/health/ready").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.1)
                    else:
                        pytest.fail("NEXUS API did not become ready.")
                yield origin, password, app.state.connector
            finally:
                server.should_exit = True
                api.join(timeout=10)
                if worker.poll() is None:
                    worker.terminate()
                    try:
                        worker.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        worker.kill()
                        worker.wait(timeout=5)
                app.state.engine.dispose()
                assert not api.is_alive(), "The test API did not stop."


def sign_in(page, origin, email, password):
    page.goto(origin)
    page.locator('input[name="email"]').fill(email)
    page.locator('input[name="password"]').fill(password)
    page.get_by_role("button", name="Sign in to workspace").click()
    expect(page.get_by_role("link", name="AI command center", exact=True)).to_be_visible()


def test_independently_approved_purchase_reaches_verified_execution(workspace):
    origin, password, ledger = workspace
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("NEXUS_TEST_CHROMIUM") or None,
        )
        exceptions = []
        owner = browser.new_page(viewport={"width": 1440, "height": 1000})
        reviewer = browser.new_page(viewport={"width": 1440, "height": 1000})
        for page in (owner, reviewer):
            page.on("pageerror", lambda error: exceptions.append(str(error)))

        sign_in(owner, origin, "owner@nexus.local", password)
        owner.get_by_role("button", name="Run governed action").click()
        owner.locator('select[name="agent"]').select_option(label="Procurement Atlas")
        owner.locator('select[name="tool"]').select_option(label="Purchase requests")
        owner.locator('input[name="amount"]').fill("12500.00")
        owner.locator('input[name="purpose"]').fill("Synthetic purchase for the browser regression")
        with owner.expect_response(
            lambda response: response.url == f"{origin}/v1/console/actions"
            and response.request.method == "POST"
        ) as submitted:
            owner.get_by_role("button", name="Submit for policy evaluation").click()
        assert submitted.value.status == 202
        action = submitted.value.json()
        assert action["status"] == "awaiting_approval"
        expect(owner.get_by_role("button", name="Review request")).to_be_visible()
        owner.get_by_role("button", name="Review request").click()
        expect(owner.get_by_role("button", name="Approve action")).to_be_disabled()
        owner.get_by_role("button", name="Close dialog").click()
        assert ledger.count() == 0

        sign_in(reviewer, origin, "reviewer@nexus.local", password)
        reviewer.get_by_role("link", name="Human approvals", exact=True).click()
        reviewer.get_by_role("button", name="Review request").click()
        expect(reviewer.get_by_text("Immutable SHA-256 fingerprint")).to_be_visible()
        reviewer.locator('textarea[name="comment"]').fill("Independently reviewed the synthetic purchase.")
        with reviewer.expect_response(
            lambda response: response.url.endswith("/decision")
            and response.request.method == "POST"
        ) as decided:
            reviewer.get_by_role("button", name="Approve action").click()
        assert decided.value.status == 200

        owner.get_by_role("link", name="Execution ledger", exact=True).click()
        reference = "ACT-" + action["id"][:8].upper()
        row = owner.get_by_role("row").filter(has_text=reference)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if row.count() and "Verified" in row.inner_text():
                break
            refresh = owner.get_by_role("button", name="Refresh workspace")
            expect(refresh).to_be_enabled()
            refresh.click()
            owner.wait_for_timeout(250)
        expect(row).to_contain_text("Verified", timeout=1000)
        row.click()
        expect(owner.get_by_text("Action evidence", exact=True)).to_be_visible()
        expect(owner.get_by_text("Execution Verified", exact=True)).to_be_visible()
        assert ledger.count() == 1
        assert ledger.lookup(action["id"])["amount"] == "12500.00"
        assert not exceptions
        browser.close()
