"""大阪城ホール公式イベント一覧を取得する。

ページ: https://www.osaka-johall.com/event/
構造: サーバーレンダリングされたカードに日付、タイトル、開演・終演を掲載。
robots.txtは404で明示規定なし（確認日: 2026-08-29）。公開ページのみを
共通キャッシュ・間隔制御で取得する。
"""
import html as html_lib
import re

from .base import guess_audience, http_get, make_event, strip_tags

URL = "https://www.osaka-johall.com/event/"
DURATION_MIN = 180


def _clean(value):
    return " ".join(html_lib.unescape(strip_tags(value or "")).split())


def _fmt(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _detail_values(block, label):
    pattern = rf'<span class="d-ttl">\s*{label}\s*</span>\s*<span class="d-txt">(.*?)</span>'
    match = re.search(pattern, block, re.S)
    if not match:
        return []
    return [value.strip() for value in _clean(match.group(1)).split("/") if value.strip()]


def _parse_page(html):
    events = []
    for block in re.split(r'<div class="slider-contents">', html)[1:]:
        block = block.split('<div class="slider-contents">', 1)[0]
        date_match = re.search(r'<span class="date">\s*(\d{4})/(\d{2})/(\d{2})\s*</span>', block)
        title_match = re.search(r'<dt class="event-ttl">(.*?)</dt>', block, re.S)
        if not date_match or not title_match:
            continue
        name = _clean(title_match.group(1))
        starts = _detail_values(block, "開演")
        ends = _detail_values(block, "終演")
        if not name or not starts:
            continue
        for index, start in enumerate(starts):
            match = re.match(r'(\d{1,2}):(\d{2})', start)
            if not match:
                continue
            start_min = int(match.group(1)) * 60 + int(match.group(2))
            end = ends[index] if index < len(ends) and re.match(r'^\d{1,2}:\d{2}$', ends[index]) else _fmt(start_min + DURATION_MIN)
            event_name = name if len(starts) == 1 else f"{name}（{index + 1}回目）"
            events.append(make_event(
                date=f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}",
                name=event_name,
                venue="大阪城ホール",
                category="concert",
                start=_fmt(start_min),
                end=end,
                attendance=16000,
                audience=guess_audience(event_name, "general"),
                notes="" if index < len(ends) else "終了時刻は大型ホール公演の標準3時間で推定",
                source="osaka-johall.com",
            ))
    return events


def fetch():
    return _parse_page(http_get(URL))
