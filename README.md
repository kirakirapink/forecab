# FORECAB — 地域別イベント需要予報

東京・横浜・大阪のイベント情報（展示会・ライブ・スポーツ・舞台・催事）から、
タクシードライバー向けに **「いつ・どこを狙うべきか」** を星0〜5でスコアリングして表示するWebアプリ。
（FORECAB = Forecast + Cab）

画面とスコアリングは共通化し、イベント・会場・天気は地域ごとに分離している。

公開URL:

- 東京: `https://kirakirapink.github.io/forecab/tokyo/`
- 横浜: `https://kirakirapink.github.io/forecab/yokohama/`
- 大阪: `https://kirakirapink.github.io/forecab/osaka/`
- 旧URL `/forecab/` は東京版へ転送

## 使い方

ローカルではリポジトリ直下をHTTP配信して開く（イベントデータを `fetch` するため `file://` ではなくHTTPを使用）。

```bash
python3 -m http.server 8000
# http://localhost:8000/tokyo/ を開く
```

- ヘッダーの地域リボンで東京・横浜・大阪を切り替え
- 上部の日付タブで日を切り替え
- 「この日のベスト3」→ タップでそのイベントカードへ
- 時間帯別の需要予報（ヒートマップ）でピーク時間を確認
- イベントカードをタップするとスコア内訳・よく出る行き先・付け方のコツを表示
- 「おすすめ順 / 時間順」の並び替え、種別・エリアのフィルタあり

## スコアリングの仕組み（合計100点 → 星5換算）

| 項目 | 配点 | 根拠 |
|---|---|---|
| 規模 | 40 | 来場者数（対数スケール。100人=0点、10万人=満点） |
| 客層 | 20 | タクシー利用率の期待値。年配富裕層20 > ビジネス18 > 一般10 > ファミリー8 > 若年層5 |
| 時間帯 | 20 | 終演が遅いほど高得点（23時以降=終電リスクで満点）。展示会は終日出入りで底上げ |
| 駅事情 | 10 | 駅が遠い・路線が弱い・終演時に大混雑する会場ほど高得点 |
| 長距離 | 10 | 空港・近県・都心横断などロング乗車の期待値（会場マスタ由来） |
| ×種別補正 | — | 展示会1.10 / 舞台1.05 / ライブ1.00 / スポーツ0.92 / 催事0.85 |

設計の考え方:
- **展示会**は終演集中型ではなく終日出入りがあり、ビジネス客（経費移動・手荷物・空港需要）が多いため総合的に優遇
- **ライブ・スポーツ**は終演直後に需要が集中（規制退場で30〜75分に分散）
- **クラシック・オペラ**は規模こそ小さいが客層のタクシー利用率が最高クラス
- 係数はすべて [app.js](app.js) の冒頭にまとめてあり、現場の実感に合わせて調整できる

## データの更新

### 自動取得（メイン）
```bash
python3 tools/fetch_events.py              # 今日から14日分を取得して反映
python3 tools/fetch_events.py --region yokohama
python3 tools/fetch_events.py --region osaka
python3 tools/fetch_events.py --dry-run   # 取得結果のプレビューのみ
python3 tools/fetch_events.py --offline   # 通信せずキャッシュから再生成
```

実装済みのデータソース（[tools/sources/](tools/sources/) に1ファイル1ソース）:

| ソース | 取れるもの | 来場者の推定方法 |
|---|---|---|
| `npb.py` — NPB公式 月別日程 | 東京ドーム・神宮・横浜スタジアム・京セラドームのプロ野球 | 球場×平日/週末の平均動員テーブル |
| `bigsight.py` — 東京ビッグサイト公式 | 展示会・催事（会期・時間・入場区分つき） | 利用ホール数 × 7,000人/日 |
| `dome.py` — 東京ドーム公式 | ドームのコンサート・催事（野球以外。開演時刻つき） | コンサート45,000 / 催事30,000 |
| `ariake.py` — 有明アリーナ公式 | アリーナのライブ・スポーツ（当月+翌月） | 12,000（開演は18:00仮置き） |
| `zepp.py` — Zepp公式 | 東京3館・KT Zepp Yokohama・Zepp Namba / Osaka Bayside | 各館の最大収容規模 |
| `k_arena.py` — Kアリーナ横浜公式 | 公演日・OPEN/START | 20,000 |
| `yokohama_arena.py` — 横浜アリーナ公式 | 公開カレンダーJSON（複数公演・終演時刻対応） | 17,000 |
| `kyocera_dome.py` — 京セラドーム大阪公式 | 野球以外のコンサート・催事 | コンサート45,000 / 催事30,000 |
| `osaka_johall.py` — 大阪城ホール公式 | 公演日・開演/終演（複数公演対応） | 16,000 |
| `garden_theater.py` — 東京ガーデンシアター公式 | 大型ホールのライブ・スポーツ（期間公演は日ごとに展開） | 7,000（開演は18:00仮置き） |
| `yoyogi.py` — 国立代々木競技場公式 | 第一体育館のライブ・イベント（当月+翌月） | 10,000（時刻は17:00-20:30仮置き） |
| `takarazuka.py` — 宝塚歌劇公式 | 東京宝塚劇場の公演（期間公演は月曜を除き日ごとに展開） | 2,000（終演18:30の夕方回を主需要として採用） |

