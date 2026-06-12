"""東京ドーム公式のイベントスケジュールから、野球以外の催し（コンサート等）を取得する。

ページ: https://www.tokyo-dome.co.jp/dome/event/schedule.html
        1ページに当月から数ヶ月分のカレンダーが含まれる。
構造:   「2026年06月」見出し → <tr class="c-mod-calender__item"> が1日分。
        タグ（野球/コンサート/イベント）、イベント名リンク、「開場 15:00／開演 17:00」。

野球はNPBソースと重複するためここではスキップする。
"""
import re

from .base import http_get, guess_audience, make_event

SCHEDULE_URL = "https://www.tokyo-dome.co.jp/dome/event/schedule.html"

MONTH_RE = re.compile(r"(\d{4})年(\d{2})月")
DAY_RE = re.compile(r'c-mod-calender__day">(\d{1,2})<')
TAG_RE = re.compile(r"c-txt-tag__item[^>]*>([^<]+)<")
NAME_RE = re.compile(r"c-mod-calender__links.*?<a[^>]*>([^<]+)</a>", re.S)
KAIEN_RE = re.compile(r"開演\s*(\d{1,2}):(\d{2})")
KAIJO_RE = re.compile(r"開場\s*(\d{1,2}):(\d{2})")

# 東京ドームのコンサートはアリーナ構成でおおむね4万人超
ATTENDANCE = {"コンサート": 45000, "イベント": 30000}
CATEGORY = {"コンサート": "concert", "イベント": "festival"}
DURATION_MIN = {"コンサート": 210, "イベント": 180}  # 開演からの想定所要


def _fmt(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fetch():
    """東京ドームの野球以外のイベントを正規化イベントのリストで返す"""
    html = http_get(SCHEDULE_URL)

    events = []
    # 月見出しで分割（先頭は前置きなので捨てる）。splitの結果は [前置き, y1, m1, 本文1, y2, m2, 本文2, ...]
    parts = MONTH_RE.split(html)
    for i in range(1, len(parts) - 2, 3):
        year, month, body = int(parts[i]), int(parts[i + 1]), parts[i + 2]
        if not (1 <= month <= 12):
            continue
        for block in re.split(r'<tr class="c-mod-calender__item">', body)[1:]:
            dm = DAY_RE.search(block)
            nm = NAME_RE.search(block)
            if not dm or not nm:
                continue
            tag = (TAG_RE.search(block) or [None, "イベント"])[1].strip()
            if tag == "野球":
                continue  # NPBソースで取得済み

            name = " ".join(nm.group(1).split())
            km = KAIEN_RE.search(block)
            jm = KAIJO_RE.search(block)
            if km:
                start_min = int(km.group(1)) * 60 + int(km.group(2))
            elif jm:
                start_min = int(jm.group(1)) * 60 + int(jm.group(2)) + 60
            else:
                start_min = 17 * 60

            events.append(make_event(
                date=f"{year}-{month:02d}-{int(dm.group(1)):02d}",
                name=name,
                venue="東京ドーム",
                category=CATEGORY.get(tag, "festival"),
                start=_fmt(start_min),
                end=_fmt(start_min + DURATION_MIN.get(tag, 180)),
                attendance=ATTENDANCE.get(tag, 30000),
                audience=guess_audience(name, "youth" if tag == "コンサート" else "general"),
                notes=f"種別: {tag}。終了時刻は開演からの推定",
                source="tokyo-dome.co.jp",
            ))
    return events
