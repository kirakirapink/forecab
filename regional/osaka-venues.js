/* FORECAB — 大阪版 会場マスタ */
"use strict";

window.VENUES = {
  "京セラドーム大阪": {
    area: "ドーム前・大正", ward: "西区",
    lat: 34.6692, lng: 135.4761,
    station_access: "mid", long_distance: 0.6,
    typical_destinations: ["梅田", "難波", "新大阪駅", "市内ホテル"],
    tips: "終演・試合終了後はドーム前と大正駅に集中する。周辺規制を確認し、千代崎・境川側の流れも見る。"
  },
  "大阪城ホール": {
    area: "大阪城公園", ward: "中央区",
    lat: 34.6896, lng: 135.5308,
    station_access: "mid", long_distance: 0.6,
    typical_destinations: ["梅田", "難波", "新大阪駅", "京橋"],
    tips: "大阪城公園駅・大阪ビジネスパーク駅へ分散する。城見通り側の混雑と規制を確認する。"
  },
  "Zepp Namba": {
    area: "難波・大国町", ward: "浪速区",
    lat: 34.6596, lng: 135.5016,
    station_access: "mid", long_distance: 0.5,
    typical_destinations: ["梅田", "心斎橋", "天王寺", "市内ホテル"],
    tips: "終演が遅い日は難波方面への短中距離が出る。なんばパークス周辺の流し需要と合わせて見る。"
  },
  "Zepp Osaka Bayside": {
    area: "桜島・ベイエリア", ward: "此花区",
    lat: 34.6655, lng: 135.4323,
    station_access: "mid", long_distance: 0.7,
    typical_destinations: ["梅田", "難波", "新大阪駅", "市内ホテル"],
    tips: "JRゆめ咲線への集中とUSJ退園客が重なる。桜島駅周辺の乗降ルールと湾岸側の渋滞を確認する。"
  },
  "インテックス大阪": {
    area: "南港", ward: "住之江区",
    lat: 34.6380, lng: 135.4165,
    station_access: "far", long_distance: 0.8,
    typical_destinations: ["新大阪駅", "梅田", "難波", "関西空港"],
    tips: "大型展示会の閉場前後は出張客と荷物需要が集中する。中ふ頭駅の混雑と会場別の閉場時刻を確認する。"
  },
  "フェスティバルホール": {
    area: "中之島・肥後橋", ward: "北区",
    lat: 34.6925, lng: 135.4963,
    station_access: "near", long_distance: 0.6,
    typical_destinations: ["梅田", "新大阪駅", "市内ホテル", "北摂方面"],
    tips: "駅直結だがクラシック・歌謡公演はタクシー利用率が高い。終演時の中之島フェスティバルタワー車寄せを確認する。"
  },
  "オリックス劇場": {
    area: "本町・四ツ橋", ward: "西区",
    lat: 34.6788, lng: 135.4938,
    station_access: "mid", long_distance: 0.5,
    typical_destinations: ["梅田", "難波", "新大阪駅", "市内ホテル"],
    tips: "四ツ橋・本町へ分散する。終演後は新町側から幹線道路へ出る客の流れを見る。"
  },
  "グランキューブ大阪": {
    area: "中之島", ward: "北区",
    lat: 34.6898, lng: 135.4863,
    station_access: "mid", long_distance: 0.7,
    typical_destinations: ["新大阪駅", "梅田", "市内ホテル", "伊丹空港"],
    tips: "学会・企業イベントでは出張客の中長距離が期待できる。閉会時刻とリーガロイヤルホテル側の車寄せを確認する。"
  },
  "エディオンアリーナ大阪": {
    area: "難波", ward: "浪速区",
    lat: 34.6613, lng: 135.4999,
    station_access: "near", long_distance: 0.4,
    typical_destinations: ["梅田", "天王寺", "市内ホテル"],
    tips: "難波駅に近いため、大規模興行・雨天・遅い終了を優先する。周辺の恒常的な流し需要と合わせて判断する。"
  }
};

window.VENUE_DEFAULT = {
  area: "大阪市内", ward: "大阪市",
  lat: null, lng: null,
  station_access: "mid", long_distance: 0.5,
  typical_destinations: ["梅田", "難波", "新大阪駅", "市内ホテル"],
  tips: "会場の公式案内と当日の交通規制を確認してください。"
};