取得マナー（[tools/sources/base.py](tools/sources/base.py) で一元管理）:
- リクエスト間に最低2秒空ける ・ 同一URLは12時間キャッシュ ・ User-Agentに用途と連絡先を明示
- robots.txt の確認状況と時刻仮置きの有無は各ソースファイルの先頭コメントに記録

ビッグサイト固有の処理:
- 「◯◯Week」のような**合同開催の構成展は1件に統合**（重複カウントするとヒートマップが過大になるため）
- 入場区分「商談」→ ビジネス客、「一般」はイベント名キーワードで客層を推定

### 手動追加（ライブ・コンサート等、自動で取れないもの）
[data/manual_events.csv](data/events_template.csv) を作っておくと自動取得分とマージされる
（列形式は [data/events_template.csv](data/events_template.csv) と同じ。同名イベントは手動が優先）。

CSVだけで全運用したい場合は `python3 tools/csv_to_events.py data/events.csv`。

### デモデータ
```bash
python3 tools/make_demo_data.py
```
実行日から7日分の**架空イベント**を生成する（UI確認用。画面下部に注記が出る）。

### ソースを増やしたいとき
[tools/sources/](tools/sources/) に `fetch()` を持つファイルを1つ足し、
[tools/fetch_events.py](tools/fetch_events.py) から呼ぶだけ。次の候補（2026-06調査時のメモ）:
- 日本武道館 — 行事予定ページのURL特定がまだ（トップは nipponbudokan.or.jp）
- 国立競技場のイベントカレンダー — ライブ・サッカー
- Jリーグ公式日程（FC東京・東京ヴェルディの国立開催分）
- サントリーホール公演カレンダー — 富裕客層の定番
- GO TOKYO（都公式観光サイト）の観光イベント — URL要再調査（/jp/spot/event/ は404）
- ※集約サイト（Walker+等）は利用規約の確認が先

## iPhoneで使えるようにする（公開手順）

自前サーバーは不要。**GitHub Pages + GitHub Actions** で、毎朝6時(JST)に
GitHub側がデータを自動更新して静的サイトとして配信する
（ワークフロー定義: [.github/workflows/update-events.yml](.github/workflows/update-events.yml)）。

一度だけ以下を実行:

```bash
cd /Users/Shared/Taxi_JP_Project
gh repo create forecab --public --source=. --push
```

その後 GitHub のリポジトリ設定で:
1. **Settings → Pages → Source を「GitHub Actions」** にする
2. **Actions タブ → update-events → Run workflow** で初回実行

公開URLは `https://<ユーザー名>.github.io/forecab/`。ここから東京版へ移動し、
画面上部から横浜・大阪へ切り替えられる。
友人には このURLをSafariで開いて **共有 → ホーム画面に追加** してもらうと、
アイコン付きでアプリのように起動できる（PWA対応済み）。

- 料金: 無料（公開リポジトリのGitHub Pages + Actions無料枠。1日1回の実行なら余裕）
- 非公開にしたい場合: Private リポジトリのPagesは有料プランが必要になる点に注意

## 会場を追加する

東京は [venues.js](venues.js)、横浜・大阪は [regional/](regional/) 内の会場マスタに1ブロック足す。
駅アクセス（near/mid/far）、長距離期待（0〜1）、よく出る行き先、付け方のコツを書く。
未登録の会場名でもアプリは動く（標準値でスコアリング）。

## 構成

```
index.html                  旧URL互換の東京版転送入口
tokyo/index.html            東京版
yokohama/index.html         横浜版
osaka/index.html            大阪版
bootstrap.js / regions.js   共通ローダー・地域設定
app.js / scoring.js         全地域共通UI・スコアリング
venues.js                   東京会場マスタ
regional/                   横浜・大阪会場マスタ
data/events.js              東京イベントデータ
data/yokohama/events.js     横浜イベントデータ
data/osaka/events.js        大阪イベントデータ
tools/                      地域別データ生成（Python 3標準ライブラリのみ）
```

## 免責

スコアは公開情報ベースの参考値。実際の需要・交通規制・営業区域のルールは現場の判断を優先すること。
