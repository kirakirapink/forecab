"""歌舞伎座（松竹公式「歌舞伎美人」）の興行情報を取得する。

ページ: https://www.kabuki-bito.jp/theaters/kabukiza/
構造:   1ページに今後数ヶ月の興行が「興行名 → 会期 → 部別開演時刻 → 休演日」の順に並ぶ。
        「公演詳細」がブロック境界として使える。

ペルソナ的位置付け:
  P6 年配富裕層を単独で強くカバー。1階桟敷席2万円帯の客層はタクシー利用率最高クラス。
  夜の部終演（21時前後）以降、東銀座→自宅住宅地への中距離需要が典型。
"""
import datetime
import re

from .base import http_get, strip_tags, make_event

URL = "https://www.kabuki-bito.jp/theaters/kabukiza/"

# 会期: 「2026年6月3日（水）～25日（木）」など
PERIOD_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日（[月火水木金土日]）\s*[～〜~]\s*"
    r"(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日（[月火水木金土日]）"
)

# 部別開演時刻: 「昼の部 午前11時～」「夜の部 午後4時30分～」
PART_RE = re.compile(
    r"(昼の部|夜の部|第一部|第二部|第三部|朝の部|宵の部)\s*(午前|午後)\s*(\d{1,2})時(?:\s*(\d{1,2})分)?\s*[～〜~]"
)

# 休演日: 「【休演】10日（水）、18日（木）」
CLOSED_RE = re.compile(r"【休演】([^※\n]{1,80})")
DAY_RE = re.compile(r"(\d{1,2})日")

# 部別の所要時間（分）。歌舞伎は昼/夜ともに約4時間
DURATION_MIN = {
    "昼の部": 240,
    "夜の部": 270,
    "第一部": 180,
    "第二部": 210,
    "第三部": 180,
    "朝の部": 180,
    "宵の部": 210,
}

# 部別の標準的な集客（歌舞伎座の客席は約1,808席、平日昼は7割、休日や話題作は満員）
ATTENDANCE = 1500


def _to_24h(period, hour, minute):
    """『午前11時30分』『午後4時30分』 → 分単位"""
    h = int(hour)
    m = int(minute or 0)
    if period == "午後" and h != 12:
        h += 12
    elif period == "午前" and h == 12:
        h = 0
    return h * 60 + m


def _fmt_time(minutes):
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _expand_period(m):
    """会期マッチを日付リストに展開"""
    y1, mo1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y2 = int(m.group(4)) if m.group(4) else y1
    mo2 = int(m.group(5)) if m.group(5) else mo1
    d2 = int(m.group(6))
    start = datetime.date(y1, mo1, d1)
    end = datetime.date(y2, mo2, d2)
    if end < start or (end - start).days > 60:
        return []
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def _closed_days(block, dates):
    """「【休演】10日（水）、18日（木）」を解析して上演日リストから除外"""
    closed = set()
    for cm in CLOSED_RE.finditer(block):
        for dm in DAY_RE.finditer(cm.group(1)):
            day = int(dm.group(1))
            for d in dates:
                if d.day == day:
                    closed.add(d)
    return [d for d in dates if d not in closed]


def fetch(days_ahead=45):
    """歌舞伎座の今後の興行を正規化イベントのリストで返す"""
    html = http_get(URL)
    text = strip_tags(html)

    # 「歌舞伎座 公演情報」以降を取得（メニュー部分を捨てる）
    idx = text.find("歌舞伎座 公演情報")
    if idx < 0:
        idx = text.find("公演情報")
    body = text[idx:] if idx >= 0 else text

    # 「公演詳細」を区切りとして1興行ごとのブロックに分ける
    blocks = body.split("公演詳細")

    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)

    events = []
    for block in blocks:
        pm = PERIOD_RE.search(block)
        if not pm:
            continue
        # 興行名: 期間表記直前から「○月大歌舞伎」等のパターンを拾う（最後のマッチが本番興行名）
        before = block[: pm.start()]
        candidates = re.findall(
            r"[一-龥ぁ-んァ-ヶ々〆]{1,15}(?:大歌舞伎|納涼歌舞伎|顔見世大歌舞伎|新春大歌舞伎|歌舞伎)",
            before,
        )
        # 「歌舞伎座」「興行歌舞伎」などのノイズを除外
        candidates = [c for c in candidates if c not in ("歌舞伎座", "歌舞伎") and "公演" not in c]
        title = candidates[-1] if candidates else "歌舞伎座公演"

        all_dates = _expand_period(pm)
        if not all_dates:
            continue
        dates = _closed_days(block, all_dates)

        # 部別開演時刻を取得
        parts = []
        for partm in PART_RE.finditer(block):
            part_name = partm.group(1)
            start_min = _to_24h(partm.group(2), partm.group(3), partm.group(4))
            parts.append((part_name, start_min))
        if not parts:
            continue

        for d in dates:
            if not (today <= d <= cutoff):
                continue
            for part_name, start_min in parts:
                duration = DURATION_MIN.get(part_name, 240)
                events.append(make_event(
                    date=d.isoformat(),
                    name=f"{title}（{part_name}）",
                    venue="歌舞伎座",
                    category="theater",
                    start=_fmt_time(start_min),
                    end=_fmt_time(start_min + duration),
                    attendance=ATTENDANCE,
                    audience="senior_wealthy",
                    notes=f"歌舞伎の{part_name}。観客約1,808席で年配富裕層中心。終演時刻は推定。",
                    source="kabuki-bito.jp",
                ))
    return events
