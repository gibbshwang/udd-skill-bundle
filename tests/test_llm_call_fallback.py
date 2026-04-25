from types import SimpleNamespace

import pytest

from lib.llm_call import _extract_anthropic_text, detect_provider_from_env, NoProviderError


def test_detect_auto_picks_codex_cli_first(clear_ai_env, monkeypatch):
    monkeypatch.delenv("UDD_DISABLE_CODEX_CLI", raising=False)
    monkeypatch.setenv("CODEX_CLI_COMMAND", "codex-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert detect_provider_from_env("auto") == "codex_cli"


def test_detect_auto_picks_anthropic_first(clear_ai_env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert detect_provider_from_env("auto") == "anthropic"


def test_detect_auto_picks_gemini_when_no_anthropic(clear_ai_env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert detect_provider_from_env("auto") == "gemini"


def test_detect_auto_picks_openai_when_only_it(clear_ai_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert detect_provider_from_env("auto") == "openai"


def test_detect_explicit_forces_choice(clear_ai_env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    # Explicit override — returns what was asked even if its key is missing
    # (actual call will fail elsewhere; detect is about choice only)
    assert detect_provider_from_env("openai") == "openai"
    assert detect_provider_from_env("codex_cli") == "codex_cli"


def test_detect_none_raises(clear_ai_env):
    with pytest.raises(NoProviderError):
        detect_provider_from_env("auto")


def _block(type_: str, **kwargs):
    return SimpleNamespace(type=type_, **kwargs)


def test_extract_text_picks_text_block_past_tool_use():
    resp = SimpleNamespace(content=[
        _block("tool_use", id="t1", name="search", input={}),
        _block("text", text='{"ok": true}'),
    ])
    assert _extract_anthropic_text(resp) == '{"ok": true}'


def test_extract_text_concatenates_multiple_text_blocks():
    resp = SimpleNamespace(content=[
        _block("text", text='{"a": 1'),
        _block("tool_use", id="t1", name="x", input={}),
        _block("text", text=',"b": 2}'),
    ])
    assert _extract_anthropic_text(resp) == '{"a": 1,"b": 2}'


def test_extract_text_raises_when_no_text_blocks():
    resp = SimpleNamespace(content=[
        _block("tool_use", id="t1", name="x", input={}),
    ])
    with pytest.raises(RuntimeError, match="no text blocks"):
        _extract_anthropic_text(resp)
