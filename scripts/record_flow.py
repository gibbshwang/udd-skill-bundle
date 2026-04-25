"""Stage 4 — Playwright codegen recording of the full download path.

Prerequisite: Stage 3 completed (storage.json exists).
Produces: recordings/raw_recording.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from auth_flow import build_codegen_command, get_browser_channel, project_python


def validate_recording(path: Path) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not path.exists():
        return False, [f"Recording file not found: {path}"]
    content = path.read_text(encoding="utf-8")
    if "page.goto" not in content:
        issues.append("Missing page.goto call — did you navigate anywhere?")
    has_download = (
        "expect_download" in content
        or "download" in content.lower() and "button" in content.lower()
    )
    if not has_download:
        issues.append("No expect_download or download-trigger pattern detected.")
    return (len(issues) == 0, issues)


def load_config(project_dir: Path) -> dict:
    with (project_dir / "config.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument(
        "--browser-channel",
        default=None,
        help="Override browser channel (e.g. 'chrome'). Falls back to "
        "auth.browser_channel in config.yaml, then to bundled Chromium.",
    )
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    config = load_config(project_dir)
    url = config["project"]["url"]
    storage_path = project_dir / config["auth"]["storage_state"]
    output_path = project_dir / "recordings" / "raw_recording.py"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    channel = args.browser_channel or get_browser_channel(config)

    if not storage_path.exists():
        print(f"ERROR: session not found. Run auth_flow.py first.", file=sys.stderr)
        return 2

    print(f"Opening browser to {url}.", file=sys.stderr)
    print("Navigate to the download, complete it, then close the browser.", file=sys.stderr)

    cmd = build_codegen_command(
        project_python(project_dir), "record", storage_path, url, output_path,
        channel=channel,
    )
    subprocess.run(cmd, check=False)

    ok, issues = validate_recording(output_path)
    if ok:
        print(f"Recording saved: {output_path}")
        return 0

    for issue in issues:
        print(f"- {issue}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
