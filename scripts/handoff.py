"""Stage 9 — print the final summary."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import yaml


TEMPLATE = """
✅ AX Universal Data Downloader 생성 완료

📁 프로젝트: {project_dir}
⏰ 다음 실행: {next_run} ({cron_human})
📊 예상 파일: {project_dir}/downloads/YYYY-MM-DD/*.{fmt}
🔔 알림: {telegram_status}
🩹 Self-healing: {healing_status}

운영 명령:
  udd status             최근 실행 결과
  udd doctor             환경 진단
  udd login              세션 재로그인 (만료 시)
  udd retrain            UI 변경 시 재학습
  udd run                즉시 1회 실행
  udd unschedule         스케줄 제거
"""


def _next_run(cron: str) -> str:
    parts = cron.split()
    minute, hour = parts[0], parts[1]
    h = int(hour) if hour.isdigit() else 0
    m = int(minute) if minute.isdigit() else 0
    now = dt.datetime.now()
    today_run = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if today_run <= now:
        today_run += dt.timedelta(days=1)
    return today_run.strftime("%Y-%m-%d %H:%M")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    config = yaml.safe_load((project_dir / "config.yaml").read_text(encoding="utf-8"))

    summary = TEMPLATE.format(
        project_dir=project_dir,
        next_run=_next_run(config["schedule"]["cron"]),
        cron_human=config["schedule"]["cron"],
        fmt=config["download"]["expected_format"],
        telegram_status="텔레그램" if config["notify"]["telegram"].get("enabled") else "(비활성)",
        healing_status="활성" if config["healing"].get("enabled") else "(비활성)",
    )
    print(summary)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
