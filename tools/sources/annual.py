"""年次の超大型イベント手動マスタ。

自動取得が困難で年次回帰する花火大会・東京マラソン・初詣・カウントダウン等を
data/annual_master.csv に登録しておくと、開催14日前から自動で events.js に反映される。

CSV列:
    date,name,venue,category,start,end,attendance,audience,notes
    （events_template.csv と同じスキーマ）

メンテナンス方針:
    - 年に1回、翌年分の予定日を更新する（多くは「○月第N土曜」等のパターンで概算可能）
    - 公式発表が出たら正確な日付に書き換える
    - 過去日付になったエントリは消さず残しても、日付フィルタで自動除外される

ペルソナ的位置付け:
    花火・初詣・マラソン・カウントダウンは特定客層に偏らない混在イベントだが、
    会場が駅遠（花火）または広域規制（マラソン・カウントダウン）になることで
    駅事情×時間プレミアムの両軸でスコアが跳ねる。
"""
import csv
import datetime
from pathlib import Path

from .base import make_event

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "annual_master.csv"


def fetch(days_ahead=120):
    """年次手動マスタから今後 days_ahead 日以内のイベントを取得"""
    if not CSV_PATH.exists():
        return []
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=days_ahead)
    events = []
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            date_s = row.get("date", "")
            if not date_s or not row.get("name"):
                continue
            try:
                d = datetime.date.fromisoformat(date_s)
            except ValueError:
                continue
            if not (today <= d <= cutoff):
                continue
            try:
                attendance = int(row.get("attendance", "10000") or "10000")
            except ValueError:
                attendance = 10000
            events.append(make_event(
                date=date_s,
                name=row["name"],
                venue=row.get("venue", ""),
                category=row.get("category", "festival") or "festival",
                start=row.get("start", "19:00") or "19:00",
                end=row.get("end", "21:00") or "21:00",
                attendance=attendance,
                audience=row.get("audience", "general") or "general",
                notes=row.get("notes", ""),
                source="年次マスタ",
            ))
    return events
