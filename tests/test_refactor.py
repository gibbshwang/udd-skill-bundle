from pathlib import Path
from unittest.mock import patch

from refactor import build_prompt, apply_refactor_result


def test_build_prompt_contains_recording():
    recording = 'page.goto("https://x.com")\npage.click("text=통계")\n'
    config = {"project": {"url": "https://x.com"}, "validation": {"expected_columns": ["날짜"]}}
    prompt = build_prompt(recording, config)
    assert recording in prompt
    assert "selectors_yaml" in prompt
    assert "navigate_py" in prompt


def test_apply_refactor_result_writes_files(tmp_path):
    project = tmp_path / "p"
    (project / "src").mkdir(parents=True)
    (project / "selectors.yaml").write_text("# empty\n", encoding="utf-8")

    result = {
        "selectors_yaml": """
login_page:
  description: "로그인 페이지"
  primary: "text=로그인"
  fallbacks: ["id=login-btn"]
  ai_discovered: []
""",
        "navigate_py": '''
from playwright.sync_api import Page
def steps(page: Page, config: dict) -> None:
    from navigate import find
    find(page, "login_page").click()
''',
        "config_patches": {"filters": {"start_date": "{today-7d}"}},
    }
    apply_refactor_result(project, result)

    selectors = (project / "selectors.yaml").read_text(encoding="utf-8")
    assert "login_page" in selectors

    # navigate.py should have the steps() function appended
    nav = (project / "src" / "navigate.py").read_text(encoding="utf-8") if (project / "src" / "navigate.py").exists() else ""
    assert "def steps" in nav


def test_prompt_uses_single_braces_not_double():
    """Guards against .replace() vs .format() confusion — plan had {{/}} which
    would be sent literally to the LLM. After fix, prompt must use single braces."""
    config = {"project": {"url": "x"}, "validation": {"expected_columns": ["날짜"]}}
    prompt = build_prompt("page.goto('x')\n", config)
    # Template variables are single-brace
    assert "{today}" in prompt
    assert "{{today}}" not in prompt
    # JSON shape uses single brace
    assert '{{' not in prompt  # no double braces anywhere
    assert '}}' not in prompt
