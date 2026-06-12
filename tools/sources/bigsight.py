"""東京ビッグサイト公式のイベント一覧から展示会・催事を取得する。

ページ: https://www.bigsight.jp/visitor/event/ （今日以降のイベント一覧、ページネーションあり）
一覧に イベント名 / 入場区分（商談・一般）/ 利用施設 / 会期 / 開催時間 / 料金 が載っている。

来場者の推定: 利用ホール数 × 7,000人/日（中規模展示会の相場感）。
客層の推定:   入場区分「商談」→ business、「一般」はイベント名のキーワードで判定。
"""
import re

from .base import http_get, strip_tags, make_event

LIST_URL = "https://www.bigsight.jp/visitor/event/"
# ページネーションのパラメータ形式は実装が変わる可能性があるため複数試す
PAGE_URL_PATTERNS = [
    "https://www.bigsight.jp/visitor/event/?page={n}",
    "https://www.bigsight.jp/visitor/event/search.php?page={n}",
]

PER_HALL_VISITORS = 7000   # 1ホールあたりの1日来場者の概算
DEFAULT_VISITORS = 10000   # ホール数が読めなかったときの既定値

# 会期は「2026年06月10日（水）～2026年06月12日（金)」のように曜日括弧つき
PERIOD_RE = re.compile(
    r"(\d{4})年(\d{1,2})月(\d{1,2})日(?:（[^）]{1,3}）)?"
    r"\s*(?:[～〜~]\s*(?:(\d{4})年)?\s*(?:(\d{1,2})月)?\s*(\d{1,2})日)?"
)
HOURS_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-－～〜]\s*(\d{1,2}):(\d{2})")
HALL_RE = re.compile(r"([東西南北])\s*([\d\-－・,、\s]+)\s*ホール")

NAME_NOISE = ["新規タブで開きます", "新規ウィンドウで開きます"]

YOUTH_WORDS = ["アニメ", "ゲーム", "コミック", "同人", "アイドル", "コスプレ", "eスポーツ", "フェス", "就活"]
FAMILY_WORDS = ["ファミリー", "こども", "子ども", "キッズ", "親子", "恐竜"]
FESTIVAL_WORDS = ["同人", "即売", "フェス", "祭", "マルシェ", "フリーマーケット"]


def _count_halls(facility_text):
    """「東1-3・7ホール」→ 4 のようにホール数を数える"""
    total = 0
    for m in HALL_RE.finditer(facility_text):
        nums = m.group(2)
        for part in re.split(r"[・,、\s]+", nums.strip()):
            if not part:
                continue
            r = re.match(r"(\d+)\s*[-－]\s*(\d+)", part)
            if r:
                total += abs(int(r.group(2)) - int(r.group(1))) + 1
            elif part.isdigit():
                total += 1
    if "全館" in facility_text or "全展示" in facility_text:
        total = max(total, 12)
    return total


def _guess_audience_category(name, is_trade):
    if is_trade:
        return "business", "exhibition"
    if any(w in name for w in FAMILY_WORDS):
        return "family", "festival" if any(w in name for w in FESTIVAL_WORDS) else "exhibition"
    if any(w in name for w in YOUTH_WORDS):
        return "youth", "festival" if any(w in name for w in FESTIVAL_WORDS) else "exhibition"
    return "general", "festival" if any(w in name for w in FESTIVAL_WORDS) else "exhibition"


def _expand_dates(m):
    """会期の正規表現マッチを日付リスト['YYYY-MM-DD', ...]に展開する"""
    import datetime
    y1, mo1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
    start = datetime.date(y1, mo1, d1)
    if m.group(6):
        y2 = int(m.group(4)) if m.group(4) else y1
        mo2 = int(m.group(5)) if m.group(5) else mo1
        end = datetime.date(y2, mo2, int(m.group(6)))
    else:
        end = start
    if end < start or (end - start).days > 30:
        end = start  # 解析ミスの保険
    return [(start + datetime.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def _clean_name(name):
    for noise in NAME_NOISE:
        name = name.replace(noise, "")
    return " ".join(name.split())


def _parse_blocks(html):
    """h3見出しごとにイベントブロックへ分割してテキスト解析する"""
    blocks = re.split(r"<h3[^>]*>", html)[1:]
    for raw in blocks:
        name_html = raw.split("</h3>")[0]
        name = _clean_name(strip_tags("<p>" + name_html + "</p>"))
        body = strip_tags(raw)
        if not name or len(name) > 100:
            continue
        yield name, body


def _merge_cohosted(candidates):
    """同じ会期・時間・施設・規模のイベント群は合同開催（◯◯Week等の構成展）と
    みなして1件に統合する。重複カウントするとヒートマップが過大になるため。"""
    groups = {}
    for c in candidates:
        key = (tuple(c["dates"]), c["start"], c["end"], c["attendance"], c["facility"])
        groups.setdefault(key, []).append(c)

    merged = []
    for group in groups.values():
        rep = min(group, key=lambda c: len(c["name"]))
        for c in group:  # 「◯◯Week」「総合展」のような総称があればそれを代表にする
            if re.search(r"week|ウィーク|総合展", c["name"], re.IGNORECASE):
                rep = c
                break
        if len(group) > 1:
            rep = dict(rep, name=f"{rep['name']} ほか{len(group) - 1}展（合同開催）")
        merged.append(rep)
    return merged


def fetch(pages=3):
    """ビッグサイトのイベントを正規化イベントのリストで返す"""
    page_htmls = [http_get(LIST_URL)]
    for n in range(2, pages + 1):
        for pat in PAGE_URL_PATTERNS:
            try:
                html = http_get(pat.format(n=n))
            except Exception:
                continue
            if html and html not in page_htmls:
                page_htmls.append(html)
                break

    candidates = []
    seen_names = set()
    for html in page_htmls:
        for name, body in _parse_blocks(html):
            pm = PERIOD_RE.search(body)
            if not pm or name in seen_names:
                continue
            seen_names.add(name)

            hm = HOURS_RE.search(body)
            facility = ""
            fm = re.search(r"([^\n]*ホール[^\n]*)", body)
            if fm:
                facility = " ".join(fm.group(1).split())[:50]
            halls = _count_halls(body)

            candidates.append({
                "name": name,
                "dates": _expand_dates(pm),
                "start": f"{int(hm.group(1)):02d}:{hm.group(2)}" if hm else "10:00",
                "end": f"{int(hm.group(3)):02d}:{hm.group(4)}" if hm else "17:00",
                "facility": facility,
                "halls": halls,
                "attendance": halls * PER_HALL_VISITORS if halls else DEFAULT_VISITORS,
                "is_trade": "商談" in body,
            })

    events = []
    for c in _merge_cohosted(candidates):
        audience, category = _guess_audience_category(c["name"], c["is_trade"])
        notes_parts = []
        if c["facility"]:
            notes_parts.append(c["facility"])
        notes_parts.append("商談展（業界関係者中心）" if c["is_trade"] else "一般公開")
        notes_parts.append(f"来場者はホール数からの概算（{c['halls'] or '?'}ホール）")
        for date in c["dates"]:
            events.append(make_event(
                date=date, name=c["name"], venue="東京ビッグサイト",
                category=category, start=c["start"], end=c["end"],
                attendance=c["attendance"], audience=audience,
                notes="。".join(notes_parts), source="bigsight.jp",
            ))
    return events
