from lib.platform_detect import detect_os, detect_cli_host, detect_autonomous_mode


CLAUDE_VARS = ("CLAUDECODE", "CLAUDE_CODE_VERSION", "CLAUDE_SESSION_ID")
GEMINI_VARS = ("GEMINI_CLI", "GEMINI_CLI_VERSION")
CODEX_VARS = ("CODEX_CLI_VERSION",)
ALL_HOST_VARS = CLAUDE_VARS + GEMINI_VARS + CODEX_VARS


def _clear_all_host_vars(monkeypatch):
    for var in ALL_HOST_VARS:
        monkeypatch.delenv(var, raising=False)


def test_detect_os_returns_one_of_three():
    result = detect_os()
    assert result in {"windows", "macos", "linux"}


def test_detect_cli_host_claude_via_claudecode(monkeypatch):
    _clear_all_host_vars(monkeypatch)
    monkeypatch.setenv("CLAUDECODE", "1")
    assert detect_cli_host() == "claude"


def test_detect_cli_host_claude_via_version_env(monkeypatch):
    _clear_all_host_vars(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_VERSION", "1.0.0")
    assert detect_cli_host() == "claude"


def test_detect_cli_host_gemini_via_env(monkeypatch):
    _clear_all_host_vars(monkeypatch)
    monkeypatch.setenv("GEMINI_CLI_VERSION", "0.5.0")
    assert detect_cli_host() == "gemini"


def test_detect_cli_host_codex_via_env(monkeypatch):
    _clear_all_host_vars(monkeypatch)
    monkeypatch.setenv("CODEX_CLI_VERSION", "0.1.0")
    assert detect_cli_host() == "codex"


def test_detect_cli_host_unknown(monkeypatch):
    _clear_all_host_vars(monkeypatch)
    assert detect_cli_host() == "unknown"


def test_detect_autonomous_mode_claude(monkeypatch):
    monkeypatch.setenv("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS", "1")
    assert detect_autonomous_mode() is True


def test_detect_autonomous_mode_gemini(monkeypatch):
    monkeypatch.delenv("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS", raising=False)
    monkeypatch.setenv("GEMINI_YOLO", "1")
    assert detect_autonomous_mode() is True


def test_detect_autonomous_mode_codex(monkeypatch):
    monkeypatch.delenv("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS", raising=False)
    monkeypatch.delenv("GEMINI_YOLO", raising=False)
    monkeypatch.setenv("CODEX_APPROVAL_MODE", "never")
    assert detect_autonomous_mode() is True


def test_detect_autonomous_mode_off(monkeypatch):
    for var in ("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS", "GEMINI_YOLO", "CODEX_APPROVAL_MODE"):
        monkeypatch.delenv(var, raising=False)
    assert detect_autonomous_mode() is False
