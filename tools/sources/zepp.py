"""Zepp公式スケジュールから都内2館の公演を取得する。

ページ: https://www.zepp.co.jp/hall/haneda/schedule/
        https://www.zepp.co.jp/hall/divercity/schedule/
構造:   サーバーレンダリング。公演カードに日付、出演者、公演名、
        OPEN/START 時刻が掲載される。

robots.txt: /wp-admin/ のみ禁止。上記スケジュールページはクロール可
（確認日: 2026-07-03）。
"""
import html as html_lib
import re

from .base import http_get, make_event, strip_tags

HALLS = [
    {
        "url": "https://www.zepp.co.jp/hall/haneda/schedule/",
        "venue": "Zepp Haneda",
        "attendance": 2900,
    },
    {
        "url": "https://www.zepp.co.jp/hall/divercity/schedule/",
        "venue": "Zepp DiverCity",
        "attendance": 2400,
    },
]

DURATION_MIN = 150

YEAR_RE = re.compile(r'sch-content-date__year">\s*(\d{4})\s*<')
MONTH_DAY_RE = re.compile(r'sch-content-date__month">\s*(\d{1,2})\.(\d{1,2})\s*<')
PERFORMER_RE = re.compile(r'<h2 class="sch-content-text__performer">(.*?)</h2>', re.S)
TITLE_RE = re.compile(r'<h3 class="sch-content-text__ttl">(.*?)</h3>', re.S)
OPEN_RE = re.compile(r'sch-content-text-date__open">\s*(\d{1,2}):(\d{2})\s*<')
START_RE = re.compile(r'sch-content-text-date__start">\s*(\d{1,2}):(\d{2})\s*<')


def _clean(fragment):
    text = strip_tags(fragment)
    text = html_lib.unescape(text)
    return " ".join(text.split())


def _fmt(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _event_name(performer, title):
    if performer and title and title not in performer:
        return f"{performer} {title}"
    return title or performer


def _parse_page(html, venue, attendance):
    events = []
    seen = set()

    for block in re.split(r'<a class="sch-content[^"]*"', html)[1:]:
        block = block.split("</a>", 1)[0]
        ym = YEAR_RE.search(block)
        mdm = MONTH_DAY_RE.search(block)
        pm = PERFORMER_RE.search(block)
        tm = TITLE_RE.search(block)
        starts = START_RE.findall(block)
        if not ym or not mdm or not starts or (not pm and not tm):
            continue

        year = int(ym.group(1))
        month = int(mdm.group(1))
        day = int(mdm.group(2))
        performer = _clean(pm.group(1)) if pm else ""
        title = _clean(tm.group(1)) if tm else ""
        base_name = _event_name(performer, title)
        if not base_name:
            continue

        opens = [f"{int(h):02d}:{m}" for h, m in OPEN_RE.findall(block)]
        for i, (hour, minute) in enumerate(starts, start=1):
            start_min = int(hour) * 60 + int(minute)
            name = base_name if len(starts) == 1 else f"{base_name}（{i}回目）"
            key = (year, month, day, name, start_min)
            if key in seen:
                continue
            seen.add(key)
            open_time = opens[i - 1] if i <= len(opens) else ""
            notes = "終了時刻はライブハウス標準の2時間30分で推定"
            if open_time:
                notes = f"OPEN {open_time}。{notes}"
            events.append(make_event(
                date=f"{year}-{month:02d}-{day:02d}",
                name=name,
                venue=venue,
                category="concert",
                start=_fmt(start_min),
                end=_fmt(start_min + DURATION_MIN),
                attendance=attendance,
                audience="youth",
                notes=notes,
                source="zepp.co.jp",
            ))
    return events


def fetch():
    """Zepp Haneda / Zepp DiverCity のイベントを正規化イベントのリストで返す。"""
    events = []
    for hall in HALLS:
        html = http_get(hall["url"])
        events += _parse_page(html, hall["venue"], hall["attendance"])
    return events
