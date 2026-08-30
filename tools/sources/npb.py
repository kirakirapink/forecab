"""NPB公式サイトの月別日程から、地域別の対象球場の試合を取得する。

ページ: https://npb.jp/games/2026/schedule_06_detail.html （月別・全試合）
表記:   日付「6/11 （木）」/ カード「巨人 - ロッテ」or「巨人 [8-2] ロッテ」/ 球場「東京ドーム」/ 時刻「18:00」

HTMLの構造変化に強いよう、タグ構造ではなくテキスト化した行から
「対象球場名を含む行」を正規表現で解析する方針。
"""
import re

from .base import http_get, strip_tags, make_event

SCHEDULE_URL = "https://npb.jp/games/{year}/schedule_{month:02d}_detail.html"

# NPB表記（空白除去後） → アプリの会場マスタ名
REGION_STADIUMS = {
    "tokyo": {
        "東京ドーム": "東京ドーム",
        "神宮": "明治神宮野球場",
    },
    "yokohama": {
        "横浜": "横浜スタジアム",
    },
    "osaka": {
        "京セラD大阪": "京セラドーム大阪",
    },
}
# 既存の外部参照との互換用。
TARGET_STADIUMS = REGION_STADIUMS["tokyo"]

TEAMS = [
    "巨人", "ヤクルト", "DeNA", "阪神", "広島", "中日",
    "ロッテ", "日本ハム", "ソフトバンク", "楽天", "オリックス", "西武",
]

# 来場者の概算（球場, 週末か）。NPB公式の観客動員発表のおおまかな平均値
ATTENDANCE_ESTIMATE = {
    ("東京ドーム", False): 40000, ("東京ドーム", True): 42000,
    ("明治神宮野球場", False): 24000, ("明治神宮野球場", True): 29000,
    ("横浜スタジアム", False): 28000, ("横浜スタジアム", True): 32000,
    ("京セラドーム大阪", False): 26000, ("京セラドーム大阪", True): 32000,
}

GAME_DURATION_MIN = 195  # 平均試合時間 約3時間15分

# テキスト化すると1試合は「日付行 → ホーム球団 → '-'やスコア → ビジター球団 → 球場 → 時刻」
# の連続行になる（セルごとに1行）。ステートマシンで読み進める。
DATE_LINE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})（")
TIME_LINE_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _fmt_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fetch(year, month, weekend_dates, region="tokyo"):
    """指定月・地域のNPB試合を正規化イベントのリストで返す。

    weekend_dates: その月の土日のdateset（'YYYY-MM-DD'）。来場者推定に使う。
    """
    html = http_get(SCHEDULE_URL.format(year=year, month=month))
    lines = strip_tags(html).split("\n")
    target_stadiums = REGION_STADIUMS.get(region)
    if target_stadiums is None:
        raise ValueError(f"未対応の地域です: {region}")

    team_set = set(TEAMS)
    events = []
    current_day = None
    teams = []
    stadium = None

    for line in lines:
        m = DATE_LINE_RE.match(line)
        if m:
            if int(m.group(1)) == month:
                current_day = int(m.group(2))
            teams, stadium = [], None
            continue

        if line in team_set:
            if len(teams) >= 2:  # 前の試合が時刻まで到達しなかった（中止・対象外球場など）
                teams, stadium = [], None
            teams.append(line)
            continue

        normalized_line = re.sub(r"\s+", "", line)
        if normalized_line in target_stadiums:
            stadium = normalized_line if len(teams) == 2 else None
            continue

        tm = TIME_LINE_RE.match(line)
        if tm and stadium and len(teams) == 2 and current_day:
            start_min = int(tm.group(1)) * 60 + int(tm.group(2))
            if 10 * 60 <= start_min <= 19 * 60:
                date = f"{year}-{month:02d}-{current_day:02d}"
                venue = target_stadiums[stadium]
                events.append(make_event(
                    date=date,
                    name=f"プロ野球 {teams[0]} vs {teams[1]}",
                    venue=venue,
                    category="sports",
                    start=_fmt_time(start_min),
                    end=_fmt_time(start_min + GAME_DURATION_MIN),
                    attendance=ATTENDANCE_ESTIMATE[(venue, date in weekend_dates)],
                    audience="general",
                    notes="終了時刻は平均試合時間からの推定。延長あり",
                    source="npb.jp",
                ))
            teams, stadium = [], None
    return events
