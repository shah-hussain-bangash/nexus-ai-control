"""Keep Docker initialization compatible with injected runtime secrets."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("injected", [False, True])
def test_local_init_only_creates_env_when_secrets_need_generation(tmp_path, injected):
    backend = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith("NEXUS_")}
    env.update(PYTHONPATH=str(backend), NEXUS_MODE="local")
    if injected:
        env.update(NEXUS_SECRET="local-fixture-session-" + "x" * 32,
                   NEXUS_AGENT_SECRET="local-fixture-agent-" + "y" * 32)

    result = subprocess.run([sys.executable, "-m", "nexus.cli", "init"],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / "nexus.db").is_file()
    assert (tmp_path / ".env").is_file() is not injected
