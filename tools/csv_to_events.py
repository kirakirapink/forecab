#!/usr/bin/env python3
"""CSVファイルからアプリ用イベントデータ (data/events.js) を生成する。

イベント情報をExcel/スプレッドシートで管理し、CSV書き出ししたものを取り込む想定。

使い方:
    python3 tools/csv_to_events.py data/events.csv

CSVの列（1行目はヘッダー。data/events_template.csv 参照）:
    date       : 2026-06-15 形式
    name       : イベント名
    venue      : 会場名（web/venues.js のキーと一致させると精度が上がる。未登録会場も可）
    category   : exhibition / concert / sports / theater / festival
    start      : 開始時刻 10:00 形式
    end        : 終了時刻 18:00 形式
    attendance : 推定来場者数（数字のみ）
    audience   : business / general / youth / family / senior_wealthy
    notes      : メモ（任意）
"""
import csv
import json
import re
import sys
import datetime
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "events.js"

VALID_CATEGORIES = {"exhibition", "concert", "sports", "theater", "festival"}
VALID_AUDIENCES = {"business", "general", "youth", "family", "senior_wealthy"}
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(row, lineno, errors):
    if not DATE_RE.match(row.get("date", "")):
        errors.append(f"{lineno}行目: date が不正です ({row.get('date')!r}) 例: 2026-06-15")
    for col in ("start", "end"):
        if not TIME_RE.match(row.get(col, "")):
            errors.append(f"{lineno}行目: {col} が不正です ({row.get(col)!r}) 例: 18:30")
    if row.get("category") not in VALID_CATEGORIES:
        errors.append(f"{lineno}行目: category は {sorted(VALID_CATEGORIES)} のいずれか")
    if row.get("audience") not in VALID_AUDIENCES:
        errors.append(f"{lineno}行目: audience は {sorted(VALID_AUDIENCES)} のいずれか")
    if not str(row.get("attendance", "")).isdigit():
        errors.append(f"{lineno}行目: attendance は数字のみ ({row.get('attendance')!r})")
    if not row.get("name"):
        errors.append(f"{lineno}行目: name が空です")
    if not row.get("venue"):
        errors.append(f"{lineno}行目: venue が空です")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    if not src.exists():
        print(f"エラー: ファイルが見つかりません: {src}")
        sys.exit(1)

    events = []
    errors = []
    with src.open(encoding="utf-8-sig") as f:  # Excel書き出しのBOM対策
        reader = csv.DictReader(f)
        for lineno, row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if not any(row.values()):
                continue
            validate(row, lineno, errors)
            events.append({
                "id": f"csv-{lineno:03d}",
                "date": row.get("date", ""),
                "name": row.get("name", ""),
                "venue": row.get("venue", ""),
                "category": row.get("category", ""),
                "start": row.get("start", ""),
                "end": row.get("end", ""),
                "attendance": int(row["attendance"]) if str(row.get("attendance", "")).isdigit() else 0,
                "audience": row.get("audience", ""),
                "notes": row.get("notes", ""),
            })

    if errors:
        print("CSVにエラーがあります。修正してから再実行してください:")
        for e in errors:
            print("  -", e)
        sys.exit(1)

    events.sort(key=lambda e: (e["date"], e["start"]))
    payload = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": str(src.name),
        "events": events,
    }
    js = (
        "// このファイルは自動生成。直接編集せず tools/csv_to_events.py で再生成する\n"
        "window.TAXI_APP_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n"
    )
    OUT_PATH.write_text(js, encoding="utf-8")
    print(f"OK: {len(events)}件のイベントを書き出しました -> {OUT_PATH}")


if __name__ == "__main__":
    main()
