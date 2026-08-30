#!/usr/bin/env python3
"""公開情報から地域別イベントを取得し、events.js を生成する。

使い方:
    python3 tools/fetch_events.py --region tokyo
    python3 tools/fetch_events.py --region yokohama --days 21
    python3 tools/fetch_events.py --region osaka --dry-run

取得は sources/base.py の2秒間隔・12時間キャッシュ・明示User-Agentを共通利用する。
"""
import argparse
import csv
import datetime
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from region_config import REGIONS  # noqa: E402
from sources import (  # noqa: E402
    annual, ariake, base, bigsight, dome, forum, garden_theater, k_arena,
    kabukiza, kyocera_dome, medical_society, national_stadium, nntt, nougakudo,
    npb, osaka_johall, takarazuka, weather, yokohama_arena, yoyogi, zepp,
)

ROOT = Path(__file__).resolve().parent.parent
JST = datetime.timezone(datetime.timedelta(hours=9))


def date_range(days):
    """GitHub ActionsがUTCでもずれない、日本時間基準の日付範囲を返す。"""
    today = datetime.datetime.now(JST).date()
    return [today + datetime.timedelta(days=i) for i in range(days)]


def load_manual_csv(path):
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8-sig") as file_obj:
        for row in csv.DictReader(file_obj):
            row = {key.strip(): (value or "").strip() for key, value in row.items() if key}
            if not row.get("date") or not row.get("name"):
                continue
            events.append({
                "date": row["date"],
                "name": row["name"],
                "venue": row.get("venue", ""),
                "category": row.get("category", "concert"),
                "start": row.get("start", "18:00"),
                "end": row.get("end", "21:00"),
                "attendance": int(row["attendance"]) if str(row.get("attendance", "")).isdigit() else 5000,
                "audience": row.get("audience", "general"),
                "notes": row.get("notes", ""),
                "source": "手動CSV",
            })
    return events


def stable_event_id(region, event):
    """取得順が変わっても同じイベントに同じIDを割り当てる。"""
    identity = "|".join(str(value).strip() for value in (
        region, event.get("date"), event.get("venue"), event.get("name"), event.get("start"),
    ))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{region}-{digest}"


class Collector:
    def __init__(self):
        self.events = []
        self.errors = []
        self.fetch_stats = []

    def add(self, source_name, label, callback):
        try:
            got = callback()
            print(f"[{source_name}] {len(got)}件（{label}）")
            self.fetch_stats.append({"source": source_name, "count": len(got)})
            self.events += got
        except Exception as exc:  # 1ソース障害でも他ソースと公開を継続する
            self.errors.append(f"[{source_name}] {exc}")


def collect_sources(region, wanted, dates, pages):
    collector = Collector()
    months = sorted({(date.year, date.month) for date in dates})
    weekend_dates = {date.isoformat() for date in dates if date.weekday() >= 5}

    if "npb" in wanted:
        for year, month in months:
            collector.add(
                "npb", f"{region}・{year}-{month:02d}",
                lambda year=year, month=month: npb.fetch(year, month, weekend_dates, region=region),
            )
    if "bigsight" in wanted:
        collector.add("bigsight", "東京ビッグサイト", lambda: bigsight.fetch(pages=pages))
    if "dome" in wanted:
        collector.add("dome", "東京ドーム・野球以外", dome.fetch)
    if "ariake" in wanted:
        collector.add("ariake", "有明アリーナ", ariake.fetch)
    if "zepp" in wanted:
        collector.add("zepp", f"{REGIONS[region]['label']}のZepp", lambda: zepp.fetch(region=region))
    if "garden_theater" in wanted:
        collector.add("garden_theater", "東京ガーデンシアター", garden_theater.fetch)
    if "nntt" in wanted:
        collector.add("nntt", "新国立劇場", nntt.fetch)
    if "kabukiza" in wanted:
        collector.add("kabukiza", "歌舞伎座", kabukiza.fetch)
    if "national_stadium" in wanted:
        collector.add("national_stadium", "国立競技場", national_stadium.fetch)
    if "medical_society" in wanted:
        collector.add("medical_society", "都内学術集会", medical_society.fetch)
    if "nougakudo" in wanted:
        collector.add("nougakudo", "国立能楽堂", nougakudo.fetch)
    if "yoyogi" in wanted:
        collector.add("yoyogi", "国立代々木競技場 第一体育館", yoyogi.fetch)
    if "takarazuka" in wanted:
        collector.add("takarazuka", "東京宝塚劇場", takarazuka.fetch)
    if "annual" in wanted:
        collector.add("annual", "東京年次マスタ", lambda: annual.fetch(days_ahead=len(dates)))
    if "forum" in wanted:
        collector.add("forum", "東京国際フォーラム", lambda: forum.fetch(days_ahead=len(dates)))
    if "k_arena" in wanted:
        collector.add("k_arena", "Kアリーナ横浜", lambda: k_arena.fetch(months))
    if "yokohama_arena" in wanted:
        collector.add("yokohama_arena", "横浜アリーナ", lambda: yokohama_arena.fetch(months))
    if "kyocera_dome" in wanted:
        collector.add("kyocera_dome", "京セラドーム大阪・野球以外", lambda: kyocera_dome.fetch(months))
    if "osaka_johall" in wanted:
        collector.add("osaka_johall", "大阪城ホール", osaka_johall.fetch)
    return collector


