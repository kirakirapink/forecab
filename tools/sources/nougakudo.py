"""国立能楽堂の主催公演情報を取得する。

ページ: https://www.ntj.jac.go.jp/nou/
構造:   トップページの「国立能楽堂主催公演」セクションに、
        「ジャンル → 会場 → 日付 → 公演名」の繰り返しで主催公演が並ぶ。
        日付は「M月D日（曜）」または「M月D日（曜）～D日（曜）」形式。
        開演時刻は一覧に載らないため、公演種別から推定（定例13:00、能楽鑑賞教室14:30 等）。

ペルソナ的位置付け:
  P6 年配富裕層を強くカバー。能・狂言の観客は年配層が中心で
  千駄ヶ谷駅から徒歩7分とやや駅遠のため終演後タクシー需要が確実に立つ。
  歌舞伎座と同等のタクシー利用率（客層の所得・年齢が高い）。
"""
import datetime
import re

from .base import http_get, strip_tags, make_event

URL = "https://www.ntj.jac.go.jp/nou/"

# 「6月23日（火）～27日（土）」または「8月1日（水）」
DATE_RANGE_RE = re.compile(
    r"(\d{1,2})月(\d{1,2})日（[月火水木金土日]）"
    r"(?:\s*[～〜~]\s*(?:(\d{1,2})月)?(\d{1,2})日（[月火水木金土日]）)?"
)

# 公演種別ごとの標準開演時刻
START_BY_KIND = {
    "定例公演": "13:00",
    "普及公演": "13:00",
    "能楽鑑賞教室": "14:30",
    "親子": "13:00",
    "蝋燭": "18:00",
    "特別公演": "13:00",
    "企画公演": "13:00",
    "公演": "13:00",  # フォールバック
}

# 国立能楽堂の客席数（公称591席）
ATTENDANCE = 500   # 主催公演は通常満席に近く90%程度
DURATION_MIN = 150  # 能・狂言の標準的な所要時間


def _start_time(name):
    for kind, t in START_BY_KIND.items():
        if kind in name:
            return t
    return "13:00"


def _end_time(start):
    h, m = map(int, start.split(":"))
    end_min = h * 60 + m + DURATION_MIN
    return f"{(end_min // 60) % 24:02d}:{end_min % 60:02d}"


def _extract_performances(text):
    """主催公演セクションから公演を抽出。
    パターン:「能・狂言\n国立能楽堂\n6月23日（火）～27日（土）\n6月能楽鑑賞教室\n仏師／葵上\n詳細はこちら」
    """
    # 「主催公演」以降から「お知らせ」「アクセス」等の終端マーカーまで
    start = text.find("主催公演")
    if start < 0:
        return []
    end = len(text)
    for marker in ["お知らせ", "アクセス", "施設案内", "国立能楽堂について"]:
        m = text.find(marker, start + 100)
        if 0 < m < end:
            end = m
    body = text[start:end]

    today = datetime.date.today()
    # この時点で年を推定: 表示順は通常今日付近の月から始まる。
    # トップページに載るのは概ね「今月〜3ヶ月先」。月を見て年を決める
    base_year = today.year
    results = []
    seen = set()
    for m in DATE_RANGE_RE.finditer(body):
        m1, d1 = int(m.group(1)), int(m.group(2))
        m2 = int(m.group(3)) if m.group(3) else m1
        d2 = int(m.group(4)) if m.group(4) else d1

        # 年推定: 今月より前の月 = 来年扱い（12月→1月の年越し対応）
        year1 = base_year + (1 if m1 < today.month - 1 else 0)
        year2 = base_year + (1 if m2 < today.month - 1 else 0)
        try:
            start_d = datetime.date(year1, m1, d1)
            end_d = datetime.date(year2, m2, d2)
        except ValueError:
            continue
        if end_d < start_d or (end_d - start_d).days > 14:
            continue

        # 日付マッチ直後のテキストから公演名を抽出（次の日付パターンまで）
        after_start = m.end()
        next_m = DATE_RANGE_RE.search(body, after_start)
        chunk_end = next_m.start() if next_m else min(after_start + 200, len(body))
        chunk = body[after_start:chunk_end]
        lines = [l.strip() for l in chunk.split("\n") if l.strip()]
        # 「詳細はこちら」は除外
        lines = [l for l in lines if l not in ("詳細はこちら", "国立能楽堂", "能・狂言")]
        if not lines:
            continue
        # 最初の1-2行を公演名として連結
        name_parts = lines[:2]
        # 演目（／区切り）が2行目にあるパターン
        name = " ".join(name_parts)[:80]
        # 重複公演を除外
        key = (start_d.isoformat(), name)
        if key in seen:
            continue
        seen.add(key)

        for i in range((end_d - start_d).days + 1):
            day = start_d + datetime.timedelta(days=i)
            start_t = _start_time(name)
            results.append(make_event(
                date=day.isoformat(),
                name=name,
                venue="国立能楽堂",
                category="theater",
                start=start_t,
                end=_end_time(start_t),
                attendance=ATTENDANCE,
                audience="senior_wealthy",
                notes="能・狂言。年配富裕層中心。千駄ヶ谷駅徒歩7分でやや駅遠、終演後タクシー需要強い。",
                source="ntj.jac.go.jp",
            ))
    return results


def fetch(days_ahead=120):
    """国立能楽堂の主催公演を取得"""
    html = http_get(URL)
    text = strip_tags(html)
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)
    return [e for e in _extract_performances(text)
            if today.isoformat() <= e["date"] <= cutoff.isoformat()]
