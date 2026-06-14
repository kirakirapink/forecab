#!/usr/bin/env python3
"""公開情報からイベントを自動取得して data/events.js を生成する。

使い方:
    python3 tools/fetch_events.py                  # 今日から14日分を取得して反映
    python3 tools/fetch_events.py --days 7        # 範囲を変える
    python3 tools/fetch_events.py --dry-run       # events.js を書かずに結果を表示
    python3 tools/fetch_events.py --offline       # 通信せずキャッシュのみで再生成

データソース（tools/sources/ 以下に1ファイル1ソース）:
    npb       NPB公式の月別日程（東京ドーム・明治神宮野球場の試合）
    bigsight  東京ビッグサイト公式のイベント一覧（展示会・催事）

さらに data/manual_events.csv があればマージする（ライブ・コンサート等、
自動取得できないイベントを手で足す用。列は data/events_template.csv と同じ）。

マナー: リクエスト間2秒・12時間キャッシュ・User-Agentに連絡先明示（sources/base.py）。
"""
import argparse
import csv
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources import base, npb, bigsight, dome, ariake, nntt, kabukiza, national_stadium, medical_society, nougakudo, annual, forum, weather  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "events.js"
MANUAL_CSV = ROOT / "data" / "manual_events.csv"

# GitHub Actions(UTC)で実行しても日付がズレないよう、日本時間で「今日」を決める
JST = datetime.timezone(datetime.timedelta(hours=9))


def date_range(days):
    today = datetime.datetime.now(JST).date()
    return [today + datetime.timedelta(days=i) for i in range(days)]


def load_manual_csv():
    if not MANUAL_CSV.exists():
        return []
    events = []
    with MANUAL_CSV.open(encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("date") or not row.get("name"):
                continue
            events.append({
                "date": row["date"], "name": row["name"], "venue": row.get("venue", ""),
                "category": row.get("category", "concert"), "start": row.get("start", "18:00"),
                "end": row.get("end", "21:00"),
                "attendance": int(row["attendance"]) if str(row.get("attendance", "")).isdigit() else 5000,
                "audience": row.get("audience", "general"), "notes": row.get("notes", ""),
                "source": "手動CSV",
            })
    return events


def main():
    ap = argparse.ArgumentParser(description="イベント自動取得 → data/events.js 生成")
    ap.add_argument("--days", type=int, default=14, help="今日から何日分を対象にするか（既定14）")
    ap.add_argument("--pages", type=int, default=3, help="ビッグサイト一覧の取得ページ数（既定3）")
    ap.add_argument("--sources", default="npb,bigsight,dome,ariake,nntt,kabukiza,national_stadium,medical_society,nougakudo,annual,forum", help="使うソース（カンマ区切り）")
    ap.add_argument("--offline", action="store_true", help="通信せずキャッシュのみ使う")
    ap.add_argument("--dry-run", action="store_true", help="events.js を書かずに結果表示のみ")
    args = ap.parse_args()

    base.OFFLINE = args.offline
    wanted = set(args.sources.split(","))
    dates = date_range(args.days)
    date_set = {d.isoformat() for d in dates}
    weekend_dates = {d.isoformat() for d in dates if d.weekday() >= 5}

    all_events = []
    errors = []

    if "npb" in wanted:
        months = sorted({(d.year, d.month) for d in dates})
        for year, month in months:
            try:
                got = npb.fetch(year, month, weekend_dates)
                print(f"[npb] {year}-{month:02d}: {len(got)}試合（都内球場）")
                all_events += got
            except base.SourceError as e:
                errors.append(f"[npb] {e}")

    if "bigsight" in wanted:
        try:
            got = bigsight.fetch(pages=args.pages)
            print(f"[bigsight] {len(got)}件（開催日ごとに展開済み）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[bigsight] {e}")

    if "dome" in wanted:
        try:
            got = dome.fetch()
            print(f"[dome] {len(got)}件（東京ドーム・野球以外）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[dome] {e}")

    if "ariake" in wanted:
        try:
            got = ariake.fetch()
            print(f"[ariake] {len(got)}件（有明アリーナ）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[ariake] {e}")

    if "nntt" in wanted:
        try:
            got = nntt.fetch()
            print(f"[nntt] {len(got)}件（新国立劇場：オペラ・バレエ・現代演劇）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[nntt] {e}")

    if "kabukiza" in wanted:
        try:
            got = kabukiza.fetch()
            print(f"[kabukiza] {len(got)}件（歌舞伎座）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[kabukiza] {e}")

    if "national_stadium" in wanted:
        try:
            got = national_stadium.fetch()
            print(f"[national_stadium] {len(got)}件（国立競技場）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[national_stadium] {e}")

    if "medical_society" in wanted:
        try:
            got = medical_society.fetch()
            print(f"[medical_society] {len(got)}件（日本医学会・都内学術集会）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[medical_society] {e}")

    if "nougakudo" in wanted:
        try:
            got = nougakudo.fetch()
            print(f"[nougakudo] {len(got)}件（国立能楽堂）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[nougakudo] {e}")

    if "annual" in wanted:
        try:
            got = annual.fetch(days_ahead=args.days)
            print(f"[annual] {len(got)}件（年次マスタ）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[annual] {e}")

    if "forum" in wanted:
        try:
            got = forum.fetch(days_ahead=args.days)
            print(f"[forum] {len(got)}件（東京国際フォーラム）")
            all_events += got
        except base.SourceError as e:
            errors.append(f"[forum] {e}")

    manual = load_manual_csv()
    if manual:
        print(f"[manual] {MANUAL_CSV.name}: {len(manual)}件")
        all_events += manual

    # 期間でフィルタし、(日付, 会場, 名前) で重複排除（手動CSVを優先したいので手動を先に）
    all_events.sort(key=lambda e: 0 if e.get("source") == "手動CSV" else 1)
    seen = set()
    events = []
    for ev in all_events:
        if ev["date"] not in date_set:
            continue
        key = (ev["date"], ev["venue"], ev["name"])
        if key in seen:
            continue
        seen.add(key)
        events.append(ev)

    events.sort(key=lambda e: (e["date"], e["start"]))
    for i, ev in enumerate(events, start=1):
        ev["id"] = f"auto-{i:03d}"

    print(f"\n対象期間: {dates[0]} 〜 {dates[-1]} / 採用 {len(events)}件")
    for e in errors:
        print("警告:", e)

    if args.dry_run:
        for ev in events:
            print(f"  {ev['date']} {ev['start']}-{ev['end']} [{ev['category']:<10}] "
                  f"{ev['venue']:<10} {ev['name'][:40]} ({ev['attendance']:,}人, {ev['source']})")
        return

    # 気象予報（東京地方）。失敗時は空dictで継続（app.js側でweather_factor=1.0）
    try:
        wx = weather.fetch()
        print(f"[weather] {len(wx)}日分（気象庁・東京地方）")
    except Exception as e:
        wx = {}
        print(f"警告: [weather] {e}")

    srcs = sorted({e["source"] for e in events})
    payload = {
        "generated_at": datetime.datetime.now(JST).isoformat(timespec="seconds"),
        "source": "自動取得: " + " + ".join(srcs) if srcs else "データなし",
        "events": events,
        "weather": wx,
    }
    js = (
        "// このファイルは自動生成。直接編集せず tools/fetch_events.py で再生成する\n"
        "window.TAXI_APP_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n"
    )
    OUT_PATH.write_text(js, encoding="utf-8")
    print(f"書き出し完了 -> {OUT_PATH}")
    if not events:
        print("注意: 採用0件です。--dry-run で取得状況を確認してください。")


if __name__ == "__main__":
    main()
