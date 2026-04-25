import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def test_full_stage_0_1_2_renders_tree(tmp_path):
    project_dir = tmp_path / "erp-sales"

    # Stage 1
    stdin_data = "erp-sales\nhttps://erp.company.com\nTest desc\n매일 09:00\n날짜,매출\n"
    r = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "scope.py"),
         str(project_dir), "--from-stdin"],
        input=stdin_data, text=True, capture_output=True,
    )
    assert r.returncode == 0, r.stderr
    assert (project_dir / "config.yaml").exists()

    # Stage 2 (no install, no git to keep test fast)
    r = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "scaffold.py"),
         str(project_dir), "--skill-dir", str(SKILL_DIR),
         "--no-install", "--no-git"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    # Check key files rendered (note: src/*.py.tmpl and tests/*.py.tmpl
    # are added in later waves; this test is tolerant about missing ones)
    assert (project_dir / "pyproject.toml").exists()
    assert (project_dir / "README.md").exists()
    assert (project_dir / ".gitignore").exists()
    assert "erp-sales" in (project_dir / "pyproject.toml").read_text()
    assert (project_dir / "downloads").is_dir()
    assert (project_dir / "auth").is_dir()
