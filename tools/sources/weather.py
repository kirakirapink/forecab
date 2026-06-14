"""気象庁(JMA)の東京地方天気予報を取得する。

API:    https://www.jma.go.jp/bosai/forecast/data/forecast/{area_code}.json
        area_code=130000 = 東京都
構造:   レスポンスは2セクション
        [0] 短期予報: 当日含む3日分の weatherCodes + 6時間毎降水確率 + 朝夕気温
        [1] 週間予報: 翌日から7日分の weatherCodes / pop / tempsMin/tempsMax

タクシー需要への影響:
  - 雨: 電車・徒歩を避けてタクシーに流れる。需要1.3〜1.4倍
  - 雪: さらに需要急増。タクシー一択になり1.7〜1.8倍
  - 猛暑(35℃以上): 駅まで歩きたくない層が増加。1.1倍加算
  - 極寒(0℃未満): 同様に屋外を避ける。1.1倍加算

app.js 側で events.js の weather_forecast を参照して係数を計算する。
"""
import datetime
import json
import urllib.request

from .base import _SSL_CTX, USER_AGENT, SourceError

# 130000 = 東京都
URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json"


def _fetch_json():
    """JMA forecast JSON を取得（生）"""
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as res:
            return json.loads(res.read())
    except Exception as e:
        raise SourceError(f"JMA取得失敗: {e}") from e


def _parse_date(ts):
    """ISO 'YYYY-MM-DDTHH:MM:SS+09:00' → 'YYYY-MM-DD'"""
    return ts.split("T", 1)[0]


def fetch():
    """日付ISO → {weather_code, weather, pop_max, temp_max, temp_min} の dict を返す。
    取得失敗時は空 dict を返す（スコアは weather_factor=1.0 で計算される設計）。
    """
    try:
        data = _fetch_json()
    except SourceError as e:
        print(f"[weather] 警告: {e}")
        return {}

    result = {}

    # ===== 短期予報（3日分） =====
    if data and len(data) > 0:
        short = data[0].get("timeSeries", [])
        # timeSeries[0]: 天気概況（3日分: 今日0時 / 明日0時 / 明後日0時 想定の代表値）
        if len(short) > 0 and short[0].get("areas"):
            a = short[0]["areas"][0]
            for i, ts in enumerate(short[0]["timeDefines"]):
                date = _parse_date(ts)
                codes = a.get("weatherCodes", [])
                weathers = a.get("weathers", [])
                if i < len(codes):
                    result.setdefault(date, {})["weather_code"] = codes[i]
                if i < len(weathers):
                    result.setdefault(date, {})["weather"] = weathers[i]

        # timeSeries[1]: 6時間毎の降水確率
        #   timeDefinesの各時刻は「その時刻から6時間先まで」の予報を表す
        #   日次最大 + 時間帯別配列の両方を保持（時間帯別はヒートマップ表示用）
        if len(short) > 1 and short[1].get("areas"):
            a = short[1]["areas"][0]
            pops_by_date = {}
            hourly_by_date = {}  # 日付 → [{start_min, end_min, pop}, ...]
            for i, ts in enumerate(short[1]["timeDefines"]):
                date = _parse_date(ts)
                pop_list = a.get("pops", [])
                if i >= len(pop_list):
                    continue
                try:
                    pop = int(pop_list[i])
                except (ValueError, TypeError):
                    continue
                pops_by_date[date] = max(pops_by_date.get(date, 0), pop)
                # 「YYYY-MM-DDTHH:MM:SS+09:00」から時間を抜く
                hour = int(ts[11:13])
                start_min = hour * 60
                end_min = start_min + 360  # 6時間 = 360分
                hourly_by_date.setdefault(date, []).append({
                    "start_min": start_min,
                    "end_min": end_min,
                    "pop": pop,
                })
            for date, pop in pops_by_date.items():
                result.setdefault(date, {})["pop_max"] = pop
            for date, hourly in hourly_by_date.items():
                result.setdefault(date, {})["hourly"] = hourly

        # timeSeries[2]: 朝晩の気温（最低・最高）
        if len(short) > 2 and short[2].get("areas"):
            a = short[2]["areas"][0]
            temps_by_date = {}
            for i, ts in enumerate(short[2]["timeDefines"]):
                date = _parse_date(ts)
                temp_list = a.get("temps", [])
                if i < len(temp_list):
                    try:
                        t = int(temp_list[i])
                        temps_by_date.setdefault(date, []).append(t)
                    except (ValueError, TypeError):
                        pass
            for date, ts in temps_by_date.items():
                result.setdefault(date, {})["temp_min"] = min(ts)
                result.setdefault(date, {})["temp_max"] = max(ts)

    # ===== 週間予報（7日分） =====
    if len(data) > 1:
        weekly = data[1].get("timeSeries", [])
        if len(weekly) > 0 and weekly[0].get("areas"):
            a = weekly[0]["areas"][0]
            for i, ts in enumerate(weekly[0]["timeDefines"]):
                date = _parse_date(ts)
                codes = a.get("weatherCodes", [])
                pops = a.get("pops", [])
                if date not in result:
                    result[date] = {}
                if i < len(codes) and codes[i]:
                    result[date].setdefault("weather_code", codes[i])
                if i < len(pops) and pops[i]:
                    try:
                        result[date].setdefault("pop_max", int(pops[i]))
                    except (ValueError, TypeError):
                        pass

        if len(weekly) > 1 and weekly[1].get("areas"):
            a = weekly[1]["areas"][0]
            for i, ts in enumerate(weekly[1]["timeDefines"]):
                date = _parse_date(ts)
                tmin = a.get("tempsMin", [])
                tmax = a.get("tempsMax", [])
                if date not in result:
                    result[date] = {}
                if i < len(tmin) and tmin[i]:
                    try:
                        result[date].setdefault("temp_min", int(tmin[i]))
                    except (ValueError, TypeError):
                        pass
                if i < len(tmax) and tmax[i]:
                    try:
                        result[date].setdefault("temp_max", int(tmax[i]))
                    except (ValueError, TypeError):
                        pass

    return result
