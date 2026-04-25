from pathlib import Path

from lib.template_render import render_string, render_file


def test_render_string_simple():
    out = render_string("Hello {{name}}!", {"name": "World"})
    assert out == "Hello World!"


def test_render_string_multiple():
    out = render_string("{{a}}+{{b}}={{c}}", {"a": "1", "b": "2", "c": "3"})
    assert out == "1+2=3"


def test_render_string_missing_var_raises():
    import pytest
    with pytest.raises(KeyError):
        render_string("{{missing}}", {})


def test_render_string_unchanged_without_vars():
    out = render_string("no placeholders here", {"unused": "x"})
    assert out == "no placeholders here"


def test_render_file_writes_output(tmp_path: Path):
    src = tmp_path / "in.tmpl"
    dst = tmp_path / "out.txt"
    src.write_text("Project: {{project}}\nURL: {{url}}\n")
    render_file(src, dst, {"project": "erp-sales", "url": "https://x.com"})
    assert dst.read_text() == "Project: erp-sales\nURL: https://x.com\n"


def test_render_file_creates_parent_dirs(tmp_path: Path):
    src = tmp_path / "in.tmpl"
    dst = tmp_path / "deep" / "nested" / "out.txt"
    src.write_text("x")
    render_file(src, dst, {})
    assert dst.exists()
