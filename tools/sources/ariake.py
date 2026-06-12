"""有明アリーナ公式のイベントページから催しを取得する。

ページ: https://ariake-arena.tokyo/event/      （当月）
        https://ariake-arena.tokyo/event/next/  （翌月）
構造:   <li id=detail-NNN> が1イベント。日付は「6.6 SAT」形式（複数日あり）、
        イベント名は <div class="event_name"><p>…</p>。
        開演時刻は一覧に載らないことが多いため、既定18:00開演で扱いnotesに明記する。
"""
import datetime
import re

from .base import http_get, guess_audience, make_event

PAGE_URLS = [
    "https://ariake-arena.tokyo/event/",
    "https://ariake-arena.tokyo/event/next/",
]

ITEM_SPLIT_RE = re.compile(r"<li id=detail-\d+>")
DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\s+(?:MON|TUE|WED|THU|FRI|SAT|SUN)")
NAME_RE = re.compile(r'event_name">\s*<p>(.*?)</p>', re.S)

SPORTS_WORDS = ["バレーボール", "バスケットボール", "大会", "選手権", "リーグ", "卓球", "体操"]
DEFAULT_ATTENDANCE = 12000  # 満員約15,000人のアリーナ。コンサートの標準的な入り


def fetch():
    """有明アリーナのイベントを正規化イベントのリストで返す"""
    today = datetime.date.today()
    events = []
    seen = set()

    for url in PAGE_URLS:
        try:
            html = http_get(url)
        except Exception:
            continue
        for block in ITEM_SPLIT_RE.split(html)[1:]:
            block = block.split("</li>")[0]
            nm = NAME_RE.search(block)
            dates = DATE_RE.findall(block)
            if not nm or not dates:
                continue
            name = " ".join(re.sub(r"<[^>]+>", " ", nm.group(1)).split())
            if not name:
                continue

            category = "sports" if any(w in name for w in SPORTS_WORDS) else "concert"
            audience = guess_audience(name, "general")

            for mon, day, in [(int(m), int(d)) for m, d, in [(x[0], x[1]) for x in dates]]:
                # 年は実行日基準で推定（12月に1月のイベントを見たら翌年と判断）
                year = today.year + (1 if mon < today.month - 6 else 0)
                date = f"{year}-{mon:02d}-{day:02d}"
                key = (date, name)
                if key in seen:
                    continue
                seen.add(key)
                events.append(make_event(
                    date=date, name=name, venue="有明アリーナ",
                    category=category, start="18:00", end="21:00",
                    attendance=DEFAULT_ATTENDANCE, audience=audience,
                    notes="開演時刻は一覧に未掲載のため18:00と仮置き。公演サイトで要確認",
                    source="ariake-arena.tokyo",
                ))
    return events
