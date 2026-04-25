"""Stage 7 — show user the latest download + wait for YES/NO."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from lib.telegram import send


def find_latest_download(project_dir: Path) -> Path | None:
    dl = project_dir / "downloads"
    if not dl.exists():
        return None
    for date_dir in sorted(dl.iterdir(), reverse=True):
        if date_dir.is_dir():
            files = [f for f in date_dir.iterdir() if f.is_file()]
            if files:
                # Return most recently modified file in the latest date dir
                return max(files, key=lambda p: p.stat().st_mtime)
    return None


_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1")


def _read_csv_multi_encoding(path: Path) -> pd.DataFrame:
    """Korean gov / enterprise CSVs are routinely cp949 / euc-kr — try each
    encoding in order before giving up. Mirrors the helper in
    templates/src/validators.py.tmpl so approve_flow and the user-project
    validator agree on what's readable.
    """
    last_err: Exception | None = None
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise UnicodeDecodeError(
        f"none of {_CSV_ENCODINGS} could decode {path.name!r}: {last_err}"
    )


def summarize_file(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        df = pd.read_excel(path)
    elif suffix == ".csv":
        df = _read_csv_multi_encoding(path)
    else:
        return {"path": str(path), "size_bytes": path.stat().st_size, "rows": None, "columns": None}
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "rows": len(df),
        "columns": list(df.columns),
        "sample": df.head(10).to_dict(orient="records"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    latest = find_latest_download(project_dir)
    if latest is None:
        print(json.dumps({"status": "no_file"}))
        return 1

    summary = summarize_file(latest)

    # Print human-readable to stderr (for skill to show)
    print(f"File: {summary['path']}", file=sys.stderr)
    print(f"Rows: {summary['rows']}, Columns: {summary['columns']}", file=sys.stderr)
    if "sample" in summary:
        for row in summary["sample"][:10]:
            print(row, file=sys.stderr)

    # Emit JSON to stdout for programmatic use
    print(json.dumps(summary, ensure_ascii=False, default=str))

    # Send telegram sample if configured
    config = yaml.safe_load((project_dir / "config.yaml").read_text(encoding="utf-8"))
    chat_id = config["notify"]["telegram"].get("chat_id")
    if chat_id:
        text = (f"📊 *{config['project']['name']}* 샘플\n"
                f"파일: `{latest.name}`\n"
                f"Rows: {summary['rows']}, Columns: {summary['columns']}")
        send(chat_id, text, files=[latest])

    return 0


if __name__ == "__main__":
    sys.exit(main())
