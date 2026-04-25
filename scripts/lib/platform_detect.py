"""Detect the host OS and AI CLI the skill is running under."""

from __future__ import annotations

import os
import sys


def detect_os() -> str:
    """Return 'windows' | 'macos' | 'linux'."""
    platform = sys.platform
    if platform == "win32":
        return "windows"
    if platform == "darwin":
        return "macos"
    return "linux"


def detect_cli_host() -> str:
    """Return 'claude' | 'gemini' | 'codex' | 'unknown'.

    Codex is checked **before** Claude/Gemini because nested invocations
    (e.g. ``codex exec`` started from a Claude Code shell) inherit the parent
    CLAUDECODE / GEMINI_CLI env vars but are *executing under* Codex. The
    innermost host is what matters for autonomous-mode behavior.
    """
    if (
        os.environ.get("CODEX_THREAD_ID")
        or os.environ.get("CODEX_MANAGED_BY_NPM")
        or os.environ.get("CODEX_CLI_VERSION")
    ):
        return "codex"
    if (
        os.environ.get("CLAUDECODE")
        or os.environ.get("CLAUDE_CODE_VERSION")
        or os.environ.get("CLAUDE_SESSION_ID")
    ):
        return "claude"
    if os.environ.get("GEMINI_CLI") or os.environ.get("GEMINI_CLI_VERSION"):
        return "gemini"
    return "unknown"


def detect_autonomous_mode() -> bool:
    """True when the host CLI was started with permission-bypass flag."""
    if os.environ.get("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS") == "1":
        return True
    if os.environ.get("GEMINI_YOLO") == "1":
        return True
    if os.environ.get("CODEX_APPROVAL_MODE") == "never":
        return True
    # Codex 0.125+ doesn't expose an "approval mode" env var. Both ``codex
    # exec`` and ``codex --full-auto`` run non-interactively (no per-tool
    # prompts), and ``CODEX_THREAD_ID`` is set in both. Interactive ``codex``
    # TUI also sets it, but in that mode the user is at a prompt so the
    # validate loop wouldn't be running unattended anyway. Trust the
    # thread-id signal as a good-enough autonomous indicator.
    if os.environ.get("CODEX_THREAD_ID"):
        return True
    return False


def ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8.

    Windows Python defaults to the active code page (cp949 on Korean
    locale), so printing non-ASCII text raises UnicodeEncodeError. Call
    this at the top of any entry point that writes Korean — run.py, cli.py,
    and skill helper scripts. No-op on platforms that already default to
    UTF-8.
    """
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            pass
