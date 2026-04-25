"""Stage 6 — autonomous validation loop.

Runs `python src/run.py` up to 5 times; on failure, asks the LLM to diagnose,
applies a patch (selector/timing/validation), retries. Emits JSON summary to stdout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.llm_call import ask


DIAGNOSIS_PROMPT = """You are a Playwright automation expert diagnosing a failed run.

Context:
  Project: {project}
  URL: {url}
  Attempt: {attempt}/{max}

Error:
  Type: {error_type}
  Message: {error_message}

Classify the root cause and propose a patch.

Respond as JSON ONLY:
{{
  "type": "selector"|"timing"|"validation"|"logic",
  "element": "<selectors.yaml name if selector>",
  "new_selector": "<Playwright selector if selector>",
  "wait_ms": <int if timing>,
  "config_key": "<dotted path if validation>",
  "config_value": <value if validation>,
  "patch_diff": "<unified diff if logic>",
  "confidence": 0.0-1.0,
  "reasoning": "<1-3 sentences>"
}}
"""


def classify_error(message: str) -> str:
    m = message.lower()
    if "timeout" in m and "locator" in m:
        return "selector"
    if "elementnotfound" in m or "all fallbacks failed" in m or "all selectors failed" in m:
        return "selector"
    if "validationerror" in m or "missing columns" in m or "row count" in m:
        return "validation"
    if "timeout" in m:
        return "timing"
    return "logic"


def apply_diagnosis(project_dir: Path, diag: dict) -> bool:
    t = diag.get("type")
    if t == "selector":
        return _patch_selector(project_dir, diag)
    if t == "timing":
        return _patch_timing(project_dir, diag)
    if t == "validation":
        return _patch_config(project_dir, diag)
    if t == "logic":
        # logic patches require manual approval; return False to force escalation
        return False
    return False


def _patch_selector(project_dir: Path, diag: dict) -> bool:
    sel_path = project_dir / "selectors.yaml"
    data = yaml.safe_load(sel_path.read_text(encoding="utf-8")) or {}
    name = diag.get("element")
    new_sel = diag.get("new_selector")
    if not name or not new_sel:
        return False
    entry = data.setdefault(name, {"description": name, "fallbacks": [], "ai_discovered": []})
    entry.setdefault("ai_discovered", []).append({
        "selector": new_sel,
        "discovered_at": dt.datetime.now().astimezone().isoformat(),
        "success_count": 0,
        "reasoning": diag.get("reasoning", ""),
    })
    with sel_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return True


def _patch_timing(project_dir: Path, diag: dict) -> bool:
    # Simple strategy: append a wait call after the first step in navigate.py
    nav_path = project_dir / "src" / "navigate.py"
    if not nav_path.exists():
        return False
    content = nav_path.read_text(encoding="utf-8")
    wait_ms = int(diag.get("wait_ms", 2000))
    marker = "def steps("
    if marker not in content:
        return False

    # Guard against duplicate import time
    if "import time\n" not in content:
        patched = content.replace(marker, f"import time\n\n{marker}", 1)
    else:
        patched = content

    # Guard against duplicate sleep injection
    if "time.sleep(" not in patched:
        patched = re.sub(
            r"(def steps\([^)]*\)[^:]*:)",
            rf"\1\n    time.sleep({wait_ms / 1000})",
            patched, count=1,
        )

    if patched == content:
        return False  # No change
    nav_path.write_text(patched, encoding="utf-8")
    return True


def _patch_config(project_dir: Path, diag: dict) -> bool:
    key = diag.get("config_key")
    value = diag.get("config_value")
    if not key:
        return False
    cfg_path = project_dir / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    parts = key.split(".")
    node = cfg
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return True


def run_once(project_dir: Path, timeout: int = 180) -> dict:
    py = project_dir / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    # Force UTF-8 in the child + decoder. Without explicit encoding, Windows
    # defaults to cp949 and any Korean log line from run.py crashes
    # subprocess._readerthread on read.
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        result = subprocess.run(
            [str(py), "src/run.py"], cwd=project_dir,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=env,
        )
        # subprocess docs say stdout/stderr are str when text=True, but in
        # practice they can be None on certain platforms / when the process
        # produced no output. Tail-slicing None crashes the loop, so coerce.
        return {
            "exit": result.returncode,
            "stdout": (result.stdout or "")[-2000:],
            "stderr": (result.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired as e:
        return {"exit": 124, "stdout": "", "stderr": f"TimeoutExpired: {e}"}


def diagnose(project_dir: Path, run_result: dict, attempt: int, max_attempts: int,
             config: dict) -> dict:
    error_msg = (run_result.get("stderr") or "") + "\n" + (run_result.get("stdout") or "")
    pre_classified = classify_error(error_msg)

    prompt = DIAGNOSIS_PROMPT.format(
        project=config["project"]["name"],
        url=config["project"]["url"],
        attempt=attempt, max=max_attempts,
        error_type=pre_classified,
        error_message=error_msg[-1500:],
    )
    try:
        diag = ask(prompt, preference=config["healing"]["ai_provider"], max_tokens=1500)
    except Exception as e:
        return {"type": pre_classified, "error": str(e)}
    return diag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="After success, require 3 consecutive passes")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    config = yaml.safe_load((project_dir / "config.yaml").read_text(encoding="utf-8"))
    max_attempts = config["healing"].get("dev_max_attempts", 5)

    attempts_log: list[dict] = []

    for attempt in range(1, max_attempts + 1):
        result = run_once(project_dir)
        attempts_log.append({"attempt": attempt, "exit": result["exit"]})

        if result["exit"] == 0:
            if not args.strict:
                print(json.dumps({"status": "success", "attempt": attempt,
                                  "log": attempts_log}, ensure_ascii=False))
                return 0
            # Strict: require 3 consecutive passes
            streak = 1
            for j in range(2):
                r2 = run_once(project_dir)
                attempts_log.append({"attempt": f"{attempt}.{j+2}", "exit": r2["exit"]})
                if r2["exit"] == 0:
                    streak += 1
                else:
                    break
            if streak >= 3:
                print(json.dumps({"status": "success_strict", "attempt": attempt,
                                  "log": attempts_log}, ensure_ascii=False))
                return 0
            # Strict failed → fall through to diagnose using the non-0 result
            result = r2

        diag = diagnose(project_dir, result, attempt, max_attempts, config)
        attempts_log[-1]["diagnosis"] = diag

        if diag.get("type") == "logic":
            print(json.dumps({"status": "escalate_logic", "attempt": attempt,
                              "diagnosis": diag, "log": attempts_log}, ensure_ascii=False))
            return 5

        applied = apply_diagnosis(project_dir, diag)
        attempts_log[-1]["applied"] = applied
        if not applied:
            print(json.dumps({"status": "escalate_no_patch", "attempt": attempt,
                              "diagnosis": diag, "log": attempts_log}, ensure_ascii=False))
            return 6

    print(json.dumps({"status": "escalate_budget_exhausted",
                      "attempts": max_attempts, "log": attempts_log}, ensure_ascii=False))
    return 7


if __name__ == "__main__":
    sys.exit(main())
