from pathlib import Path
import pandas as pd

from approve_flow import find_latest_download, summarize_file


def test_find_latest_download(tmp_path):
    dl = tmp_path / "downloads"
    (dl / "2026-04-20").mkdir(parents=True)
    (dl / "2026-04-24").mkdir(parents=True)
    (dl / "2026-04-24" / "report.xlsx").write_bytes(b"PK\x03\x04")
    (dl / "2026-04-20" / "old.xlsx").write_bytes(b"PK\x03\x04")

    latest = find_latest_download(tmp_path)
    assert latest.name == "report.xlsx"


def test_find_latest_download_none(tmp_path):
    (tmp_path / "downloads").mkdir()
    assert find_latest_download(tmp_path) is None


def test_summarize_file_xlsx(tmp_path):
    p = tmp_path / "a.xlsx"
    pd.DataFrame({"날짜": ["2026-04-01"], "매출": [100]}).to_excel(p, index=False)
    summary = summarize_file(p)
    assert summary["rows"] == 1
    assert summary["columns"] == ["날짜", "매출"]
    assert summary["path"] == str(p)


def test_find_latest_download_picks_latest_in_date_dir(tmp_path):
    import time
    dl = tmp_path / "downloads"
    d = dl / "2026-04-24"
    d.mkdir(parents=True)
    older = d / "old.xlsx"
    older.write_bytes(b"PK\x03\x04")
    time.sleep(0.02)
    newer = d / "new.xlsx"
    newer.write_bytes(b"PK\x03\x04")
    assert find_latest_download(tmp_path).name == "new.xlsx"
