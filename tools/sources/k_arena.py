"""Kアリーナ横浜の公式公演スケジュールを取得する。

ページ: https://k-arena.com/schedule/?y=2026&m=9
構造:   サーバーレンダリングされた公演カードに日付、題名、出演者、OPEN/STARTを掲載。
robots.txt: 全ページ取得可（確認日: 2026-08-29）。
"""
import html as html_lib
import re

from .base import http_get, make_event, strip_tags

URL = "https://k-arena.com/schedule/?y={year}&m={month}"
DURATION_MIN = 180


def _clean(value):
    return " ".join(html_lib.unescape(strip_tags(value or "")).split())


def _fmt(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_page(html):
    events = []
    for block in re.split(r'<li class="schedule-list-item[^\"]*">', html)[1:]:
        block = block.split('</li>', 1)[0]
        date_match = re.search(r'schedule-list-item__date">\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\.', block)
        title_match = re.search(r'schedule-list-item__title">(.*?)</h2>', block, re.S)
        start_match = re.search(r'START\s*(\d{1,2}):(\d{2})', block, re.I)
        if not date_match or not title_match or not start_match:
            continue
        artist_match = re.search(r'schedule-list-item__artist">(.*?)</p>', block, re.S)
        open_match = re.search(r'OPEN\s*(\d{1,2}):(\d{2})', block, re.I)
        title = _clean(title_match.group(1))
        artist = _clean(artist_match.group(1)) if artist_match else ""
        name = title if not artist or artist in title else f"{title} — {artist}"
        start_min = int(start_match.group(1)) * 60 + int(start_match.group(2))
        notes = "終了時刻は大型アリーナ公演の標準3時間で推定"
        if open_match:
            notes = f"OPEN {int(open_match.group(1)):02d}:{open_match.group(2)}。{notes}"
        events.append(make_event(
            date=f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}",
            name=name,
            venue="Kアリーナ横浜",
            category="concert",
            start=_fmt(start_min),
            end=_fmt(start_min + DURATION_MIN),
            attendance=20000,
            audience="youth",
            notes=notes,
            source="k-arena.com",
        ))
    return events


def fetch(months):
    """``[(year, month), ...]`` に該当する公式公演を返す。"""
    events = []
    for year, month in months:
        events += _parse_page(http_get(URL.format(year=year, month=month)))
    return events
