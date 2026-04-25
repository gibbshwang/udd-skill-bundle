from schedule_install import cron_to_schtasks_schedule, cron_to_plist_interval, extract_start_time


def test_cron_daily():
    s = cron_to_schtasks_schedule("0 9 * * *")
    assert s["sc"] == "DAILY"
    assert s["st"] == "09:00"


def test_cron_weekly_monday():
    s = cron_to_schtasks_schedule("30 8 * * 1")
    assert s["sc"] == "WEEKLY"
    assert s["d"] == "MON"
    assert s["st"] == "08:30"


def test_cron_hourly():
    s = cron_to_schtasks_schedule("0 * * * *")
    assert s["sc"] == "HOURLY"


def test_extract_start_time():
    assert extract_start_time("0 9 * * *") == "09:00"
    assert extract_start_time("30 14 * * *") == "14:30"


def test_cron_to_plist_daily():
    p = cron_to_plist_interval("0 9 * * *")
    assert p == [{"Hour": 9, "Minute": 0}]


def test_cron_to_plist_weekly():
    p = cron_to_plist_interval("0 9 * * 1")
    assert p == [{"Weekday": 1, "Hour": 9, "Minute": 0}]
