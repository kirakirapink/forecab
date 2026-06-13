"""日本医学会 分科会総会一覧から、東京都開催の学術集会を取得する。

ページ: https://jams.med.or.jp/members-a/index.html
構造:   各分科会総会が「No.XX 日本〇〇学会 / YYYY年MM月DD日（曜）～YYYY年MM月DD日（曜）／場所」の形式で
        テキスト中に列挙される。

ペルソナ的位置付け:
  P3 専門職（医師）ど真ん中。地方開催の学会では羽田・東京駅→会場のタクシー需要、
  都内開催では学会会場→ホテル・空港の需要が出る。
  医師は時間価値が高く経費移動可能で、タクシー利用率が一般よりかなり高い。
"""
import datetime
import re

from .base import http_get, strip_tags, make_event

URL = "https://jams.med.or.jp/members-a/index.html"

# 「No.17 日本内科学会  2026年4月10日（金）～2026年4月12日（日）／東京都・ハイブリッド開催」のような形式
SOCIETY_RE = re.compile(
    r"No\.(\d+)\s*([^\n|]{2,50}?学会)\s*"
    r"(\d{4})年(\d{1,2})月(\d{1,2})日（[月火水木金土日]）"
    r"\s*[～〜~]\s*"
    r"(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日（[月火水木金土日]）"
    r"／([^|\n]{1,50})"
)

# WEB開催のみは除外（タクシー需要なし）
WEB_ONLY_PATTERNS = ["WEB開催", "Web開催", "オンライン開催", "WEB総会"]

# 学術集会の典型的な参加者数（学会規模により変動が大きいが概算）
DEFAULT_ATTENDANCE = 2500

# 学会は終日開催（9時〜17時想定）。タクシー需要は朝（地方医師の宿→会場）と夕方（会場→宿・懇親会・空港）に立つ
DEFAULT_START = "09:00"
DEFAULT_END = "17:00"


def fetch(days_ahead=120):
    """日本医学会の今後の東京都開催学会を取得"""
    html = http_get(URL)
    text = strip_tags(html)

    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)
    events = []
    seen = set()

    for m in SOCIETY_RE.finditer(text):
        society = m.group(2).strip()
        location = m.group(9).strip()

        # 東京都開催のみ。WEB開催のみは除外
        if "東京都" not in location:
            continue
        if any(p in location for p in WEB_ONLY_PATTERNS):
            continue

        try:
            y1, mo1, d1 = int(m.group(3)), int(m.group(4)), int(m.group(5))
            y2 = int(m.group(6)) if m.group(6) else y1
            mo2 = int(m.group(7)) if m.group(7) else mo1
            d2 = int(m.group(8))
            start_date = datetime.date(y1, mo1, d1)
            end_date = datetime.date(y2, mo2, d2)
        except (ValueError, TypeError):
            continue
        if end_date < start_date or (end_date - start_date).days > 14:
            continue

        # 期間内の各日を1イベントとして展開
        days = (end_date - start_date).days + 1
        for i in range(days):
            date = start_date + datetime.timedelta(days=i)
            if not (today <= date <= cutoff):
                continue
            key = (date.isoformat(), society)
            if key in seen:
                continue
            seen.add(key)

            hybrid = "ハイブリッド" in location
            events.append(make_event(
                date=date.isoformat(),
                name=f"{society} 学術集会",
                venue="都内学術集会会場",
                category="exhibition",  # 専門職向け会議として展示会扱い（ビジネス系）
                start=DEFAULT_START,
                end=DEFAULT_END,
                attendance=DEFAULT_ATTENDANCE,
                audience="business",  # 医師は専門職だが既存スキーマでは business が最も近い
                notes=f"分科会No.{m.group(1)}。{location}。"
                      + ("一部はオンライン参加だが現地参加者も多い。" if hybrid else "")
                      + "全国から医師が参集。羽田・東京駅→会場、会場→都心ホテルの需要が典型。",
                source="jams.med.or.jp",
            ))
    return events
