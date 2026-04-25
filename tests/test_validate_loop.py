from validate_loop import classify_error, apply_diagnosis


def test_classify_timeout():
    assert classify_error("TimeoutError: locator.wait_for(...)") == "selector"


def test_classify_element_not_found():
    assert classify_error("ElementNotFoundError: all fallbacks failed for x") == "selector"


def test_classify_validation():
    assert classify_error("ValidationError: missing columns: ['X']") == "validation"


def test_classify_unknown():
    assert classify_error("SomethingElse: boom") == "logic"


def test_apply_diagnosis_selector_patch(tmp_path):
    sel_path = tmp_path / "selectors.yaml"
    sel_path.write_text("foo:\n  description: x\n  primary: \"#old\"\n  fallbacks: []\n  ai_discovered: []\n")

    diag = {"type": "selector", "element": "foo", "new_selector": "#new",
            "reasoning": "dom changed"}
    apply_diagnosis(tmp_path, diag)

    import yaml
    data = yaml.safe_load(sel_path.read_text())
    assert any(ai["selector"] == "#new" for ai in data["foo"]["ai_discovered"])
