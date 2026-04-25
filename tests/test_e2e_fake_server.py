"""E2E test against the fake server. Skipped by default; run with: pytest -m e2e."""

from pathlib import Path
import pytest

pytestmark = pytest.mark.skip(reason="E2E requires real Playwright browser + network; manual only")


def test_e2e_full_pipeline(tmp_path):
    """
    Manual test (not run in CI). Steps:
      1. In one terminal: python tests/fixtures/fake_server.py
      2. In another:     /udd with URL http://127.0.0.1:<port>/login
      3. Expect: project folder created, download succeeds, scheduler registered.
    See tests/fixtures/fake_server.py for the fake system.
    """
    pass
