#!/usr/bin/env python3
"""本日の需要予報を「ラジオ原稿」にし、音声(m4a)とYouTube用動画(mp4)を生成する。

macOS専用（音声合成に標準の say コマンドを使用）。

使い方:
    python3 tools/make_radio.py              # 原稿 + 音声 + 動画を output/radio/ に生成
    python3 tools/make_radio.py --script-only   # 原稿テキストだけ生成（確認用)
    python3 tools/make_radio.py --date 2026-06-13  # 対象日を指定

生成物（output/radio/YYYY-MM-DD/）:
    script.txt           読み上げ原稿
    forecab_radio.m4a    音声（ポッドキャスト等にそのまま使える）
    forecab_radio.mp4    カバー画像つき動画（YouTube投稿用。ffmpegがある場合のみ）
"""
import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from post_discord import priority  # noqa: E402  (重点の順位付けを共用)
from make_icon import write_png, AMBER, BLACK, WHITE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVENTS_JS = ROOT / "data" / "events.js"
OUT_ROOT = ROOT / "output" / "radio"
JST = datetime.timezone(datetime.timedelta(hours=9))

VOICE = "Kyoko"      # macOS標準の日本語ボイス
RATE = 180           # 読み上げ速度（words/min相当。日本語はこのくらいが聞きやすい）

WEEKDAYS = ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"]

AUDIENCE_SPOKEN = {
    "business": "ビジネス客",
    "senior_wealthy": "年配の富裕層",
    "general": "一般のお客様",
    "youth": "若い世代",
    "family": "ファミリー層",
}

AUDIENCE_COMMENT = {
    "business": "タクシー利用率は高めです。",
    "senior_wealthy": "タクシー利用率はもっとも高い客層です。",
    "general": "規模で勝負の現場です。",
    "youth": "電車利用が中心のため、過度な期待は禁物です。",
    "family": "荷物や子ども連れの短距離需要が見込めます。",
}


def spoken_number(n):
    """28000 -> 「2万8000」のような読み上げ向き表記"""
    n = int(n)
    if n >= 10000:
        man, rest = divmod(n, 10000)
        return f"{man}万{rest if rest else ''}"
    return str(n)


def spoken_time(hhmm):
    """'16:30' -> 「16時30分」、'16:00' -> 「16時」"""
    h, m = map(int, hhmm.split(":"))
    return f"{h}時{f'{m}分' if m else ''}"


def shift(hhmm, minutes):
    h, m = map(int, hhmm.split(":"))
    t = h * 60 + m + minutes
    return f"{(t // 60) % 24:02d}:{t % 60:02d}"


