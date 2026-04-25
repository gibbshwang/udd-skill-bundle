from pathlib import Path
import sys

from scaffold import render_all_templates, TEMPLATE_SRC_FILES


def test_render_all_templates_copies_files(tmp_path, monkeypatch):
    # Build fake skill bundle dir with templates
    skill_dir = tmp_path / "skill"
    tmpl_dir = skill_dir / "templates"
    tmpl_dir.mkdir(parents=True)
    (tmpl_dir / "pyproject.toml.tmpl").write_text('name = "{{project_name}}"\n')
    (tmpl_dir / "README.md.tmpl").write_text("# {{project_name}}\n")
    (tmpl_dir / "config.yaml.tmpl").write_text("x: {{project_name}}\n")
    (tmpl_dir / "selectors.yaml.tmpl").write_text("# empty\n")
    (tmpl_dir / "requirements.txt.tmpl").write_text("playwright\n")
    (tmpl_dir / ".gitignore.tmpl").write_text("auth/\n")

    src_dir = tmpl_dir / "src"
    src_dir.mkdir()
    for fname in TEMPLATE_SRC_FILES:
        (src_dir / f"{fname}.tmpl").write_text(f"# {fname}\n")
    tests_dir = tmpl_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_validators.py.tmpl").write_text("# test\n")
    (tests_dir / "test_selectors.py.tmpl").write_text("# test\n")
    (tests_dir / "test_healer_mock.py.tmpl").write_text("# test\n")

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    render_all_templates(
        skill_dir=skill_dir,
        project_dir=project_dir,
        vars={
            "project_name": "erp-sales",
            "project_name_upper": "ERP-SALES",
            "url": "https://x.com",
            "description": "test",
            "cron": "0 9 * * *",
            "today": "2026-04-24",
        },
    )

    assert (project_dir / "pyproject.toml").exists()
    assert "erp-sales" in (project_dir / "pyproject.toml").read_text()
    assert (project_dir / "src" / "run.py").exists()
    assert (project_dir / "tests" / "test_validators.py").exists()
    assert (project_dir / ".gitignore").exists()
