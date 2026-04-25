"""Provider-agnostic LLM call wrapper.

Used by skill helper scripts (Stage 5 refactor, Stage 6 diagnosis).
Generated projects embed a functionally equivalent module at src/llm_client.py.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any


class NoProviderError(RuntimeError):
    pass


def detect_provider_from_env(preference: str = "auto") -> str:
    """Return 'anthropic' | 'gemini' | 'openai'.

    preference='auto' → env fallback chain (anthropic → gemini → openai)
    preference=<explicit> → forced (caller may still get runtime error if key missing)
    """
    if preference == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("GEMINI_API_KEY"):
            return "gemini"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        raise NoProviderError(
            "No AI provider API key found. Set ANTHROPIC_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY."
        )
    if preference in {"anthropic", "claude"}:
        return "anthropic"
    if preference == "gemini":
        return "gemini"
    if preference == "openai":
        return "openai"
    raise ValueError(f"Unknown provider preference: {preference!r}")


def ask(prompt: str, image_bytes: bytes | None = None,
        preference: str = "auto", model_hint: str | None = None,
        max_tokens: int = 1024) -> dict[str, Any]:
    """Send prompt (+ optional image) to chosen provider. Return parsed JSON dict.

    Models (if model_hint not provided):
      anthropic → claude-sonnet-4-6
      gemini    → gemini-2.0-flash
      openai    → gpt-4o-mini

    The prompt is expected to instruct the model to respond with JSON only.
    """
    provider = detect_provider_from_env(preference)
    if provider == "anthropic":
        return _ask_anthropic(prompt, image_bytes, model_hint or "claude-sonnet-4-6", max_tokens)
    if provider == "gemini":
        return _ask_gemini(prompt, image_bytes, model_hint or "gemini-2.0-flash", max_tokens)
    if provider == "openai":
        return _ask_openai(prompt, image_bytes, model_hint or "gpt-4o-mini", max_tokens)
    raise RuntimeError(f"Unreachable: {provider}")


def _ask_anthropic(prompt: str, image_bytes: bytes | None, model: str, max_tokens: int) -> dict:
    from anthropic import Anthropic
    client = Anthropic()
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image_bytes:
        content.insert(0, {
            "type": "image",
            "source": {
                "type": "base64", "media_type": "image/png",
                "data": base64.b64encode(image_bytes).decode(),
            },
        })
    resp = client.messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    )
    return _parse_json(_extract_anthropic_text(resp))


def _extract_anthropic_text(resp: Any) -> str:
    """Return the concatenated text of all text blocks in the response.

    The Anthropic Messages API returns a list of content blocks that may
    include non-text types (tool_use, thinking, etc.). Picking ``content[0]``
    blindly crashes with AttributeError when the first block lacks ``.text``.
    """
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
        generation_config={"response_mime_type": "application/json",
                           "max_output_tokens": max_tokens},
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
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
    )
    return _parse_json(resp.choices[0].message.content)


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response (tolerates ```json fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)
