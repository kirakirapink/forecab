"""横浜アリーナ公式カレンダーの公開JSONを取得する。

エンドポイント: https://www.yokohama-arena.co.jp/event/202609?_format=json
公式カレンダー画面自身が同URLをAjaxで参照している。robots.txtではイベントページ取得可
（確認日: 2026-08-29）。
"""
import json

from .base import guess_audience, http_get, make_event

URL = "https://www.yokohama-arena.co.jp/event/{year}{month:02d}?_format=json"
DURATION_MIN = 180


def _fmt(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_payload(text):
    rows = json.loads(text)
    events = []
    for row in rows if isinstance(rows, list) else []:
        date = str(row.get("date2") or row.get("date1") or "")
        title = str(row.get("title") or "").strip()
        artist = str(row.get("artist") or "").strip()
        name = title or artist
        if artist and title and artist not in title:
            name = f"{title} — {artist}"
        starts = row.get("ev_start") or []
        ends = row.get("ev_end") or []
        opens = row.get("ev_open") or []
        if len(date) != 10 or not name or not starts:
            continue
        category = "concert" if str(row.get("category")) == "1" else "festival"
        for index, start in enumerate(starts):
            try:
                hour, minute = [int(part) for part in str(start).split(":", 1)]
            except (TypeError, ValueError):
                continue
            start_min = hour * 60 + minute
            end = str(ends[index]) if index < len(ends) and ends[index] else _fmt(start_min + DURATION_MIN)
            event_name = name if len(starts) == 1 else f"{name}（{index + 1}回目）"
            notes = ""
            if index < len(opens) and opens[index]:
                notes = f"OPEN {opens[index]}。"
            if index >= len(ends) or not ends[index]:
                notes += "終了時刻は大型アリーナ公演の標準3時間で推定"
            events.append(make_event(
                date=date,
                name=event_name,
                venue="横浜アリーナ",
                category=category,
                start=_fmt(start_min),
                end=end,
                attendance=17000,
                audience=guess_audience(event_name, "youth" if category == "concert" else "general"),
                notes=notes,
                source="yokohama-arena.co.jp",
            ))
    return events


def fetch(months):
    events = []
    for year, month in months:
        events += _parse_payload(http_get(URL.format(year=year, month=month)))
    return events
