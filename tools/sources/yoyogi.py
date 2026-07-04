"""国立代々木競技場 第一体育館のイベント情報を取得する。

ページ: https://www.jpnsport.go.jp/yoyogi/event/tabid/59/Default.aspx
構造:   サーバーレンダリング。event-calendar テーブルに日付とイベント名の2列。
        掲載は当月・来月のみで、時刻情報は公開されない。

robots.txt: 上記ページはクロール可（確認日: 2026-07-04）。
時刻: 公開情報に開始/終了時刻がないため、アリーナ系ライブの夕方公演として
      17:00-20:30を仮置きする。詳細は公式公演ページで要確認。

メモ: 第二体育館（tabid/60）は将来候補。Issue #40 では対象外。
"""
import datetime
import re

from .base import http_get, make_event, strip_tags

URL = "https://www.jpnsport.go.jp/yoyogi/event/tabid/59/Default.aspx"
VENUE = "国立代々木競技場 第一体育館"
ATTENDANCE = 10000

ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
DATE_RE = re.compile(r"(?:(\d{4})/)?(\d{1,2})/(\d{1,2})")
SKIP_WORDS = ("準備", "設営", "リハーサル", "撤去", "搬入", "搬出", "仕込み")


def _clean(fragment):
    return " ".join(strip_tags(fragment).split())


def _infer_year(month, today):
    """当月+翌月だけが載る前提で月から年を決める。12月ページの1月を翌年にする。"""
    if month == today.month:
        return today.year
    next_month = 1 if today.month == 12 else today.month + 1
    if month == next_month:
        return today.year + (1 if today.month == 12 and month == 1 else 0)
    if today.month == 1 and month == 12:
        return today.year - 1
    return today.year + (1 if month < today.month else 0)


def _parse_date(text, today):
    m = DATE_RE.search(text)
    if not m:
        return None
    year_s, month_s, day_s = m.groups()
    month = int(month_s)
    day = int(day_s)
    year = int(year_s) if year_s else _infer_year(month, today)
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _parse_rows(html, today):
    seen = set()
    for row in ROW_RE.findall(html):
        cells = CELL_RE.findall(row)
        if len(cells) < 2:
            continue
        date = _parse_date(_clean(cells[0]), today)
        name = _clean(cells[1])
        if not date or not name or name == "イベントはありません。":
            continue
        if any(word in name for word in SKIP_WORDS):
            continue
        key = (date.isoformat(), name)
        if key in seen:
            continue
        seen.add(key)
        yield date.isoformat(), name


def fetch():
    """第一体育館のイベントを正規化イベントのリストで返す。"""
    html = http_get(URL)
    today = datetime.date.today()
    events = []
    for date, name in _parse_rows(html, today):
        events.append(make_event(
            date=date,
            name=name,
            venue=VENUE,
            category="concert",
            start="17:00",
            end="20:30",
            attendance=ATTENDANCE,
            audience="youth",
            notes="開始・終了時刻は未掲載のため17:00-20:30で仮置き。公式公演ページで要確認",
            source="jpnsport.go.jp/yoyogi",
        ))
    return events
