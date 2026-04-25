"""Shared pytest fixtures for udd skill bundle tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure `scripts/` is on path for all tests
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def clear_ai_env(monkeypatch):
    """Remove all three AI provider env vars so tests start from a clean state."""
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def clear_cli_env(monkeypatch):
    """Remove CLI host + autonomous mode env vars."""
    for var in (
        "CLAUDE_CODE_VERSION",
        "CLAUDE_SESSION_ID",
        "GEMINI_CLI_VERSION",
        "CODEX_CLI_VERSION",
        "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS",
        "GEMINI_YOLO",
        "CODEX_APPROVAL_MODE",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Temporary project directory with standard subfolders."""
    d = tmp_path / "test-project"
    for sub in ("src", "tests", "auth", "downloads", "logs", "recordings"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d
