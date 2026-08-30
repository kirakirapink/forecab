"""京セラドーム大阪公式スケジュールから野球以外のイベントを取得する。

ページ: https://www.kyoceradome-osaka.jp/schedule/?yearId=2026&monthId=08
野球はNPB公式から別取得するため除外。robots.txtは404で明示規定なし
（確認日: 2026-08-29）。公開ページのみを共通キャッシュ・間隔制御で取得する。
"""
import html as html_lib
import re

from .base import guess_audience, http_get, make_event, strip_tags

URL = "https://www.kyoceradome-osaka.jp/schedule/?yearId={year}&monthId={month:02d}"
DURATION_MIN = 180


def _clean(value):
    return " ".join(html_lib.unescape(strip_tags(value or "")).split())


def _fmt(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_page(html):
    events = []
    # re.splitのキャプチャにより year/month/day/content の4要素単位になる。
    parts = re.split(r'<section class="event-box[^\"]*"\s+id="event(\d{4})-(\d{2})-(\d{2})">', html)
    for index in range(1, len(parts), 4):
        if index + 3 >= len(parts):
            break
        year, month, day, block = parts[index:index + 4]
        block = block.split('</section>', 1)[0]
        top = block.split('</div>', 1)[0]
        kind_match = re.search(r'<span>(.*?)</span>', top, re.S)
        kind = _clean(kind_match.group(1)) if kind_match else ""
        if "野球" in kind:
            continue
        titles = [_clean(value) for value in re.findall(r'<h[12][^>]*>(.*?)</h[12]>', top, re.S)]
        titles = [value for value in titles if value]
        if not titles:
            continue
        name = titles[0]
        if len(titles) > 1 and titles[1] not in name:
            name = f"{name} {titles[1]}"
        if "非公開" in name:
            continue
        start_match = re.search(r'開始時間：\s*(\d{1,2}):(\d{2})', block)
        if not start_match:
            continue
        start_min = int(start_match.group(1)) * 60 + int(start_match.group(2))
        category = "concert" if "コンサート" in kind else "festival"
        events.append(make_event(
            date=f"{year}-{month}-{day}",
            name=name,
            venue="京セラドーム大阪",
            category=category,
            start=_fmt(start_min),
            end=_fmt(start_min + DURATION_MIN),
            attendance=45000 if category == "concert" else 30000,
            audience=guess_audience(name, "general"),
            notes="終了時刻はドームイベントの標準3時間で推定",
            source="kyoceradome-osaka.jp",
        ))
    return events


def fetch(months):
    events = []
    for year, month in months:
        events += _parse_page(http_get(URL.format(year=year, month=month)))
    return events
