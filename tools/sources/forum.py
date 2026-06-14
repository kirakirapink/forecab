"""東京国際フォーラム（イベントカレンダー）の公演情報を取得する。

ページ:   https://www.t-i-forum.co.jp/visitors/event/
構造:     当月の公演が「日付 → 種別タグ（一般/関係者/一般&関係者）→ 公演名」の繰り返し。
          開始終了時刻は一覧に載らないため、公演名のキーワードから推定する。
          詳細ページ巡回は通信負荷が大きいので避け、推定で運用する方針。

ペルソナ的位置付け:
  P3 専門職（学会・株主総会）/ P6 年配富裕層（クラシック・ミュージカル・演歌）/
  business 系（IR・展示会）を幅広くカバーする重要会場。
  ホールA(5012席)、ホールC(1502席)、ホールB7(745席) を中心に大箱が並ぶ。
"""
import datetime
import re

from .base import http_get, strip_tags, make_event, guess_audience

URL = "https://www.t-i-forum.co.jp/visitors/event/"

DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日（[月火水木金土日]）")
TYPE_TAGS = {"一般", "関係者", "一般&関係者"}
SKIP_LINES = {"イベントカレンダー", "印刷する", "フリーワード検索", "日付検索", "絞り込み検索",
              "すべて", "～", "MENU", "CLOSE", "戻る", "閉じる"}

# 中止公演や非公開関係者イベントを除外するためのパターン
CANCEL_RE = re.compile(r"(中止|延期未定|延期決定|公演中止)")

# 公演名キーワードからカテゴリ/開演時刻/集客を推定するルール（先勝ち）
_IC = re.IGNORECASE
INFERENCE_RULES = [
    # 学術・展示会・見本市・カンファレンス（昼開催、終日）
    (re.compile(r"学会|学術|総会(?!.*株主)|EXPO|見本市|展示会|フェア|医療|薬学|Conference|Forum|Symposium|シンポジウム", _IC),
     {"category": "exhibition", "start": "10:00", "end": "17:00", "attendance": 3000, "audience": "business",
      "note": "学会・展示会・カンファレンス想定。10-17時開催で推定"}),
    # 株主総会・IR・式典・表彰式
    (re.compile(r"株主総会|表彰式|定時総会|IR説明", _IC),
     {"category": "exhibition", "start": "10:00", "end": "12:00", "attendance": 800, "audience": "business",
      "note": "株主総会・式典想定。10-12時で推定"}),
    # クラシック・オペラ
    (re.compile(r"オペラ|交響楽|フィルハーモニー|クラシック|歌劇|魔笛|フィガロ|椿姫|ボエーム|アイーダ|ディズニー・オン・クラシック", _IC),
     {"category": "theater", "start": "18:30", "end": "21:30", "attendance": 4000, "audience": "senior_wealthy",
      "note": "クラシック・オペラ想定。18:30開演で推定"}),
    # 演歌・歌謡（年配富裕層）
    (re.compile(r"演歌|歌謡|松山千春|さだまさし|加藤登紀子|松任谷由実|YUMI MATSUTOYA|SHOGO HAMADA|浜田省吾|押尾コータロー|レキシ|聖飢魔", _IC),
     {"category": "concert", "start": "18:00", "end": "21:00", "attendance": 4000, "audience": "senior_wealthy",
      "note": "年配富裕層向けコンサート想定。18時開演で推定"}),
    # ミュージカル・舞台
    (re.compile(r"ミュージカル|歌舞伎|落語|能楽|狂言|舞台|演劇", _IC),
     {"category": "theater", "start": "18:00", "end": "21:00", "attendance": 3000, "audience": "senior_wealthy",
      "note": "ミュージカル・舞台想定。18時開演で推定"}),
    # ファンミーティング・K-POP・特典会（若年層）
    (re.compile(r"FANMEETING|FAN MEETING|FANCON|K-POP|KPOP|アイドル|生誕|特典会|握手会|KYUHYUN|ONEUS|TWICE|NiziU", _IC),
     {"category": "concert", "start": "18:00", "end": "20:30", "attendance": 4000, "audience": "youth",
      "note": "ファンミ・K-POP想定。若年層中心で18時開演推定"}),
    # コンサート全般（汎用）
    (re.compile(r"コンサート|CONCERT|LIVE|TOUR|ライブ|ツアー|公演|フェス|Anniversary", _IC),
     {"category": "concert", "start": "18:30", "end": "21:00", "attendance": 4000, "audience": "general",
      "note": "コンサート想定。18:30開演で推定"}),
    # フリマ・骨董市（昼開催の催事）
    (re.compile(r"フリーマーケット|骨董市|大江戸", _IC),
     {"category": "festival", "start": "09:00", "end": "16:00", "attendance": 5000, "audience": "general",
      "note": "催事想定。日中開催で推定"}),
    # 上映会・キッズ
    (re.compile(r"上映会|キッズ|ファミリー|親子|プペル", _IC),
     {"category": "theater", "start": "13:00", "end": "16:00", "attendance": 1500, "audience": "family",
      "note": "上映会・ファミリー向け想定。昼開催で推定"}),
]

