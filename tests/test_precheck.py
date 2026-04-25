from precheck import build_report


def test_build_report_all_good(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    report = build_report(
        python_version="3.11.5",
        playwright_version="1.48.0",
        chromium_installed=True,
        autonomous_mode=True,
    )
    assert report["status"] == "ok"
    assert report["python"] == "3.11.5"
    assert report["playwright"] == "1.48.0"
    assert report["chromium"] is True
    assert report["ai_providers"] == ["anthropic"]
    assert report["autonomous_mode"] is True


def test_build_report_missing_playwright(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = build_report(
        python_version="3.11.5",
        playwright_version=None,
        chromium_installed=False,
        autonomous_mode=False,
    )
    assert report["status"] == "missing"
    assert "playwright" in report["missing"]
    assert "chromium" in report["missing"]
    assert report["ai_providers"] == []


def test_build_report_python_too_old(monkeypatch):
    report = build_report(
        python_version="3.9.0",
        playwright_version="1.48.0",
        chromium_installed=True,
        autonomous_mode=True,
    )
    assert report["status"] == "error"
    assert "python>=3.10" in report["missing"]


def test_build_report_multiple_ai(monkeypatch, clear_ai_env):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    report = build_report("3.11.5", "1.48.0", True, True)
    assert set(report["ai_providers"]) == {"gemini", "openai"}