def load_events(date_iso):
    data = json.loads(EVENTS_JS.read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    return [e for e in data.get("events", []) if e.get("date") == date_iso]


def event_paragraph(rank, ev):
    """重点イベント1件ぶんの読み上げ文"""
    cat = ev.get("category")
    aud = ev.get("audience")
    lines = [f"重点、{rank}件目。{ev['venue']}、「{ev['name']}」。"]
    if cat == "exhibition":
        lines.append(
            f"{spoken_time(ev['start'])}から{spoken_time(ev['end'])}まで、"
            f"規模はおよそ{spoken_number(ev['attendance'])}人。"
            f"{AUDIENCE_SPOKEN.get(aud, '')}が中心で、{AUDIENCE_COMMENT.get(aud, '')}"
        )
        lines.append(
            f"展示会のため終日出入りがあります。最大の山は、閉場前の"
            f"{spoken_time(shift(ev['end'], -60))}から{spoken_time(shift(ev['end'], 30))}ごろです。"
        )
    elif cat == "festival":
        lines.append(
            f"{spoken_time(ev['start'])}から{spoken_time(ev['end'])}まで、"
            f"およそ{spoken_number(ev['attendance'])}人規模。"
            f"引け際の{spoken_time(shift(ev['end'], -30))}以降が中心です。"
        )
    else:
        lines.append(
            f"{spoken_time(ev['start'])}開始、{spoken_time(ev['end'])}終了見込み、"
            f"およそ{spoken_number(ev['attendance'])}人。"
            f"{AUDIENCE_SPOKEN.get(aud, '')}が中心で、{AUDIENCE_COMMENT.get(aud, '')}"
        )
        lines.append(
            f"終演後、{spoken_time(shift(ev['end'], -15))}から"
            f"{spoken_time(shift(ev['end'], 75))}ごろまで需要が続く見込みです。"
        )
        if cat == "sports":
            lines.append("試合の進行次第で、終了時刻は前後します。")
    # notes はデータ管理用の表記（ホール番号等）が多く読み上げに不向きなため使わない
    return "".join(lines)


def build_script(date, events):
    label = f"{date.month}月{date.day}日、{WEEKDAYS[date.weekday()]}"
    p = [f"おはようございます。フォアキャブ・デイリー。{label}の、東京イベント需要予報です。"]

    if not events:
        p.append("本日把握しているイベントはありません。通常の流しを中心に、ご安全に。")
        p.append("以上、フォアキャブ・デイリーでした。")
        return "\n\n".join(p)

    top = sorted(events, key=priority, reverse=True)[:3]
    evenings = [e for e in events if int(e["end"].split(":")[0]) >= 20]
    p.append(
        f"本日、都内で把握しているイベントは{len(events)}件。"
        + (f"夜まで動きのある現場が{len(evenings)}件あります。" if evenings else "日中型の現場が中心です。")
    )

    for i, ev in enumerate(top, 1):
        p.append(event_paragraph(i, ev))

    others = [e for e in events if e not in top]
    if others:
        names = "、".join(f"{e['venue']}の「{e['name']}」" for e in others[:3])
        p.append(f"このほか、{names}{'、など' if len(others) > 3 else ''}があります。")

    # 時系列のまとめ（行動イメージ）
    closes = sorted(set(e["end"] for e in events))
    p.append(
        f"時間の流れとしては、最初の山が{spoken_time(shift(closes[0], -60))}ごろから、"
        f"最後の波は{spoken_time(closes[-1])}すぎまでです。"
        "詳しいスコアと星の評価は、フォアキャブのサイトで確認してください。"
    )
    p.append("以上、フォアキャブ・デイリーでした。本日もご安全に。")
    return "\n\n".join(p)


def make_cover(path, width=1280, height=720):
    """YouTube用カバー画像（市松バンド + 琥珀 + 円環）"""
    cell = 40
    band = cell * 2
    cx, cy = width / 2, height / 2
    rings = [(0.30, 0.26), (0.18, 0.14), (0.06, 0.0)]
    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            if y < band or y >= height - band:
                row.append(BLACK if ((x // cell) + (y // cell)) % 2 == 0 else WHITE)
                continue
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / height
            color = AMBER
            for outer, inner in rings:
                if inner <= d <= outer:
                    color = BLACK
                    break
            row.append(color)
        pixels.append(row)
    write_png(path, width, height, pixels)


def main():
    ap = argparse.ArgumentParser(description="本日の需要予報ラジオを生成")
    ap.add_argument("--date", help="対象日 YYYY-MM-DD（既定: 今日）")
    ap.add_argument("--script-only", action="store_true", help="原稿テキストのみ生成")
    args = ap.parse_args()

    date = (datetime.date.fromisoformat(args.date) if args.date
            else datetime.datetime.now(JST).date())
    events = load_events(date.isoformat())
    script = build_script(date, events)

    out_dir = OUT_ROOT / date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    script_path = out_dir / "script.txt"
    script_path.write_text(script, encoding="utf-8")
    print(f"原稿: {script_path}（{len(script)}文字、読み上げ約{len(script) // 300 + 1}分）")

    if args.script_only:
        return

    # 音声合成: say(AIFF) → afconvert(m4a)
    aiff = out_dir / "radio.aiff"
    m4a = out_dir / "forecab_radio.m4a"
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), "-f", str(script_path)], check=True)
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(aiff), str(m4a)],
                   check=True, capture_output=True)
    aiff.unlink()
    print(f"音声: {m4a}")

    # 動画化（ffmpegがあれば）: カバー静止画 + 音声 → mp4
    if shutil.which("ffmpeg"):
        cover = out_dir / "cover.png"
        if not cover.exists():
            make_cover(cover)
        mp4 = out_dir / "forecab_radio.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-loop", "1", "-i", str(cover), "-i", str(m4a),
             "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(mp4)],
            check=True,
        )
        print(f"動画: {mp4}（YouTube投稿用）")
    else:
        print("ffmpeg が見つからないため動画化はスキップ（brew install ffmpeg で有効化）")


if __name__ == "__main__":
    main()
