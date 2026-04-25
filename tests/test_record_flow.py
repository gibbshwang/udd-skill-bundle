from pathlib import Path

from record_flow import validate_recording


def test_validate_recording_ok(tmp_path):
    rec = tmp_path / "raw.py"
    rec.write_text("""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(storage_state="auth/storage.json")
    page = context.new_page()
    page.goto("https://erp.example.com")
    page.get_by_text("다운로드").click()
    with page.expect_download() as dl:
        page.get_by_role("button", name="엑셀").click()
""", encoding="utf-8")
    assert validate_recording(rec) == (True, [])


def test_validate_recording_missing_file(tmp_path):
    rec = tmp_path / "missing.py"
    ok, issues = validate_recording(rec)
    assert ok is False
    assert any("not found" in i.lower() for i in issues)


def test_validate_recording_no_goto(tmp_path):
    rec = tmp_path / "raw.py"
    rec.write_text("# empty recording\n")
    ok, issues = validate_recording(rec)
    assert ok is False
    assert any("page.goto" in i for i in issues)
