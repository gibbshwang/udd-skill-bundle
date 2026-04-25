"""Provider-agnostic LLM call wrapper.

Used by skill helper scripts (Stage 5 refactor, Stage 6 diagnosis).
Generated projects embed a functionally equivalent module at src/llm_client.py.

Default provider is Codex CLI so generated projects can comply with
environments where direct external AI API calls are not allowed.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class NoProviderError(RuntimeError):
    pass


def detect_provider_from_env(preference: str = "auto") -> str:
    """Return 'codex_cli' | 'anthropic' | 'gemini' | 'openai'.

    preference='auto' uses this fallback chain:
    codex_cli -> anthropic -> gemini -> openai.
    """
    if preference == "auto":
        if _codex_cli_available():
            return "codex_cli"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("GEMINI_API_KEY"):
            return "gemini"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        raise NoProviderError(
            "No AI provider found. Install/login Codex CLI or set "
            "ANTHROPIC_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY."
        )
    if preference in {"codex", "codex_cli", "codex-cli"}:
        return "codex_cli"
    if preference in {"anthropic", "claude"}:
        return "anthropic"
    if preference == "gemini":
        return "gemini"
    if preference == "openai":
        return "openai"
    raise ValueError(f"Unknown provider preference: {preference!r}")


def ask(
    prompt: str,
    image_bytes: bytes | None = None,
    preference: str = "auto",
    model_hint: str | None = None,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Send prompt (+ optional image) to chosen provider. Return parsed JSON dict."""
    provider = detect_provider_from_env(preference)
    if provider == "codex_cli":
        return _ask_codex_cli(prompt, image_bytes, model_hint, max_tokens)
    if provider == "anthropic":
        return _ask_anthropic(prompt, image_bytes, model_hint or "claude-sonnet-4-6", max_tokens)
    if provider == "gemini":
        return _ask_gemini(prompt, image_bytes, model_hint or "gemini-2.0-flash", max_tokens)
    if provider == "openai":
        return _ask_openai(prompt, image_bytes, model_hint or "gpt-4o-mini", max_tokens)
    raise RuntimeError(f"Unreachable: {provider}")


def _find_codex_cli_command() -> str | None:
    override = os.environ.get("CODEX_CLI_COMMAND")
    if override:
        return override

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate = Path(appdata) / "npm" / "codex.cmd"
            if candidate.exists():
                return str(candidate)
        for name in ("codex.cmd", "codex.exe", "codex"):
            found = shutil.which(name)
            if found and not found.lower().endswith(".ps1"):
                return found
        return None

    return shutil.which("codex")


def _codex_cli_available() -> bool:
    if os.environ.get("UDD_DISABLE_CODEX_CLI"):
        return False
    return _find_codex_cli_command() is not None


def _codex_json_schema() -> dict[str, Any]:
    # Generic object schema. Stage 5, Stage 6, and runtime healing each ask for
    # different keys, so the prompt owns the precise response contract.
    return {"type": "object", "additionalProperties": True}


def _ask_codex_cli(
    prompt: str,
    image_bytes: bytes | None,
    model: str | None,
    max_tokens: int,
) -> dict[str, Any]:
    command = _find_codex_cli_command()
    if not command:
        raise NoProviderError("Codex CLI not found. Set CODEX_CLI_COMMAND or install codex.")

    timeout = int(os.environ.get("CODEX_CLI_TIMEOUT_SECONDS", "180"))
    sandbox = os.environ.get("CODEX_CLI_SANDBOX", "read-only")
    cwd = os.environ.get("CODEX_CLI_CWD", os.getcwd())
    model = model or os.environ.get("CODEX_CLI_MODEL") or None

    wrapped_prompt = (
        prompt.rstrip()
        + "\n\nReturn only a JSON object. Do not include markdown, prose, or code fences."
        + f"\nKeep the response concise. Max output tokens requested by caller: {max_tokens}."
    )

    with tempfile.TemporaryDirectory(prefix="udd-codex-cli-") as tmp:
        tmp_path = Path(tmp)
        schema_path = tmp_path / "schema.json"
        result_path = tmp_path / "result.json"
        schema_path.write_text(json.dumps(_codex_json_schema()), encoding="utf-8")

        cmd = [
            command,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            sandbox,
            "--ask-for-approval",
            "never",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(result_path),
            "-C",
            cwd,
        ]
        if model:
            cmd += ["--model", model]
        if image_bytes:
            image_path = tmp_path / "screenshot.png"
            image_path.write_bytes(image_bytes)
            cmd += ["--image", str(image_path)]
        cmd.append("-")

        result = subprocess.run(
            cmd,
            input=wrapped_prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Codex CLI failed "
                f"(exit={result.returncode}): {(result.stderr or result.stdout)[-2000:]}"
            )

        text = result_path.read_text(encoding="utf-8") if result_path.exists() else result.stdout
        return _parse_json(text)


def _ask_anthropic(prompt: str, image_bytes: bytes | None, model: str, max_tokens: int) -> dict:
    from anthropic import Anthropic

    client = Anthropic()
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image_bytes:
        content.insert(0, {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(image_bytes).decode(),
            },
        })
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    )
    return _parse_json(_extract_anthropic_text(resp))


def _extract_anthropic_text(resp: Any) -> str:
    blocks = getattr(resp, "content", None) or []
    texts = [getattr(b, "text", None) for b in blocks if getattr(b, "type", None) == "text"]
    texts = [t for t in texts if t]
    if not texts:
        raise RuntimeError(
            f"Anthropic response contained no text blocks "
            f"(block types: {[getattr(b, 'type', '?') for b in blocks]!r})."
        )
    return "".join(texts)


def _ask_gemini(prompt: str, image_bytes: bytes | None, model: str, max_tokens: int) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    m = genai.GenerativeModel(model)
    parts: list = [prompt]
    if image_bytes:
        parts.append({"mime_type": "image/png", "data": image_bytes})
    resp = m.generate_content(
        parts,
        generation_config={
            "response_mime_type": "application/json",
            "max_output_tokens": max_tokens,
        },
    )
    return _parse_json(resp.text)


def _ask_openai(prompt: str, image_bytes: bytes | None, model: str, max_tokens: int) -> dict:
    from openai import OpenAI

    client = OpenAI()
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image_bytes:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"
            },
        })
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
    )
    return _parse_json(resp.choices[0].message.content)


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response (tolerates fences and short preambles)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise
