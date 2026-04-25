"""Stage 0 — environment diagnostics. Emits a JSON report to stdout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.platform_detect import detect_autonomous_mode, detect_cli_host, detect_os


MIN_PYTHON = (3, 10)


def detect_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def detect_playwright_version() -> str | None:
    probe = (
        "import importlib.metadata as m;\n"
        "try:\n"
        "    print(m.version('playwright'))\n"
        "except m.PackageNotFoundError:\n"
        "    pass\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            return out or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def detect_chromium_installed() -> bool:
    """Check Playwright's browser cache dir."""
    cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.exists():
        cache = Path.home() / "AppData" / "Local" / "ms-playwright"
    if not cache.exists():
        return False
    return any(p.name.startswith("chromium") for p in cache.iterdir() if p.is_dir())


def detect_ai_providers() -> list[str]:
    providers = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append("anthropic")
    if os.environ.get("GEMINI_API_KEY"):
        providers.append("gemini")
    if os.environ.get("OPENAI_API_KEY"):
        providers.append("openai")
    return providers


def build_report(
    python_version: str,
    playwright_version: str | None,
    chromium_installed: bool,
    autonomous_mode: bool,
) -> dict:
    missing = []
    errors = []

    py_parts = tuple(int(x) for x in python_version.split(".")[:2])
    if py_parts < MIN_PYTHON:
        label = f"python>={MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
        errors.append(label)
        missing.append(label)
    if playwright_version is None:
        missing.append("playwright")
    if not chromium_installed:
        missing.append("chromium")

    providers = detect_ai_providers()

    if errors:
        status = "error"
    elif missing:
        status = "missing"
    else:
        status = "ok"

    return {
        "status": status,
        "python": python_version,
        "playwright": playwright_version,
        "chromium": chromium_installed,
        "ai_providers": providers,
        "autonomous_mode": autonomous_mode,
        "os": detect_os(),
        "cli_host": detect_cli_host(),
        "missing": missing,
        "errors": errors,
    }


def main() -> int:
    report = build_report(
        python_version=detect_python_version(),
        playwright_version=detect_playwright_version(),
        chromium_installed=detect_chromium_installed(),
        autonomous_mode=detect_autonomous_mode(),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] == "error":
        return 2
    if report["status"] == "missing":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
