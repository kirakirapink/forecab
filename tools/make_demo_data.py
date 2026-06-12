#!/usr/bin/env python3
"""デモ用イベントデータ生成スクリプト。

実行した日を起点に7日分のデモイベントを data/events.js に書き出す。
イベント名はすべて架空（実在のイベントではない）。

使い方:
    python3 tools/make_demo_data.py
"""
import json
import datetime
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "events.js"

# day: 実行日からのオフセット（0=今日）
# audience: business / general / youth / family / senior_wealthy
TEMPLATE = [
    # --- Day 0 ---
    dict(day=0, name="国際スマートモビリティEXPO（1日目）", venue="東京ビッグサイト",
         category="exhibition", start="10:00", end="18:00", attendance=45000,
         audience="business", notes="B2B見本市。出展社・バイヤーの出入りが終日続く"),
    dict(day=0, name="プロ野球ナイター", venue="東京ドーム",
         category="sports", start="18:00", end="21:30", attendance=42000,
         audience="general", notes="延長で終了時刻が後ろにずれる可能性あり"),
    dict(day=0, name="ロックバンド アリーナツアー", venue="有明アリーナ",
         category="concert", start="18:30", end="21:00", attendance=15000,
         audience="youth", notes="規制退場で出が30分程度に分散"),
    dict(day=0, name="海外オーケストラ来日公演", venue="サントリーホール",
         category="theater", start="19:00", end="21:15", attendance=2000,
         audience="senior_wealthy", notes="S席3万円クラス。タクシー利用率高"),
    dict(day=0, name="DXサミット TOKYO", venue="東京国際フォーラム",
         category="exhibition", start="09:30", end="18:30", attendance=8000,
         audience="business", notes="経営層向けカンファレンス。懇親会後20時台にも波"),

    # --- Day 1 ---
    dict(day=1, name="国際スマートモビリティEXPO（2日目・最終日）", venue="東京ビッグサイト",
         category="exhibition", start="10:00", end="17:00", attendance=50000,
         audience="business", notes="最終日は閉場が1時間早い。撤収需要も出る"),
    dict(day=1, name="シンガーソングライター 武道館公演", venue="日本武道館",
         category="concert", start="18:00", end="21:00", attendance=14000,
         audience="general", notes="金曜夜。九段下駅大混雑の定番パターン"),
    dict(day=1, name="プロ野球ナイター", venue="明治神宮野球場",
         category="sports", start="18:00", end="21:45", attendance=30000,
         audience="general", notes="花火演出の日は観客増"),
    dict(day=1, name="アイドルグループ ライブ", venue="Zepp DiverCity",
         category="concert", start="19:00", end="21:30", attendance=2400,
         audience="youth", notes="物販で昼から人はいるが乗車は終演後のみ"),
    dict(day=1, name="プロ野球ナイター", venue="東京ドーム",
         category="sports", start="18:00", end="21:30", attendance=41000,
         audience="general", notes=""),

    # --- Day 2 (週末) ---
    dict(day=2, name="サッカー国際親善試合", venue="国立競技場",
         category="sports", start="19:00", end="21:00", attendance=55000,
         audience="general", notes="終了後は外苑周辺交通規制。規制外で構える"),
    dict(day=2, name="アイドルグループ ドーム公演（1日目）", venue="東京ドーム",
         category="concert", start="17:00", end="20:30", attendance=45000,
         audience="youth", notes="遠征組が多く東京駅・羽田方面の需要が混じる"),
    dict(day=2, name="ファミリー恐竜ワールド展", venue="東京ビッグサイト",
         category="festival", start="09:00", end="17:00", attendance=25000,
         audience="family", notes="ベビーカー連れの短距離需要が点々と出る"),
    dict(day=2, name="ロックフェス前夜祭", venue="豊洲PIT",
         category="concert", start="17:00", end="19:30", attendance=3000,
         audience="youth", notes=""),
    dict(day=2, name="バレエ団 全幕公演", venue="東京文化会館",
         category="theater", start="18:00", end="21:00", attendance=2300,
         audience="senior_wealthy", notes="土曜夜公演。終演後は上野公園口に列"),

    # --- Day 3 (週末) ---
    dict(day=3, name="アイドルグループ ドーム公演（2日目・昼）", venue="東京ドーム",
         category="concert", start="14:00", end="17:30", attendance=45000,
         audience="youth", notes="昼公演のため夕方に山。夜は需要薄"),
    dict(day=3, name="同人誌即売会", venue="東京ビッグサイト",
         category="festival", start="10:00", end="17:00", attendance=80000,
         audience="youth", notes="物量は大きいが電車利用が大半。大荷物客の駅までの短距離が狙い目"),
    dict(day=3, name="オペラ マチネ公演", venue="東京文化会館",
         category="theater", start="14:00", end="17:30", attendance=2300,
         audience="senior_wealthy", notes=""),
    dict(day=3, name="大相撲 場所中（千秋楽前）", venue="両国国技館",
         category="sports", start="08:30", end="18:00", attendance=11000,
         audience="senior_wealthy", notes="打ち出し18時前後。銀座・赤坂方面の中距離が出る"),

    # --- Day 4 (平日・谷間) ---
    dict(day=4, name="医療機器メーカー 新製品発表会", venue="東京国際フォーラム",
         category="exhibition", start="13:00", end="17:00", attendance=1500,
         audience="business", notes="小規模だが客単価は高め"),

    # --- Day 5 ---
    dict(day=5, name="国際食品・飲料展（1日目）", venue="東京ビッグサイト",
         category="exhibition", start="10:00", end="17:00", attendance=35000,
         audience="business", notes="地方バイヤー多数。東京駅・ホテル方面"),
    dict(day=5, name="クラシック リサイタル", venue="サントリーホール",
         category="theater", start="19:00", end="21:00", attendance=1800,
         audience="senior_wealthy", notes=""),

    # --- Day 6 ---
    dict(day=6, name="国際食品・飲料展(2日目)", venue="東京ビッグサイト",
         category="exhibition", start="10:00", end="17:00", attendance=38000,
         audience="business", notes=""),
    dict(day=6, name="演歌歌手 特別公演", venue="日本武道館",
         category="concert", start="16:00", end="18:30", attendance=12000,
         audience="senior_wealthy", notes="年配客中心で開演前の送りも狙える"),
    dict(day=6, name="eスポーツ大会 決勝", venue="有明アリーナ",
         category="sports", start="15:00", end="20:00", attendance=12000,
         audience="youth", notes=""),
]


def main():
    today = datetime.date.today()
    events = []
    for i, t in enumerate(TEMPLATE, start=1):
        d = today + datetime.timedelta(days=t["day"])
        events.append({
            "id": f"demo-{i:03d}",
            "date": d.isoformat(),
            "name": t["name"],
            "venue": t["venue"],
            "category": t["category"],
            "start": t["start"],
            "end": t["end"],
            "attendance": t["attendance"],
            "audience": t["audience"],
            "notes": t["notes"],
        })

    payload = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": "demo",
        "events": events,
    }
    js = (
        "// このファイルは自動生成。直接編集せず tools/make_demo_data.py か tools/csv_to_events.py で再生成する\n"
        "window.TAXI_APP_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n"
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(js, encoding="utf-8")
    print(f"OK: {len(events)}件のデモイベントを書き出しました -> {OUT_PATH}")


if __name__ == "__main__":
    main()
