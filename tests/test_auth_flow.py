import pytest

from auth_flow import build_codegen_command, get_browser_channel


def test_build_codegen_command_save_storage(tmp_path):
    cmd = build_codegen_command(
        python_exe="/usr/bin/python3",
        mode="save",
        storage_path=tmp_path / "storage.json",
        url="https://example.com",
    )
    assert cmd[0] == "/usr/bin/python3"
    assert "-m" in cmd
    assert "playwright" in cmd
    assert "codegen" in cmd
    assert "--save-storage" in cmd
    assert str(tmp_path / "storage.json") in cmd
    assert "https://example.com" in cmd
    # save mode must NOT also write a recording
    assert "--output" not in cmd
    assert "--load-storage" not in cmd


def test_build_codegen_command_load_and_record(tmp_path):
    cmd = build_codegen_command(
        python_exe="/usr/bin/python3",
        mode="record",
        storage_path=tmp_path / "storage.json",
        url="https://example.com",
        output=tmp_path / "raw.py",
    )
    assert "--load-storage" in cmd
    assert "--output" in cmd
    assert str(tmp_path / "raw.py") in cmd
    assert "--target" in cmd
    assert "python" in cmd


def test_build_codegen_command_setup_combines_save_and_record(tmp_path):
    """First-time setup mode: single browser session that captures BOTH
    storage_state and a recording — replaces having to run save then record
    in two separate browser sessions."""
    storage = tmp_path / "storage.json"
    output = tmp_path / "raw_recording.py"
    cmd = build_codegen_command(
        python_exe="/usr/bin/python3",
        mode="setup",
        storage_path=storage,
        url="https://example.com",
        output=output,
    )
    assert "--save-storage" in cmd
    assert str(storage) in cmd
    assert "--output" in cmd
    assert str(output) in cmd
    # setup is fresh login, so no existing storage to load
    assert "--load-storage" not in cmd
    # url must be the final argument so playwright treats it as the launch URL
    assert cmd[-1] == "https://example.com"


def test_build_codegen_command_setup_requires_output(tmp_path):
    with pytest.raises(ValueError, match="setup requires output"):
        build_codegen_command(
            python_exe="/usr/bin/python3",
            mode="setup",
            storage_path=tmp_path / "storage.json",
            url="https://example.com",
            output=None,
        )


def test_build_codegen_command_passes_channel_when_set(tmp_path):
    """Anti-bot sites (some Korean gov portals) reject Playwright's bundled
    Chromium fingerprint. ``channel='chrome'`` switches to system Chrome."""
    cmd = build_codegen_command(
        python_exe="/usr/bin/python3",
        mode="save",
        storage_path=tmp_path / "storage.json",
        url="https://example.com",
        channel="chrome",
    )
    assert "--channel" in cmd
    chan_idx = cmd.index("--channel")
    assert cmd[chan_idx + 1] == "chrome"


def test_build_codegen_command_omits_channel_when_none(tmp_path):
    cmd = build_codegen_command(
        python_exe="/usr/bin/python3",
        mode="save",
        storage_path=tmp_path / "storage.json",
        url="https://example.com",
        channel=None,
    )
    assert "--channel" not in cmd


def test_get_browser_channel_returns_value():
    assert get_browser_channel({"auth": {"browser_channel": "chrome"}}) == "chrome"


def test_get_browser_channel_returns_none_when_unset():
    assert get_browser_channel({"auth": {}}) is None
    assert get_browser_channel({}) is None
    assert get_browser_channel({"auth": {"browser_channel": ""}}) is None
    assert get_browser_channel({"auth": {"browser_channel": None}}) is None