# デフォルト（どのルールにもマッチしない場合）
DEFAULT_INFERENCE = {
    "category": "concert", "start": "18:30", "end": "21:00",
    "attendance": 3000, "audience": "general",
    "note": "公演詳細不明。コンサート想定（18:30開演）で推定",
}


def _infer(name):
    for rule, attrs in INFERENCE_RULES:
        if rule.search(name):
            # 名前から客層を再推定（先勝ちルールが general を返した場合のみ上書き）
            attrs = dict(attrs)
            if attrs["audience"] == "general":
                attrs["audience"] = guess_audience(name, default="general")
            return attrs
    attrs = dict(DEFAULT_INFERENCE)
    attrs["audience"] = guess_audience(name, default="general")
    return attrs


def _parse_events(text):
    """テキストを行単位で処理して (date, name, type) のタプルを生成する"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # 「イベントカレンダーは...」以降の本体だけ見る
    start_idx = 0
    for i, line in enumerate(lines):
        if "イベントカレンダーは主催者よりいただいた" in line:
            start_idx = i + 1
            break
    body = lines[start_idx:]

    current_date = None
    current_type = None
    name_buf = []
    results = []

    def flush():
        if current_date and current_type and name_buf:
            name = " ".join(name_buf).strip()
            if name and name not in SKIP_LINES and not CANCEL_RE.search(name):
                results.append((current_date, name, current_type))

    for line in body:
        m = DATE_RE.match(line)
        if m:
            flush()
            name_buf = []
            current_date = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            current_type = None
            continue
        if line in TYPE_TAGS:
            flush()
            name_buf = []
            current_type = line
            continue
        if line in SKIP_LINES:
            continue
        if line.startswith("フッター") or line.startswith("Copyright"):
            break
        if current_date and current_type is not None:
            name_buf.append(line)
    flush()
    return results


def fetch(days_ahead=120):
    """東京国際フォーラムの今後の公演を返す"""
    html = http_get(URL)
    text = strip_tags(html)
    raw = _parse_events(text)

    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)

    events = []
    seen = set()
    for date, name, type_tag in raw:
        # 関係者のみは来場者ゼロ扱いでタクシー需要薄い → 除外
        if type_tag == "関係者":
            continue
        if not (today <= date <= cutoff):
            continue
        key = (date.isoformat(), name)
        if key in seen:
            continue
        seen.add(key)
        attrs = _infer(name)
        events.append(make_event(
            date=date.isoformat(),
            name=name[:80],
            venue="東京国際フォーラム",
            category=attrs["category"],
            start=attrs["start"],
            end=attrs["end"],
            attendance=attrs["attendance"],
            audience=attrs["audience"],
            notes=attrs["note"],
            source="t-i-forum.co.jp",
        ))
    return events
