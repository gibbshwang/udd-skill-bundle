from pathlib import Path

from scope import cron_from_natural_language, validate_slug, build_config


def test_validate_slug_accepts_kebab():
    validate_slug("erp-sales")  # no raise


def test_validate_slug_rejects_uppercase():
    import pytest
    with pytest.raises(ValueError):
        validate_slug("ERP-Sales")


def test_validate_slug_rejects_spaces():
    import pytest
    with pytest.raises(ValueError):
        validate_slug("erp sales")


def test_cron_from_natural_daily_9am():
    assert cron_from_natural_language("매일 09:00") == "0 9 * * *"
    assert cron_from_natural_language("매일 9시") == "0 9 * * *"
    assert cron_from_natural_language("daily at 09:00") == "0 9 * * *"


def test_cron_from_natural_already_cron():
    assert cron_from_natural_language("0 9 * * *") == "0 9 * * *"


def test_cron_from_natural_weekly_monday():
    assert cron_from_natural_language("매주 월요일 오전 9시") == "0 9 * * 1"


def test_build_config_structure():
    cfg = build_config(
        name="erp-sales",
        url="https://erp.company.com",
        description="ERP 매출 엑셀",
        cron="0 9 * * *",
        expected_columns=["날짜", "매출"],
    )
    assert cfg["project"]["name"] == "erp-sales"
    assert cfg["project"]["url"] == "https://erp.company.com"
    assert cfg["schedule"]["cron"] == "0 9 * * *"
    assert cfg["validation"]["expected_columns"] == ["날짜", "매출"]
    assert cfg["auth"]["mode"] == "session_replay"
    assert cfg["healing"]["enabled"] is True
    assert cfg["healing"]["ai_provider"] == "auto"
