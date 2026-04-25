"""Stage 3 — launch Playwright codegen for session capture.

Modes:
- ``setup`` (first-time): one browser session that logs in AND records the
  download flow. Produces both ``auth/storage.json`` and
  ``recordings/raw_recording.py``. Replaces having to run Stage 3 + Stage 4
  separately on first setup. Recommended for fresh projects.
- ``save`` (re-login lifecycle): refresh storage.json only. Used by ``udd login``
  when an existing session has expired.
- ``verify`` (assertion): headless check that storage_state is still valid.

``record_flow.py`` (Stage 4) remains for the retrain lifecycle (``udd retrain``),
which re-records the click path while reusing the saved session.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def build_codegen_command(
    python_exe: str,
    mode: str,
    storage_path: Path,
    url: str,
    output: Path | None = None,
    channel: str | None = None,
) -> list[str]:
    """Build playwright codegen invocation.

    ``mode``:
    - ``save`` — capture storage_state only (no recording output).
    - ``record`` — load existing storage_state, record actions to ``output``.
    - ``setup`` — first-time combined: capture storage AND record actions to
      ``output`` in a single browser session.

    ``channel`` (optional): override the browser binary. ``None`` (default)
    uses Playwright's bundled Chromium. Set to ``"chrome"`` / ``"msedge"`` to
    use the system browser — useful when a target site blocks the bundled
    Chromium fingerprint (some Korean government / enterprise sites do this).
    """
    cmd = [python_exe, "-m", "playwright", "codegen", "--target", "python"]
    if channel:
        cmd += ["--channel", channel]
    if mode == "save":
        cmd += ["--save-storage", str(storage_path)]
    elif mode == "record":
        cmd += ["--load-storage", str(storage_path)]
        if output is None:
            raise ValueError("mode=record requires output path")
        cmd += ["--output", str(output)]
    elif mode == "setup":
        if output is None:
            raise ValueError("mode=setup requires output path")
        cmd += ["--save-storage", str(storage_path), "--output", str(output)]
    else:
        raise ValueError(f"Unknown mode: {mode!r}")
    cmd.append(url)
    return cmd


def project_python(project_dir: Path) -> str:
    if sys.platform == "win32":
        return str(project_dir / ".venv" / "Scripts" / "python.exe")
    return str(project_dir / ".venv" / "bin" / "python")


def load_config(project_dir: Path) -> dict:
    with (project_dir / "config.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_browser_channel(config: dict) -> str | None:
    """Return the configured browser channel (``chrome`` / ``msedge`` / ...) or None.

    Reads ``auth.browser_channel`` from config.yaml. ``None`` (default) means use
    Playwright's bundled Chromium. Set to ``"chrome"`` when a target site blocks
    the bundled Chromium fingerprint (some Korean government / enterprise sites).
    """
    auth = config.get("auth") or {}
    channel = auth.get("browser_channel")
    return channel if channel else None


def verify_session(
    project_dir: Path, url: str, storage_path: Path, channel: str | None = None
) -> bool:
    """Launch a headless browser, load storage, visit URL, verify no login redirect."""
    py = project_python(project_dir)
    launch_kwargs = "headless=True"
    if channel:
        launch_kwargs += f", channel={channel!r}"
    script = f"""
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch({launch_kwargs})
    ctx = b.new_context(storage_state={str(storage_path)!r})
    p = ctx.new_page()
    p.goto({url!r}, wait_until='domcontentloaded')
    sys.exit(0 if 'login' not in p.url.lower() or p.url == {url!r} else 1)
"""
    result = subprocess.run([py, "-c", script], capture_output=True, timeout=60)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--mode", choices=["setup", "save", "verify"], default="save")
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
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    channel = args.browser_channel or get_browser_channel(config)

    if args.mode == "setup":
        recording_path = project_dir / "recordings" / "raw_recording.py"
        recording_path.parent.mkdir(parents=True, exist_ok=True)
        print(
            f"Opening browser to {url}. Log in, navigate to the data, click the download button, "
            "then close the browser. Both the session and the recording are captured in this single run.",
            file=sys.stderr,
        )
        cmd = build_codegen_command(
            project_python(project_dir), "setup", storage_path, url, recording_path,
            channel=channel,
        )
        subprocess.run(cmd, check=False)

        if not storage_path.exists():
            print(f"ERROR: storage not saved at {storage_path}", file=sys.stderr)
            return 1
        if not recording_path.exists():
            print(f"ERROR: recording not saved at {recording_path}", file=sys.stderr)
            return 2
        print(f"Saved session to {storage_path}", file=sys.stderr)
        print(f"Saved recording to {recording_path}", file=sys.stderr)

        if not verify_session(project_dir, url, storage_path, channel=channel):
            print("WARNING: session saved but verification failed.", file=sys.stderr)
            return 1

        sys.path.insert(0, str(Path(__file__).parent))
        from record_flow import validate_recording
        ok, issues = validate_recording(recording_path)
        if not ok:
            for issue in issues:
                print(f"- {issue}", file=sys.stderr)
            print(
                "Session saved but recording validation failed. "
                "Re-run with --mode setup to retry, or use record_flow.py alone to re-record.",
                file=sys.stderr,
            )
            return 3
        print("Session verified. Recording validated.")
        return 0

    if args.mode == "save":
        print(f"Opening browser to {url}. Log in, then close the browser.", file=sys.stderr)
        cmd = build_codegen_command(
            project_python(project_dir), "save", storage_path, url, channel=channel,
        )
        subprocess.run(cmd, check=False)
        if not storage_path.exists():
            print(f"ERROR: storage not saved at {storage_path}", file=sys.stderr)
            return 1
        print(f"Saved session to {storage_path}", file=sys.stderr)
        # verify immediately
        if verify_session(project_dir, url, storage_path, channel=channel):
            print("Session verified.")
            return 0
        print("WARNING: session saved but verification failed.", file=sys.stderr)
        return 1

    if args.mode == "verify":
        return 0 if verify_session(project_dir, url, storage_path, channel=channel) else 1


if __name__ == "__main__":
    sys.exit(main())
