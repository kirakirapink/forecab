"""東京ガーデンシアター公式スケジュールから公演情報を取得する。

ページ: https://www.shopping-sumitomo-rd.com/tokyo_garden_theater/schedule/
構造:   サーバーレンダリング。li.event_all に開催日（単日または期間）、
        ジャンル、出演者、公演名が掲載される。開演時刻は一覧にないため、
        有明アリーナと同じく18:00-21:00で仮置きする。

robots.txt: /tokyo_garden_theater/wp-content/uploads/ のみ禁止。上記スケジュール
ページはクロール可（確認日: 2026-07-03）。
"""
import datetime
import html as html_lib
import re

from .base import http_get, make_event, strip_tags

URL = "https://www.shopping-sumitomo-rd.com/tokyo_garden_theater/schedule/"

ITEM_SPLIT_RE = re.compile(r'<li class="event_all[^"]*">')
YMD_RE = re.compile(
    r'<div class="ymd">\s*<div class="m">(\d{1,2})</div>\s*'
    r'<div class="d">(\d{1,2})</div>',
    re.S,
)
TAG_RE = re.compile(r'<div class="tag">(.*?)</div>', re.S)
PLAYER_RE = re.compile(r'<div class="player"[^>]*>(.*?)</div>', re.S)
TITLE_RE = re.compile(r'<div class="title"[^>]*>(.*?)</div>', re.S)
ACTIVE_MONTH_RE = re.compile(r'date=(\d{4})-(\d{2})#nav"[^>]*>\s*<span>\1</span>\s*<span><span>\2</span>')

ATTENDANCE = 7000


def _clean(fragment):
    text = strip_tags(fragment)
    text = html_lib.unescape(text)
    return " ".join(text.split())


def _base_year_for_page(html, today):
    m = ACTIVE_MONTH_RE.search(html)
    if m:
        return int(m.group(1)), int(m.group(2))
    return today.year, today.month


def _infer_year(month, today, page_year, page_month):
    if month == page_month:
        return page_year
    if page_month == 12 and month == 1:
        return page_year + 1
    if page_month == 1 and month == 12:
        return page_year - 1
    if abs(month - page_month) <= 6:
        return page_year
    return today.year + (1 if month < today.month - 6 else 0)


def _expand_dates(date_pairs, today, page_year, page_month):
    start_month, start_day = date_pairs[0]
    if len(date_pairs) >= 2:
        end_month, end_day = date_pairs[-1]
    else:
        end_month, end_day = start_month, start_day

    start = datetime.date(_infer_year(start_month, today, page_year, page_month), start_month, start_day)
    end = datetime.date(_infer_year(end_month, today, page_year, page_month), end_month, end_day)
    if end < start:
        end = datetime.date(end.year + 1, end.month, end.day)
    if (end - start).days > 14:
        end = start
    return [(start + datetime.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def _event_name(player, title):
    if player and title and title not in player:
        return f"{player} {title}"
    return title or player


def fetch():
    """東京ガーデンシアターのイベントを正規化イベントのリストで返す。"""
    html = http_get(URL)
    today = datetime.date.today()
    page_year, page_month = _base_year_for_page(html, today)

    events = []
    seen = set()
    for block in ITEM_SPLIT_RE.split(html)[1:]:
        block = block.split("</li>", 1)[0]
        date_pairs = [(int(m), int(d)) for m, d in YMD_RE.findall(block)]
        tag = _clean((TAG_RE.search(block) or [None, ""])[1])
        player = _clean(PLAYER_RE.search(block).group(1)) if PLAYER_RE.search(block) else ""
        title = _clean(TITLE_RE.search(block).group(1)) if TITLE_RE.search(block) else ""
        name = _event_name(player, title)
        if not date_pairs or not name:
            continue

        category = "sports" if "スポーツ" in tag else "concert"
        for date in _expand_dates(date_pairs, today, page_year, page_month):
            key = (date, name)
            if key in seen:
                continue
            seen.add(key)
            events.append(make_event(
                date=date,
                name=name,
                venue="東京ガーデンシアター",
                category=category,
                start="18:00",
                end="21:00",
                attendance=ATTENDANCE,
                audience="youth",
                notes=f"ジャンル: {tag or '不明'}。開演時刻は一覧に未掲載のため18:00と仮置き",
                source="shopping-sumitomo-rd.com/tokyo_garden_theater",
            ))
    return events
