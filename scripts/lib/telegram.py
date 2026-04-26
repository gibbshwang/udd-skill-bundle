"""Minimal Telegram send helper. Token read from OS keyring."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import keyring
import requests


log = logging.getLogger("udd.telegram")

KEYRING_SERVICE = "udd-telegram"
KEYRING_KEY = "bot_token"
API_BASE = "https://api.telegram.org"

_TOKEN_URL_RE = re.compile(r"(api\.telegram\.org/bot)[^/\s]+")


def _redact(text: str) -> str:
    """Redact bot tokens from Telegram URLs in error/log messages."""
    return _TOKEN_URL_RE.sub(r"\1<REDACTED>", text)


def get_token() -> str | None:
    return keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)


def send(chat_id: str, text: str, files: list[Path] | None = None) -> bool:
    token = get_token()
    if not token:
        log.warning("Telegram bot_token not in keyring (%s/%s)", KEYRING_SERVICE, KEYRING_KEY)
        return False

    url = f"{API_BASE}/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("Telegram send failed: %s", _redact(str(e)))
        return False

    for path in files or []:
        if not path.exists():
            continue
        doc_url = f"{API_BASE}/bot{token}/sendDocument"
        try:
            with path.open("rb") as f:
                r = requests.post(doc_url, data={"chat_id": chat_id},
                                  files={"document": (path.name, f)}, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            log.error("Telegram sendDocument failed: %s", _redact(str(e)))

    return True
