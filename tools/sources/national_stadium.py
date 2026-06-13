"""国立競技場 (MUFG Stadium) の公式イベントから催しを取得する。

ページ: https://jns-e.com/event/page/YYYYMM/ （月別）
構造:   各イベントは <div class="p-event-list__wrapper"> でラップされ、
        <p class="sport">/<p class="music"> でカテゴリ、
        <p class="p-event-list__head"> でタイトル、
        <span class="day-wrapper"> 内に <span class="year"> + <span class="date"> で日付（連日は複数並ぶ）、
        <dd>開場HH:MM 開演HH:MM</dd> や <dd>HH:MM キックオフ</dd> で開始時刻。

ペルソナ的位置付け:
  5万人規模＋規制退場の最大級会場。1件あたりのインパクトが圧倒的。
  - 代表戦/Jリーグ大一番/天皇杯決勝 → P1経営層・P3専門職の接待観戦、一般、P10インバウンド
  - 大型ライブ → P7中高年ライブ（往年アーティスト時）または若年層（アイドル系時）
"""
import datetime
import re

from .base import http_get, guess_audience, make_event, SourceError

URL_FMT = "https://jns-e.com/event/page/{year}{month:02d}/"

WRAPPER_SPLIT = re.compile(r'<div class="p-event-list__wrapper">')
CAT_RE = re.compile(r'<p class="(sport|music)">.*?<span>([^<]+)</span>', re.S)
TITLE_RE = re.compile(r'<p class="p-event-list__head">([^<]+)</p>')
DATE_RE = re.compile(
    r'<span class="year">(\d{4})</span>\s*<span class="date">(\d{1,2})/(\d{1,2})</span>'
)
START_DD_RE = re.compile(r"<dt>開始時間</dt>\s*<dd>([^<]+)</dd>")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

CATEGORY_LABEL = {"sport": "スポーツ", "music": "音楽"}
APP_CATEGORY = {"sport": "sports", "music": "concert"}
ATTENDANCE = {"sport": 45000, "music": 50000}
DURATION_MIN = {"sport": 150, "music": 180}
DEFAULT_START_MIN = {"sport": 14 * 60, "music": 18 * 60}  # 未掲載時のフォールバック


def _fmt_time(minutes):
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _pick_start(text, cat_key):
    """「開場15:30 開演17:30」「14:00 キックオフ」等から開始時刻を抽出"""
    if not text:
        return DEFAULT_START_MIN[cat_key]
    # 開演/キックオフが付く時刻を優先
    for pat in (r"開演\s*(\d{1,2}):(\d{2})", r"(\d{1,2}):(\d{2})\s*開演",
                r"(\d{1,2}):(\d{2})\s*キックオフ", r"キックオフ\s*(\d{1,2}):(\d{2})"):
        m = re.search(pat, text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
    # 複数時刻なら最後（「開場HH:MM 開演HH:MM」で開演を取るため）。1つしかなければそれ
    matches = list(TIME_RE.finditer(text))
    if matches:
        m = matches[-1]
        return int(m.group(1)) * 60 + int(m.group(2))
    return DEFAULT_START_MIN[cat_key]


def _fetch_month(year, month):
    """指定月の月別ページからイベントを抽出"""
    try:
        html = http_get(URL_FMT.format(year=year, month=month))
    except SourceError:
        return []
    if "予定はありません" in html:
        return []

    events = []
    for block in WRAPPER_SPLIT.split(html)[1:]:
        # ブロックの終端: 次の <a> または </a></li> までを切り出す
        block = re.split(r"</a></li>", block, maxsplit=1)[0]

        cm = CAT_RE.search(block)
        tm = TITLE_RE.search(block)
        if not cm or not tm:
            continue
        cat_key = cm.group(1)  # 'sport' / 'music'
        title = " ".join(re.sub(r"&quot;", '"', tm.group(1)).split())[:120]
        if not title:
            continue

        # 日付（連日は複数マッチ）
        dates = []
        for dm in DATE_RE.finditer(block):
            try:
                dates.append(datetime.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3))))
            except ValueError:
                pass
        if not dates:
            continue

        sm = START_DD_RE.search(block)
        start_min = _pick_start(sm.group(1) if sm else "", cat_key)
        end_min = start_min + DURATION_MIN[cat_key]

        audience = guess_audience(title, "general")
        if cat_key == "sport" and any(w in title for w in ["代表", "決勝", "リーグワン", "天皇杯"]):
            audience = "business"

        for d in dates:
            events.append(make_event(
                date=d.isoformat(),
                name=title,
                venue="国立競技場",
                category=APP_CATEGORY[cat_key],
                start=_fmt_time(start_min),
                end=_fmt_time(end_min),
                attendance=ATTENDANCE[cat_key],
                audience=audience,
                notes=f"国立競技場5万人規模 ({CATEGORY_LABEL[cat_key]})。規制退場により需要は60-90分に分散。",
                source="jns-e.com",
            ))
    return events


def fetch(months_ahead=2):
    """国立競技場の今月＋翌月分のイベントを取得"""
    today = datetime.date.today()
    events, seen = [], set()
    for i in range(months_ahead):
        d = today.replace(day=1) + datetime.timedelta(days=32 * i)
        for ev in _fetch_month(d.year, d.month):
            key = (ev["date"], ev["name"])
            if key in seen:
                continue
            seen.add(key)
            events.append(ev)
    return events