def normalize_events(region, raw_events, dates):
    date_set = {date.isoformat() for date in dates}
    # 手動CSVを優先し、同日・同会場・同名を二重計上しない。
    raw_events.sort(key=lambda event: 0 if event.get("source") == "手動CSV" else 1)
    seen = set()
    events = []
    for event in raw_events:
        if event.get("date") not in date_set:
            continue
        key = (event.get("date"), event.get("venue"), event.get("name"))
        if key in seen:
            continue
        seen.add(key)
        event["id"] = stable_event_id(region, event)
        events.append(event)
    return sorted(events, key=lambda event: (event["date"], event["start"], event["venue"]))


def parse_args():
    parser = argparse.ArgumentParser(description="地域別イベント自動取得 → events.js 生成")
    parser.add_argument("--region", choices=REGIONS, default="tokyo", help="対象地域（既定: tokyo）")
    parser.add_argument("--days", type=int, default=14, help="今日から何日分を対象にするか（既定14）")
    parser.add_argument("--pages", type=int, default=3, help="ビッグサイト一覧の取得ページ数（既定3）")
    parser.add_argument("--sources", help="地域既定値を上書きするソース名（カンマ区切り）")
    parser.add_argument("--offline", action="store_true", help="通信せずキャッシュのみ使う")
    parser.add_argument("--dry-run", action="store_true", help="events.jsを書かずに結果表示のみ")
    return parser.parse_args()


def main():
    args = parse_args()
    config = REGIONS[args.region]
    if args.days < 1:
        raise SystemExit("--days は1以上を指定してください")

    base.OFFLINE = args.offline
    if args.offline:
        base.CACHE_MAX_AGE_HOURS = 24 * 365 * 100

    wanted = set(args.sources.split(",")) if args.sources else set(config["sources"])
    dates = date_range(args.days)
    collector = collect_sources(args.region, wanted, dates, args.pages)
    manual_path = ROOT / config["manual_csv"]
    manual = load_manual_csv(manual_path)
    if manual:
        print(f"[manual] {manual_path.name}: {len(manual)}件")
        collector.events += manual
    events = normalize_events(args.region, collector.events, dates)

    print(f"\n地域: {config['label']} / 対象期間: {dates[0]} 〜 {dates[-1]} / 採用 {len(events)}件")
    for error in collector.errors:
        print("警告:", error)
    if args.dry_run:
        for event in events:
            print(f"  {event['date']} {event['start']}-{event['end']} [{event['category']:<10}] "
                  f"{event['venue']:<12} {event['name'][:40]} ({event['attendance']:,}人, {event['source']})")
        return

    try:
        wx = weather.fetch(config["weather_area_code"])
        print(f"[weather] {len(wx)}日分（気象庁・{config['weather_label']}）")
    except Exception as exc:
        wx = {}
        collector.errors.append(f"[weather] {exc}")
        print(f"警告: [weather] {exc}")
    sources = sorted({event["source"] for event in events})
    payload = {
        "generated_at": datetime.datetime.now(JST).isoformat(timespec="seconds"),
        "region": args.region,
        "source": "自動取得: " + " + ".join(sources) if sources else "データなし",
        "events": events,
        "weather": wx,
        "fetch_stats": collector.fetch_stats,
        "errors": collector.errors,
    }
    output_path = ROOT / config["output"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "// このファイルは自動生成。直接編集せず tools/fetch_events.py で再生成する\n"
        "window.TAXI_APP_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n"
    )
    output_path.write_text(script, encoding="utf-8")
    print(f"書き出し完了 -> {output_path}")
    if not events:
        print("注意: 採用0件です。--dry-run で取得状況を確認してください。")


if __name__ == "__main__":
    main()
