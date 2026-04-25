"""Stage 2 — scaffold a project from templates.

Separate concerns:
  - `render_all_templates`: pure file rendering (testable without venv)
  - `install_dependencies`: heavy side-effect (venv + pip), called from main()
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.template_render import render_file

import yaml


TEMPLATE_SRC_FILES = [
    "__init__.py",
    "run.py",
    "auth.py",
    "navigate.py",
    "download.py",
    "validators.py",
    "healer.py",
    "llm_client.py",
    "notify.py",
    "cli.py",
]

TEMPLATE_TEST_FILES = [
    "test_validators.py",
    "test_selectors.py",
    "test_healer_mock.py",
]

TEMPLATE_ROOT_FILES = [
    "pyproject.toml",
    "requirements.txt",
    ".gitignore",
    "README.md",
    "config.yaml",
    "selectors.yaml",
]


def render_all_templates(skill_dir: Path, project_dir: Path, vars: dict[str, str]) -> None:
    """Copy every .tmpl from skill bundle into project_dir with substitutions."""
    tmpl_dir = skill_dir / "templates"

    for fname in TEMPLATE_ROOT_FILES:
        if fname == "config.yaml" and (project_dir / "config.yaml").exists():
            # scope.py writes the authoritative config, including user intake
            # values. Rendering config.yaml.tmpl here would silently erase
            # that state, which makes the pipeline impossible to audit.
            continue
        src = tmpl_dir / f"{fname}.tmpl"
        if src.exists():
            render_file(src, project_dir / fname, vars)

    for fname in TEMPLATE_SRC_FILES:
        src = tmpl_dir / "src" / f"{fname}.tmpl"
        if src.exists():
            render_file(src, project_dir / "src" / fname, vars)

    for fname in TEMPLATE_TEST_FILES:
        src = tmpl_dir / "tests" / f"{fname}.tmpl"
        if src.exists():
            render_file(src, project_dir / "tests" / fname, vars)


def create_directories(project_dir: Path) -> None:
    for sub in ("src", "tests", "auth", "downloads", "logs", "recordings"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)


def install_dependencies(project_dir: Path) -> None:
    """Create venv and install dependencies. Heavy — real network I/O."""
    venv_dir = project_dir / ".venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    py = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run([str(py), "-m", "pip", "install", "-U", "pip"], check=True)
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(project_dir / "requirements.txt")], check=True)
    subprocess.run([str(py), "-m", "playwright", "install", "chromium"], check=True)


def git_init(project_dir: Path) -> None:
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "scaffold ax-udd project", "--allow-empty"],
        cwd=project_dir, check=True, capture_output=True,
    )


def vars_from_config(project_dir: Path) -> dict[str, str]:
    cfg_path = project_dir / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError("config.yaml missing — run Stage 1 (scope.py) first")
    with cfg_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    name = cfg["project"]["name"]
    return {
        "project_name": name,
        "project_name_upper": name.upper(),
        "url": cfg["project"]["url"],
        "description": cfg["project"]["description"],
        "cron": cfg["schedule"]["cron"],
        "today": dt.date.today().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--skill-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--no-install", action="store_true",
                        help="Skip venv + pip + playwright install (for testing)")
    parser.add_argument("--no-git", action="store_true", help="Skip git init")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    vars_map = vars_from_config(project_dir)

    create_directories(project_dir)
    render_all_templates(args.skill_dir, project_dir, vars_map)
    # Overwrite config.yaml with the fully-formed one from scope.py (don't re-render)
    # config.yaml.tmpl rendering was just a fallback; scope.py version is richer.

    if not args.no_install:
        install_dependencies(project_dir)
    if not args.no_git:
        git_init(project_dir)

    print(f"Scaffolded {project_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
