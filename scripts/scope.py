"""Stage 1 — interactive intake that writes config.yaml.

Callable two ways:
  python scope.py <project_dir>            # interactive
  python scope.py <project_dir> --from-stdin  # reads 5-line stdin
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
_CRON_RE = re.compile(r"^\S+\s+\S+\s+\S+\s+\S+\s+\S+$")
_KO_WEEKDAY = {"월": "1", "화": "2", "수": "3", "목": "4", "금": "5", "토": "6", "일": "0"}


def validate_slug(name: str) -> None:
    if not _SLUG_RE.match(name):
        raise ValueError(
            f"Invalid slug: {name!r}. Use lowercase letters, digits, and hyphens only (e.g., 'erp-sales')."
        )


def cron_from_natural_language(text: str) -> str:
    t = text.strip().lower()
    if _CRON_RE.match(t):
        return t

    time_match = re.search(r"(\d{1,2})\s*[시:](?:\s*(\d{1,2}))?", t) or re.search(
        r"(\d{1,2}):(\d{2})", t
    )
    hour = "0"
    minute = "0"
    if time_match:
        hour = str(int(time_match.group(1)))
        if time_match.group(2):
            minute = str(int(time_match.group(2)))

    if "매일" in t or "daily" in t or "every day" in t:
        return f"{minute} {hour} * * *"

    weekly = re.search(r"매주\s*([월화수목금토일])요?일", t)
    if weekly:
        return f"{minute} {hour} * * {_KO_WEEKDAY[weekly.group(1)]}"

    if "매시" in t or "hourly" in t or "every hour" in t:
        return f"{minute} * * * *"

    raise ValueError(f"Could not parse schedule: {text!r}. Provide cron like '0 9 * * *'.")


def build_config(
    name: str,
    url: str,
    description: str,
    cron: str,
    expected_columns: list[str],
) -> dict:
    return {
        "project": {"name": name, "url": url, "description": description},
        "auth": {
            "mode": "session_replay",
            "storage_state": "auth/storage.json",
            "session_ttl_check": "daily",
            # null = use Playwright's bundled Chromium. Set to "chrome" or
            # "msedge" if the target site rejects the bundled fingerprint
            # (some Korean government / enterprise portals do this).
            "browser_channel": None,
        },
        "filters": {
            "start_date": "{today-30d}",
            "end_date": "{today}",
        },
        "download": {
            "save_dir": "downloads/{YYYY-MM-DD}/",
            "expected_format": "xlsx",
            "timeout_ms": 60000,
        },
        "validation": {
            "min_rows": 1,
            "expected_columns": expected_columns,
            "size_bounds_kb": [1, 51200],
            "columns_strict": False,
        },
        "healing": {
            "enabled": True,
            "max_ai_retries": 3,
            "dev_max_attempts": 5,
            "ai_provider": "auto",
            "promote_after": 10,
            "cool_down_hours": 24,
            "allow_logic_patches": False,
        },
        "schedule": {
            "cron": cron,
            "enabled": True,
            "os_task_name": f"UDD-{name.upper()}",
        },
        "notify": {
            "telegram": {
                "enabled": False,
                "chat_id": "",
                "bot_token_keyring": "udd-telegram/bot_token",
            },
            "on_success": False,
            "on_failure": True,
            "on_healing": True,
            "on_validation_warning": True,
        },
        "logging": {"level": "INFO", "retention_days": 90},
    }


def write_config(project_dir: Path, config: dict) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = project_dir / "config.yaml"
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return cfg_path


def prompt_interactive() -> dict:
    print("Q1. System name (lowercase-kebab, e.g., erp-sales):", file=sys.stderr)
    name = input().strip()
    validate_slug(name)

    print("Q2. Login URL:", file=sys.stderr)
    url = input().strip()

    print("Q3. One-line description:", file=sys.stderr)
    description = input().strip()

    print("Q4. Schedule (cron or natural language, e.g., '매일 09:00'):", file=sys.stderr)
    cron_raw = input().strip()
    cron = cron_from_natural_language(cron_raw)

    print("Q5. Expected columns (comma separated, empty to skip):", file=sys.stderr)
    cols_raw = input().strip()
    columns = [c.strip() for c in cols_raw.split(",") if c.strip()] if cols_raw else []

    return build_config(name, url, description, cron, columns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--from-stdin", action="store_true",
                        help="Read 5 answers from stdin (one per line)")
    args = parser.parse_args()

    if args.from_stdin:
        lines = sys.stdin.read().splitlines()
        if len(lines) < 5:
            print("Expected 5 lines on stdin.", file=sys.stderr)
            return 1
        name, url, description, cron_raw, cols_raw = lines[:5]
        validate_slug(name)
        cron = cron_from_natural_language(cron_raw)
        columns = [c.strip() for c in cols_raw.split(",") if c.strip()] if cols_raw else []
        config = build_config(name, url, description, cron, columns)
    else:
        config = prompt_interactive()

    cfg_path = write_config(args.project_dir, config)
    print(f"Wrote {cfg_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
