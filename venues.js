// 会場マスタ
// スコアリングに使う会場ごとの特性データ。会場を追加したいときはここに足す。
//
// station_access: 最寄り駅からの近さ。タクシー需要は駅が「遠い/混む」ほど上がる
//   "near" = 駅直結・徒歩3分以内 / "mid" = 徒歩5〜10分 or 駅が大混雑する / "far" = 徒歩10分超・路線が弱い
// long_distance: 長距離乗車（空港・近県・都心横断）が出る確率の肌感 0.0〜1.0
// typical_destinations: 終演後によく出る行き先
// tips: 待機場所・付け方のコツ（デモ用の一般論。実運用では友人の経験で上書きする）

window.VENUES = {
  "東京ビッグサイト": {
    area: "湾岸（有明）",
    ward: "江東区",
    lat: 35.6298, lng: 139.7946,
    station_access: "mid", // りんかい線・ゆりかもめのみ。閉場時は駅が大行列
    long_distance: 0.8,    // 出張ビジネス客 → 羽田・東京駅・都心ホテルが多い
    typical_destinations: ["羽田空港", "東京駅", "都心ホテル（銀座・汐留）", "品川"],
    tips: "閉場30分前から東棟・西棟タクシー乗り場へ。雨天時は駅行列を嫌う客で需要倍増。"
  },
  "東京国際フォーラム": {
    area: "丸の内・有楽町",
    ward: "千代田区",
    lat: 35.6769, lng: 139.7637,
    station_access: "near",
    long_distance: 0.5,
    typical_destinations: ["羽田空港", "都心ホテル", "霞が関・大手町"],
    tips: "駅近だが企業イベント帰りの役員クラスは確実にタクシー。地上広場側の車寄せが狙い目。"
  },
  "東京ドーム": {
    area: "後楽園",
    ward: "文京区",
    lat: 35.7056, lng: 139.7519,
    station_access: "near", // 水道橋・後楽園駅至近。大半は電車に流れる
    long_distance: 0.3,
    typical_destinations: ["新宿・池袋方面", "東京駅", "近隣ホテル"],
    tips: "絶対数が多いので駅近でも一定数は拾える。終了10分前に外周へ。延長戦の有無で時間が読めない点に注意。"
  },
  "国立競技場": {
    area: "千駄ヶ谷・外苑",
    ward: "新宿区",
    lat: 35.6778, lng: 139.7146,
    station_access: "mid", // 駅は複数あるが5万人規模だと全駅が規制入場になる
    long_distance: 0.4,
    typical_destinations: ["新宿", "渋谷", "東京駅方面"],
    tips: "終了直後は外苑周辺が交通規制になりがち。規制線の外側（千駄ヶ谷駅の逆方向）で構える。"
  },
  "明治神宮野球場": {
    area: "外苑前",
    ward: "新宿区",
    lat: 35.6745, lng: 139.7169,
    station_access: "mid",
    long_distance: 0.3,
    typical_destinations: ["渋谷", "新宿", "六本木・麻布"],
    tips: "外苑前駅が混むため青山通りまで歩いて拾う客が多い。スタジアム通り沿いで流すのが有効。"
  },
  "日本武道館": {
    area: "九段下",
    ward: "千代田区",
    lat: 35.6933, lng: 139.7497,
    station_access: "mid",
    long_distance: 0.4,
    typical_destinations: ["東京駅", "新宿", "都心ホテル"],
    tips: "九段下駅は終演後に入場規制レベルで混む。靖国通り沿い・北の丸公園出口側が狙い目。"
  },
  "両国国技館": {
    area: "両国",
    ward: "墨田区",
    lat: 35.6967, lng: 139.7933,
    station_access: "near",
    long_distance: 0.5, // 相撲はタニマチ・年配富裕層が多くタクシー比率が高い
    typical_destinations: ["銀座", "赤坂", "都心ホテル", "東京駅"],
    tips: "本場所中は打ち出し（18時頃）に正面玄関側へ。料亭・銀座方面への中距離が出やすい。"
  },
  "有明アリーナ": {
    area: "湾岸（有明）",
    ward: "江東区",
    lat: 35.6432, lng: 139.7903,
    station_access: "far", // 最寄りから徒歩約10分・路線が細い
    long_distance: 0.6,
    typical_destinations: ["東京駅", "新宿・渋谷方面", "羽田空港"],
    tips: "駅が遠く弱いので湾岸では最もタクシーが出る会場。終演15分前に正面へ。豊洲方面の渋滞は織り込むこと。"
  },
  "サントリーホール": {
    area: "六本木・溜池",
    ward: "港区",
    lat: 35.6665, lng: 139.7406,
    station_access: "mid",
    long_distance: 0.6,
    typical_destinations: ["世田谷・目黒の住宅街", "広尾・麻布", "都心ホテル"],
    tips: "クラシック客は年配富裕層でタクシー利用率が非常に高い。アーク森ビル車寄せ周辺で確実に出る。"
  },
  "東京文化会館": {
    area: "上野",
    ward: "台東区",
    lat: 35.7126, lng: 139.7745,
    station_access: "near",
    long_distance: 0.5,
    typical_destinations: ["文京・豊島の住宅街", "都心ホテル", "東京駅"],
    tips: "駅前だがオペラ・バレエ客は高齢富裕層が中心で着物客も多い。正面口に短い列ができる。"
  },
  "Zepp DiverCity": {
    area: "湾岸（お台場）",
    ward: "江東区",
    lat: 35.6251, lng: 139.7753,
    station_access: "mid",
    long_distance: 0.4,
    typical_destinations: ["新橋・東京駅方面", "りんかい線沿線"],
    tips: "若年客中心でタクシー比率は低めだが、湾岸は流しが少ないため競合も少ない。"
  },
  "豊洲PIT": {
    area: "豊洲",
    ward: "江東区",
    lat: 35.6489, lng: 139.7866,
    station_access: "far",
    long_distance: 0.3,
    typical_destinations: ["豊洲駅", "東京駅方面", "月島・勝どき"],
    tips: "駅から遠く、終演が遅い日は駅までの短距離需要がまとまって出る。回転で稼ぐ会場。"
  },
  "幕張メッセ": {
    area: "千葉（幕張）",
    ward: "千葉市",
    lat: 35.6480, lng: 140.0344,
    station_access: "mid",
    long_distance: 0.7,
    typical_destinations: ["東京駅", "羽田空港", "舞浜・浦安"],
    tips: "都外だが大型展示会では都内への長距離が出る。営業区域の扱いに注意（迎車・帰り便中心）。"
  },
  "歌舞伎座": {
    area: "銀座・東銀座",
    ward: "中央区",
    lat: 35.6691, lng: 139.7672,
    station_access: "near",
    long_distance: 0.7,
    typical_destinations: ["世田谷・港区の住宅街", "都心ホテル（銀座・丸の内）", "築地・湾岸エリア"],
    tips: "1階桟敷席2万円帯の常連客は決まったタクシーを指名する傾向。木挽町広場側出口に礼装で構える。夜の部21時前後が勝負。"
  },
  "新国立劇場（オペラパレス）": {
    area: "初台",
    ward: "渋谷区",
    lat: 35.6839, lng: 139.6864,
    station_access: "mid",
    long_distance: 0.6,
    typical_destinations: ["世田谷・目黒の住宅街", "都心ホテル", "渋谷・新宿"],
    tips: "京王新線初台駅から地下通路が長く、オペラ・バレエの高齢富裕層は確実にタクシー利用。甲州街道側の正面車寄せで待機。21〜22時台が勝負。"
  },
  "新国立劇場（中劇場）": {
    area: "初台",
    ward: "渋谷区",
    lat: 35.6839, lng: 139.6864,
    station_access: "mid",
    long_distance: 0.5,
    typical_destinations: ["世田谷・目黒の住宅街", "都心ホテル", "渋谷・新宿"],
    tips: "現代演劇・ダンスは中年層中心。オペラパレスと同じ車寄せを共有。"
  },
  "新国立劇場（小劇場）": {
    area: "初台",
    ward: "渋谷区",
    lat: 35.6839, lng: 139.6864,
    station_access: "mid",
    long_distance: 0.4,
    typical_destinations: ["都心ホテル", "渋谷・新宿"],
    tips: "小規模公演。観客は若手中心で電車利用も多い。"
  },
  "都内学術集会会場": {
    area: "都内（学会会場）",
    ward: "千代田・港・新宿等",
    lat: null, lng: null,
    station_access: "mid",
    long_distance: 0.7,
    typical_destinations: ["羽田空港", "東京駅", "都心ホテル"],
    tips: "医学会など専門職向け学術集会。地方からの参加医師が中心で、羽田・東京駅方面の中距離乗車が典型。開催ホテルや東京国際フォーラム周辺で構える。"
  }
};

// 未知の会場が来たときのデフォルト特性（CSV運用で会場マスタにない会場を許容するため）
window.VENUE_DEFAULT = {
  area: "その他",
  ward: "",
  lat: null, lng: null,
  station_access: "mid",
  long_distance: 0.3,
  typical_destinations: [],
  tips: ""
};
