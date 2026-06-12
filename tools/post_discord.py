#!/usr/bin/env python3
"""data/events.js から「本日の重点」を作って Discord に投稿する。

GitHub Actions から毎朝実行される想定。
環境変数 DISCORD_WEBHOOK_URL が未設定なら何もせず正常終了する。

環境変数:
    DISCORD_WEBHOOK_URL  DiscordチャンネルのウェブフックURL（必須。なければスキップ）
    FORECAB_URL          サイトURL（あれば末尾にリンクを付ける）
"""
import datetime
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources.base import _ssl_context  # noqa: E402  (macOSローカル実行時のSSL対策を共用)

EVENTS_JS = Path(__file__).resolve().parent.parent / "data" / "events.js"
JST = datetime.timezone(datetime.timedelta(hours=9))

# 順位付け用の簡易重み（app.jsのスコアの軽量版。正確なスコアと星はサイト側で表示される）
AUDIENCE_W = {"senior_wealthy": 1.5, "business": 1.4, "general": 1.0, "family": 0.9, "youth": 0.75}
CATEGORY_W = {"exhibition": 1.25, "theater": 1.05, "concert": 1.0, "sports": 0.9, "festival": 0.8}
CATEGORY_LABEL = {"exhibition": "展示会", "concert": "ライブ", "sports": "スポーツ",
                  "theater": "舞台", "festival": "催事"}


def load_events():
    txt = EVENTS_JS.read_text(encoding="utf-8")
    return json.loads(txt.split("=", 1)[1].rstrip().rstrip(";"))


def priority(ev):
    att = max(int(ev.get("attendance", 1)), 1)
    late = 1.15 if int(ev["end"].split(":")[0]) >= 21 else 1.0
    return (math.log10(att)
            * AUDIENCE_W.get(ev.get("audience"), 1.0)
            * CATEGORY_W.get(ev.get("category"), 1.0)
            * late)


def aim_text(ev):
    """app.js の aimText と同じ語彙の簡易版"""
    h, m = map(int, ev["end"].split(":"))
    end_min = h * 60 + m

    def fmt(t):
        return f"{(t // 60) % 24:02d}:{t % 60:02d}"

    if ev["category"] == "exhibition":
        return f"常時流入 ／ ピーク {fmt(end_min - 60)}–{fmt(end_min + 30)}"
    if ev["category"] == "festival":
        return f"引け際需要 {fmt(end_min - 30)}–{fmt(end_min + 60)}"
    return f"終演後需要 {fmt(end_min - 15)}–{fmt(end_min + 75)}"


def build_message():
    data = load_events()
    today = datetime.datetime.now(JST).date()
    label = f"{today.month}/{today.day}（{'月火水木金土日'[today.weekday()]}）"
    todays = [e for e in data.get("events", []) if e.get("date") == today.isoformat()]

    lines = [f"🚕 **FORECAB — {label} の重点**"]
    if not todays:
        lines.append("本日の登録イベントはありません。")
    else:
        top = sorted(todays, key=priority, reverse=True)[:3]
        for i, e in enumerate(top, 1):
            cat = CATEGORY_LABEL.get(e.get("category"), "")
            lines.append(f"**{i}. {e['name']}**")
            lines.append(f"　{e['venue']} ／ {cat} {e['start']}–{e['end']} ／ 約{int(e['attendance']):,}人")
            lines.append(f"　{aim_text(e)}")
        rest = len(todays) - len(top)
        if rest > 0:
            lines.append(f"ほか{rest}件。")

    site = os.environ.get("FORECAB_URL", "").strip()
    if site:
        lines.append(f"詳細・あす以降 → {site}")
    return "\n".join(lines)


def main():
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        print("DISCORD_WEBHOOK_URL が未設定のため投稿をスキップしました")
        return

    payload = json.dumps({"content": build_message()}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "FORECAB/0.1"},
    )
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as res:
        print(f"Discordへ投稿しました (HTTP {res.status})")


if __name__ == "__main__":
    main()
