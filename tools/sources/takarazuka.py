"""東京宝塚劇場の公演案内から日次イベントを取得する。

ページ: https://kageki.hankyu.co.jp/revue/index.html
構造:   宝塚大劇場・東京宝塚劇場の各公演ブロックが静的HTMLで並ぶ。
        東京宝塚劇場の公演期間だけを抽出し、標準休演日の月曜を除外して展開する。
"""
import datetime
import html as html_lib
import re

from .base import http_get, make_event, strip_tags

URL = "https://kageki.hankyu.co.jp/revue/index.html"
VENUE = "東京宝塚劇場"
ATTENDANCE = 2000

ITEM_SPLIT_RE = re.compile(r"(?=<div class=\"item\b)")
UNIT_ICON_RE = re.compile(r'<div class="unit_info icon ([^"]+)"')
TITLE_RE = re.compile(r'<h2[^>]*itemprop="summary"[^>]*>(.*?)</h2>', re.S)
TOKYO_RANGE_RE = re.compile(
    r"東京宝塚劇場.*?(\d{4})年(\d{1,2})月(\d{1,2})日（[^）]+）〜"
    r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日（[^）]+）",
    re.S,
)

TROUPE_BY_ICON = {
    "icon_flower": "花組",
    "icon_moon": "月組",
    "icon_snow": "雪組",
    "icon_star": "星組",
    "icon_cosmos": "宙組",
}


def _clean(fragment):
    text = html_lib.unescape(strip_tags(fragment))
    return " ".join(text.split())


def _troupe(block):
    m = UNIT_ICON_RE.search(block)
    if not m:
        return ""
    classes = set(m.group(1).split())
    for cls, troupe in TROUPE_BY_ICON.items():
        if cls in classes:
            return troupe
    return ""


def _title(block):
    m = TITLE_RE.search(block)
    if not m:
        return ""
    title = _clean(m.group(1))
    return title.split("』", 1)[0] + "』" if "』" in title else title


def _tokyo_range(block):
    m = TOKYO_RANGE_RE.search(block)
    if not m:
        return None
    sy, sm, sd, ey, em, ed = m.groups()
    start = datetime.date(int(sy), int(sm), int(sd))
    end_year = int(ey) if ey else start.year
    end_month = int(em)
    if not ey and end_month < start.month:
        end_year += 1
    end = datetime.date(end_year, end_month, int(ed))
    return start, end


def _expand_dates(start, end):
    for i in range((end - start).days + 1):
        day = start + datetime.timedelta(days=i)
        if day.weekday() == 0:
            continue
        yield day


def fetch():
    """東京宝塚劇場の公演を正規化イベントのリストで返す。"""
    html = http_get(URL)
    events = []
    seen = set()

    for block in ITEM_SPLIT_RE.split(html):
        if not block.startswith('<div class="item'):
            continue
        troupe = _troupe(block)
        title = _title(block)
        date_range = _tokyo_range(block)
        if not troupe or not title or not date_range:
            continue
        name = f"{troupe}{title}"
        for day in _expand_dates(*date_range):
            key = (day.isoformat(), name)
            if key in seen:
                continue
            seen.add(key)
            events.append(make_event(
                date=day.isoformat(),
                name=name,
                venue=VENUE,
                category="theater",
                start="15:30",
                end="18:30",
                attendance=ATTENDANCE,
                audience="senior_wealthy",
                notes="土日は11時回あり。月曜は標準休演日として除外",
                source="kageki.hankyu.co.jp/revue",
            ))
    return events
