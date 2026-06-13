"""新国立劇場の公演情報を取得する（オペラ・バレエ・現代演劇・ダンス）。

ページ: https://www.nntt.jac.go.jp/calendar/topcalendar.json
構造:   [{ datetime: "YYYY/MM", dateballs: [{title, place, genre, datenumber, datetime2, ...}] }, ...]

JSONを直接取得できるため、HTMLパースは不要（最も実装が単純）。

ペルソナ的位置付け:
  - オペラ/バレエ → 年配富裕層（P6）+ 専門職教養層（P3）
  - 現代演劇/ダンス → 専門職教養層（P3）
  どちらも初台駅から徒歩・地下通路嫌いの高齢層が多く、終演後21〜22時台の
  甲州街道側でタクシー需要が確実に立つ立地。
"""
import datetime
import json
import re

from .base import http_get, make_event, SourceError

URL = "https://www.nntt.jac.go.jp/calendar/topcalendar.json"

# ジャンル → アプリのカテゴリ。'event' は小規模イベントなので除外
GENRE_TO_CATEGORY = {
    "opera": "theater",
    "ballet": "theater",
    "play": "theater",
    "dance": "theater",
    "musical": "theater",
}

# 会場ごとのキャパシティ（公称値）
PLACE_CAPACITY = {
    "オペラパレス": 1814,
    "中劇場": 1010,
    "小劇場": 468,
}

# タクシー需要に直結しない小規模会場は除外
EXCLUDE_PLACES = ("情報センター", "ホワイエ", "プロムナード", "アトリウム")

# 終演時間の推定（ジャンル別、分）
DURATION_MIN = {
    "opera": 210,
    "ballet": 180,
    "musical": 180,
    "play": 150,
    "dance": 120,
}

# ジャンル別の客層・観客層（オペラ/バレエは年配富裕、現代演劇/ダンスは年配寄り一般）
GENRE_AUDIENCE = {
    "opera": "senior_wealthy",
    "ballet": "senior_wealthy",
    "musical": "general",
    "play": "general",
    "dance": "general",
}

# 来場稼働率（人気公演は満員、平日昼公演は7割など）
ATTENDANCE_RATIO = 0.85


def _fmt_time(minutes):
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def fetch(days_ahead=45):
    """新国立劇場の今後の公演を正規化イベントのリストで返す"""
    try:
        raw = http_get(URL)
        data = json.loads(raw)
    except (ValueError, SourceError) as e:
        raise SourceError(f"新国立劇場JSONの取得に失敗: {e}") from e

    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)
    events = []

    for month_block in data:
        ym = month_block.get("datetime", "")
        try:
            year, month = map(int, ym.split("/"))
        except (ValueError, AttributeError):
            continue

        for ev in month_block.get("dateballs", []):
            genre = ev.get("genre", "")
            place = (ev.get("place") or "").strip()
            title = (ev.get("title") or "").strip()
            time_str = (ev.get("datetime2") or "").strip()

            if genre not in GENRE_TO_CATEGORY or not title or not place:
                continue
            if any(x in place for x in EXCLUDE_PLACES):
                continue
            # 時刻未定（timedisplay != 'T'）や ":" を含まないものはスキップ
            if ev.get("timedisplay") != "T" or ":" not in time_str:
                continue

            try:
                day = int(ev.get("datenumber") or 0)
                date = datetime.date(year, month, day)
            except (ValueError, TypeError):
                continue
            if not (today <= date <= cutoff):
                continue

            try:
                h, m = map(int, time_str.split(":"))
            except ValueError:
                continue
            start_min = h * 60 + m
            end_min = start_min + DURATION_MIN.get(genre, 150)

            attendance = int(PLACE_CAPACITY.get(place, 1000) * ATTENDANCE_RATIO)
            # JSON の title に <small>...</small> 等が混じることがあるのでタグを除去
            title = re.sub(r"<[^>]+>", "", title).strip()
            sub = re.sub(r"<[^>]+>", "", ev.get("sub_title") or "").strip()
            name = f"{title}（{sub}）" if sub and sub not in title else title

            events.append(make_event(
                date=date.isoformat(),
                name=name,
                venue=f"新国立劇場（{place}）",
                category="theater",
                start=_fmt_time(start_min),
                end=_fmt_time(end_min),
                attendance=attendance,
                audience=GENRE_AUDIENCE.get(genre, "general"),
                notes=f"ジャンル: {genre}。会場キャパ約{PLACE_CAPACITY.get(place, '?')}席。終演時刻は{DURATION_MIN.get(genre, 150)}分想定。",
                source="nntt.jac.go.jp",
            ))
    return events
