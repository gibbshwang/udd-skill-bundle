"""UDD orchestration harness.

This is the canonical entrypoint for exercising the UDD pipeline as a harness,
not merely using the templates as a project generator. It records every stage
execution in ``.udd/state.json`` so a reviewer can distinguish a real UDD run
from hand-built project files.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


STAGE_ORDER = [
    "precheck",
    "scope",
    "scaffold",
    "auth_setup",
    "record",
    "refactor",
    "validate",
    "approve",
    "schedule",
    "handoff",
]

STAGE_NUMBERS = {
    "0": "precheck",
    "1": "scope",
    "2": "scaffold",
    "3": "auth_setup",
    "4": "record",
    "5": "refactor",
    "6": "validate",
    "7": "approve",
    "8": "schedule",
    "9": "handoff",
}

ARTIFACTS = {
    "scope": ["config.yaml"],
    "scaffold": ["config.yaml", "src/run.py", "selectors.yaml", "requirements.txt", "README.md"],
    "auth_setup": ["auth/storage.json", "recordings/raw_recording.py"],
    "record": ["recordings/raw_recording.py"],
    "refactor": ["selectors.yaml", "src/navigate.py"],
    "validate": ["downloads", "logs"],
    "schedule": ["config.yaml"],
    "handoff": ["README.md"],
}

INTAKE_QUESTIONS = [
    ("slug", "System slug (lowercase-kebab, e.g. erp-sales)"),
    ("url", "Login or entry URL"),
    (
        "site_type",
        "Site type (authenticated_browser, public_browser_download, public_metadata_redirect, api, static_file)",
    ),
    ("description", "One-line description"),
    ("schedule", "Schedule (cron or natural language, e.g. daily 09:00)"),
    ("expected_columns", "Expected columns (comma-separated; empty to skip)"),
]


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_stage(stage: str) -> str:
    value = stage.strip()
    return STAGE_NUMBERS.get(value, value)


def state_path(project_dir: Path) -> Path:
    return project_dir / ".udd" / "state.json"


def load_state(project_dir: Path) -> dict[str, Any]:
    path = state_path(project_dir)
    if not path.exists():
        return {
            "schema_version": 1,
            "project_dir": str(project_dir),
            "created_at": now_iso(),
            "updated_at": None,
            "mode": "normal",
            "stages": [],
            "manual_changes": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(project_dir: Path, state: dict[str, Any]) -> None:
    path = state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def completed_stages(state: dict[str, Any]) -> set[str]:
    return {
        item["stage"]
        for item in state.get("stages", [])
        if item.get("status") == "completed"
    }


def require_previous(state: dict[str, Any], stage: str, force: bool = False) -> None:
    if force:
        return
    idx = STAGE_ORDER.index(stage)
    done = completed_stages(state)
    missing = [name for name in STAGE_ORDER[:idx] if name not in done]
    if missing:
        raise SystemExit(
            f"Refusing to run stage {stage!r}; previous stages are missing: {', '.join(missing)}. "
            "Use --force only for an explicitly documented recovery."
        )


def tail(value: str | None, limit: int = 4000) -> str:
    return (value or "")[-limit:]


# Per-stage timeout (seconds). Interactive stages (auth_setup, record) need
# the long ceiling because the user is driving a real browser; non-interactive
# stages should fail fast if they hang.
STAGE_TIMEOUTS: dict[str, int] = {
    "precheck": 120,
    "scope": 120,
    "scaffold": 1800,       # venv + browser install can take a while
    "auth_setup": 2700,     # 45 min — user-driven login
    "record": 2700,         # 45 min — user-driven recording
    "refactor": 600,
    "validate": 1200,
    "approve": 600,
    "schedule": 120,
    "handoff": 120,
}
DEFAULT_TIMEOUT = 600


def run_command(
    command: list[str],
    cwd: Path | None = None,
    timeout: int | None = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        stdout_text = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", "replace") if e.stdout else "")
        stderr_text = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", "replace") if e.stderr else "")
        return {
            "command": command,
            "exit_code": 124,  # GNU coreutils convention for timeout
            "stdout_tail": tail(stdout_text),
            "stderr_tail": tail(stderr_text + f"\n[harness] subprocess timed out after {timeout}s"),
            "timed_out": True,
        }
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout_tail": tail(result.stdout),
        "stderr_tail": tail(result.stderr),
    }


def artifact_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_snapshot(project_dir: Path, stage: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for rel in ARTIFACTS.get(stage, []):
        path = project_dir / rel
        if path.is_dir():
            snapshot[rel] = {
                "type": "dir",
                "exists": True,
                "children": sorted(p.name for p in path.iterdir())[:50],
            }
        else:
            snapshot[rel] = {
                "type": "file",
                "exists": path.exists(),
                "sha256": artifact_hash(path),
            }
    return snapshot


def append_stage(
    project_dir: Path,
    state: dict[str, Any],
    stage: str,
    result: dict[str, Any],
    *,
    status: str | None = None,
    degraded: bool = False,
    notes: str | None = None,
    user_input: dict[str, Any] | None = None,
) -> None:
    entry = {
        "stage": stage,
        "status": status or ("completed" if result["exit_code"] == 0 else "failed"),
        "started_at": now_iso(),
        "finished_at": now_iso(),
        "command": result["command"],
        "exit_code": result["exit_code"],
        "stdout_tail": result.get("stdout_tail", ""),
        "stderr_tail": result.get("stderr_tail", ""),
        "degraded": degraded,
        "notes": notes,
        "artifacts": artifact_snapshot(project_dir, stage),
    }
    if user_input is not None:
        entry["user_input"] = user_input
    state.setdefault("stages", []).append(entry)
    if degraded:
        state["mode"] = "degraded"
    save_state(project_dir, state)


def read_answers(args: argparse.Namespace) -> dict[str, str]:
    if args.answers_file:
        path = Path(args.answers_file).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        answers = {key: str(data.get(key, "")) for key, _ in INTAKE_QUESTIONS}
        answers["site_type"] = answers["site_type"] or "authenticated_browser"
        return answers

    answers: dict[str, str] = {}
    for key, question in INTAKE_QUESTIONS:
        print(question + ":", file=sys.stderr)
        answers[key] = input().strip()
    return answers


def patch_scope_metadata(project_dir: Path, answers: dict[str, str]) -> None:
    cfg_path = project_dir / "config.yaml"
    if not cfg_path.exists():
        return
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg.setdefault("project", {})["site_type"] = answers.get("site_type") or "authenticated_browser"
    cfg.setdefault("udd", {})["intake_source"] = "harness"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def stage_precheck(project_dir: Path, state: dict[str, Any]) -> int:
    result = run_command(
        [sys.executable, str(scripts_dir() / "precheck.py")],
        timeout=STAGE_TIMEOUTS.get("precheck", DEFAULT_TIMEOUT),
    )
    append_stage(project_dir, state, "precheck", result)
    print(result["stdout_tail"])
    return result["exit_code"]


def stage_scope(project_dir: Path, state: dict[str, Any], args: argparse.Namespace) -> int:
    answers = read_answers(args)
    payload = "\n".join(
        [
            answers["slug"],
            answers["url"],
            answers["description"],
            answers["schedule"],
            answers["expected_columns"],
        ]
    ) + "\n"
    command = [
        sys.executable,
        str(scripts_dir() / "scope.py"),
        str(project_dir),
        "--from-stdin",
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        completed = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=STAGE_TIMEOUTS.get("scope", DEFAULT_TIMEOUT),
        )
    except subprocess.TimeoutExpired as e:
        stdout_text = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", "replace") if e.stdout else "")
        stderr_text = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", "replace") if e.stderr else "")
        result = {
            "command": command,
            "exit_code": 124,
            "stdout_tail": tail(stdout_text),
            "stderr_tail": tail(stderr_text + f"\n[harness] scope stage timed out"),
            "timed_out": True,
        }
        intake_source = "answers_file" if args.answers_file else "interactive"
        append_stage(
            project_dir,
            state,
            "scope",
            result,
            user_input={
                "source": intake_source,
                "slug": answers["slug"],
                "url": answers["url"],
                "site_type": answers["site_type"],
                "description": answers["description"],
                "schedule": answers["schedule"],
                "expected_columns": answers["expected_columns"],
            },
        )
        return result["exit_code"]
    result = {
        "command": command,
        "exit_code": completed.returncode,
        "stdout_tail": tail(completed.stdout),
        "stderr_tail": tail(completed.stderr),
    }
    if completed.returncode == 0:
        patch_scope_metadata(project_dir, answers)
    intake_source = "answers_file" if args.answers_file else "interactive"
    append_stage(
        project_dir,
        state,
        "scope",
        result,
        user_input={
            "source": intake_source,
            "slug": answers["slug"],
            "url": answers["url"],
            "site_type": answers["site_type"],
            "description": answers["description"],
            "schedule": answers["schedule"],
            "expected_columns": answers["expected_columns"],
        },
    )
    return result["exit_code"]


def stage_scaffold(project_dir: Path, state: dict[str, Any], args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(scripts_dir() / "scaffold.py"),
        str(project_dir),
        "--skill-dir",
        str(skill_dir()),
    ]
    degraded = False
    notes = None
    if args.no_install:
        command.append("--no-install")
        degraded = True
        notes = "Skipped venv/dependency/browser installation at caller request."
    if args.no_git:
        command.append("--no-git")
        degraded = True
        notes = (notes + " " if notes else "") + "Skipped git initialization at caller request."
    result = run_command(command, timeout=STAGE_TIMEOUTS.get("scaffold", DEFAULT_TIMEOUT))
    append_stage(project_dir, state, "scaffold", result, degraded=degraded, notes=notes)
    return result["exit_code"]


def stage_command(project_dir: Path, stage: str, args: argparse.Namespace) -> list[str]:
    project_python = project_dir / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    py = str(project_python)
    if stage == "auth_setup":
        command = [py, str(scripts_dir() / "auth_flow.py"), str(project_dir), "--mode", "setup"]
        if args.browser_channel:
            command += ["--browser-channel", args.browser_channel]
        return command
    if stage == "record":
        return [py, str(scripts_dir() / "record_flow.py"), str(project_dir)]
    if stage == "refactor":
        return [py, str(scripts_dir() / "refactor.py"), str(project_dir)]
    if stage == "validate":
        return [py, str(scripts_dir() / "validate_loop.py"), str(project_dir)]
    if stage == "approve":
        return [py, str(scripts_dir() / "approve_flow.py"), str(project_dir)]
    if stage == "schedule":
        return [py, str(scripts_dir() / "schedule_install.py"), str(project_dir)]
    if stage == "handoff":
        return [py, str(scripts_dir() / "handoff.py"), str(project_dir)]
    raise ValueError(f"No command for stage {stage!r}")


def run_later_stage(project_dir: Path, state: dict[str, Any], stage: str, args: argparse.Namespace) -> int:
    command = stage_command(project_dir, stage, args)
    result = run_command(
        command,
        cwd=project_dir,
        timeout=STAGE_TIMEOUTS.get(stage, DEFAULT_TIMEOUT),
    )
    append_stage(project_dir, state, stage, result)
    print(result["stdout_tail"])
    if result["stderr_tail"]:
        print(result["stderr_tail"], file=sys.stderr)
    return result["exit_code"]


def cmd_new(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    state = load_state(project_dir)
    save_state(project_dir, state)

    for stage in ("precheck", "scope", "scaffold"):
        if args.stop_after and STAGE_ORDER.index(stage) > STAGE_ORDER.index(args.stop_after):
            break
        if stage == "precheck":
            code = stage_precheck(project_dir, state)
        elif stage == "scope":
            code = stage_scope(project_dir, state, args)
        else:
            code = stage_scaffold(project_dir, state, args)
        if code != 0:
            return code
    return 0


def cmd_stage(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    stage = normalize_stage(args.stage)
    if stage not in STAGE_ORDER:
        raise SystemExit(f"Unknown stage: {args.stage}")
    state = load_state(project_dir)
    require_previous(state, stage, force=args.force)
    if args.force:
        state.setdefault("forced_runs", []).append(
            {"stage": stage, "at": now_iso(), "reason": "operator supplied --force"}
        )
        save_state(project_dir, state)
    if stage == "precheck":
        return stage_precheck(project_dir, state)
    if stage == "scope":
        return stage_scope(project_dir, state, args)
    if stage == "scaffold":
        return stage_scaffold(project_dir, state, args)
    return run_later_stage(project_dir, state, stage, args)


def cmd_status(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    state = load_state(project_dir)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir).resolve()
    state = load_state(project_dir)
    latest: dict[str, dict[str, Any]] = {}
    for entry in state.get("stages", []):
        for rel, meta in (entry.get("artifacts") or {}).items():
            if meta.get("type") == "file" and meta.get("sha256"):
                latest[rel] = meta

    changes = []
    for rel, meta in latest.items():
        current = artifact_hash(project_dir / rel)
        if current != meta.get("sha256"):
            changes.append({"path": rel, "recorded_sha256": meta.get("sha256"), "current_sha256": current})

    state["manual_changes"] = changes
    save_state(project_dir, state)
    print(json.dumps({"ok": not changes, "manual_changes": changes}, ensure_ascii=False, indent=2))
    return 1 if changes else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="udd-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Run stage 0-2 through the harness")
    p_new.add_argument("project_dir")
    p_new.add_argument("--answers-file", help="JSON file containing slug/url/description/schedule/expected_columns")
    p_new.add_argument("--stop-after", choices=STAGE_ORDER[:3])
    p_new.add_argument("--no-install", action="store_true", help="Degraded mode: skip scaffold dependency install")
    p_new.add_argument("--no-git", action="store_true", help="Degraded mode: skip scaffold git init")
    p_new.set_defaults(func=cmd_new)

    p_stage = sub.add_parser("stage", help="Run one stage and record state")
    p_stage.add_argument("project_dir")
    p_stage.add_argument("stage", help="Stage number or name")
    p_stage.add_argument("--answers-file", help="Required only for scripted stage=scope")
    p_stage.add_argument("--browser-channel", help="Browser channel for stage 3, e.g. chrome")
    p_stage.add_argument("--no-install", action="store_true")
    p_stage.add_argument("--no-git", action="store_true")
    p_stage.add_argument("--force", action="store_true", help="Run despite missing previous stages; recorded in state")
    p_stage.set_defaults(func=cmd_stage)

    p_status = sub.add_parser("status", help="Print .udd/state.json")
    p_status.add_argument("project_dir")
    p_status.set_defaults(func=cmd_status)

    p_audit = sub.add_parser("audit", help="Compare current artifacts to recorded stage hashes")
    p_audit.add_argument("project_dir")
    p_audit.set_defaults(func=cmd_audit)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
