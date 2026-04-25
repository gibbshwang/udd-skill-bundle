"""Stage 8 — register the generated project with the OS scheduler."""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.platform_detect import detect_os


_WEEKDAY_NAMES = {"0": "SUN", "1": "MON", "2": "TUE", "3": "WED", "4": "THU", "5": "FRI", "6": "SAT"}


def extract_start_time(cron: str) -> str:
    parts = cron.split()
    minute, hour = parts[0], parts[1]
    m = int(minute) if minute.isdigit() else 0
    h = int(hour) if hour.isdigit() else 0
    return f"{h:02d}:{m:02d}"


def cron_to_schtasks_schedule(cron: str) -> dict:
    parts = cron.split()
    minute, hour, dom, month, dow = parts

    result: dict = {"st": extract_start_time(cron)}

    if hour == "*":
        result["sc"] = "HOURLY"
        return result
    if dow != "*" and dow.isdigit():
        result["sc"] = "WEEKLY"
        result["d"] = _WEEKDAY_NAMES.get(dow, "MON")
        return result
    if dom != "*" and dom.isdigit():
        result["sc"] = "MONTHLY"
        result["d"] = dom
        return result
    result["sc"] = "DAILY"
    return result


def cron_to_plist_interval(cron: str) -> list[dict]:
    parts = cron.split()
    minute, hour, dom, month, dow = parts
    m = int(minute) if minute.isdigit() else 0
    h = int(hour) if hour.isdigit() else 0

    entry: dict = {"Hour": h, "Minute": m}
    if dow != "*" and dow.isdigit():
        entry["Weekday"] = int(dow)
    if dom != "*" and dom.isdigit():
        entry["Day"] = int(dom)
    return [entry]


def _python_exe(project_dir: Path) -> str:
    if sys.platform == "win32":
        return str(project_dir / ".venv" / "Scripts" / "python.exe")
    return str(project_dir / ".venv" / "bin" / "python")


def install_windows(project_dir: Path, config: dict) -> bool:
    task_name = config["schedule"]["os_task_name"]
    cron = config["schedule"]["cron"]
    sched = cron_to_schtasks_schedule(cron)
    py = _python_exe(project_dir)
    run_script = str(project_dir / "src" / "run.py")
    tr = f'"{py}" "{run_script}"'

    cmd = ["schtasks", "/Create", "/TN", task_name, "/TR", tr, "/SC", sched["sc"]]
    if "st" in sched and sched["sc"] != "HOURLY":
        cmd += ["/ST", sched["st"]]
    if sched.get("d"):
        cmd += ["/D", sched["d"]]
    cmd += ["/F"]  # force overwrite

    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0


def install_macos(project_dir: Path, config: dict) -> bool:
    label = f"com.udd.{config['project']['name']}"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist = {
        "Label": label,
        "ProgramArguments": [_python_exe(project_dir), str(project_dir / "src" / "run.py")],
        "StartCalendarInterval": cron_to_plist_interval(config["schedule"]["cron"]),
        "StandardOutPath": str(project_dir / "logs" / "launchd.out"),
        "StandardErrorPath": str(project_dir / "logs" / "launchd.err"),
    }
    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    return r.returncode == 0


def install_linux(project_dir: Path, config: dict) -> bool:
    marker = f"UDD-{config['project']['name']}"
    cron_line = (
        f"{config['schedule']['cron']} "
        f"{_python_exe(project_dir)} {project_dir / 'src' / 'run.py'} "
        f"# {marker}"
    )

    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = [l for l in (existing.stdout or "").split("\n") if marker not in l]
    lines.append(cron_line)
    new_cron = "\n".join(l for l in lines if l) + "\n"

    r = subprocess.run(["crontab", "-"], input=new_cron, text=True, capture_output=True)
    return r.returncode == 0


def install(project_dir: Path) -> bool:
    config = yaml.safe_load((project_dir / "config.yaml").read_text(encoding="utf-8"))
    os_name = detect_os()
    if os_name == "windows":
        return install_windows(project_dir, config)
    if os_name == "macos":
        return install_macos(project_dir, config)
    if os_name == "linux":
        return install_linux(project_dir, config)
    raise RuntimeError(f"Unsupported OS: {os_name}")


def uninstall(project_dir: Path) -> bool:
    config = yaml.safe_load((project_dir / "config.yaml").read_text(encoding="utf-8"))
    os_name = detect_os()
    task_name = config["schedule"]["os_task_name"]

    if os_name == "windows":
        r = subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True)
        return r.returncode == 0
    if os_name == "macos":
        label = f"com.udd.{config['project']['name']}"
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        if plist_path.exists():
            plist_path.unlink()
        return True
    if os_name == "linux":
        marker = f"UDD-{config['project']['name']}"
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [l for l in (existing.stdout or "").split("\n") if marker not in l]
        new_cron = "\n".join(l for l in lines if l) + "\n"
        r = subprocess.run(["crontab", "-"], input=new_cron, text=True, capture_output=True)
        return r.returncode == 0
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    if args.uninstall:
        ok = uninstall(args.project_dir.resolve())
    else:
        ok = install(args.project_dir.resolve())

    print(json.dumps({"ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
