/* FORECAB — 横浜版 会場マスタ */
"use strict";

window.VENUES = {
  "Kアリーナ横浜": {
    area: "みなとみらい・横浜駅東口", ward: "西区",
    lat: 35.4611, lng: 139.6307,
    station_access: "mid", long_distance: 0.7,
    typical_destinations: ["横浜駅", "羽田空港", "関内・山下公園", "東京都心"],
    tips: "2万人規模の終演後は横浜駅方面の歩道が集中する。周辺の交通規制に従い、高島・みなとみらい側の規制外で構える。"
  },
  "横浜アリーナ": {
    area: "新横浜", ward: "港北区",
    lat: 35.5122, lng: 139.6201,
    station_access: "mid", long_distance: 0.7,
    typical_destinations: ["横浜駅", "羽田空港", "東京都心", "市内ホテル"],
    tips: "終演直後は新横浜駅が混雑する。環状2号線の渋滞と乗降規制を確認し、駅の反対側も候補にする。"
  },
  "横浜スタジアム": {
    area: "関内・日本大通り", ward: "中区",
    lat: 35.4433, lng: 139.6401,
    station_access: "near", long_distance: 0.5,
    typical_destinations: ["横浜駅", "みなとみらい", "市内ホテル", "羽田空港"],
    tips: "試合終了後は関内駅・日本大通り駅へ集中する。延長を見込み、港側や伊勢佐木町側の流しも検討する。"
  },
  "KT Zepp Yokohama": {
    area: "みなとみらい", ward: "西区",
    lat: 35.4590, lng: 139.6268,
    station_access: "near", long_distance: 0.5,
    typical_destinations: ["横浜駅", "関内", "市内ホテル", "川崎方面"],
    tips: "横浜駅に近いが、雨天や遅い終演では短中距離需要が出る。Kアリーナ開催日との重なりを確認する。"
  },
  "ぴあアリーナMM": {
    area: "みなとみらい", ward: "西区",
    lat: 35.4549, lng: 139.6306,
    station_access: "mid", long_distance: 0.6,
    typical_destinations: ["横浜駅", "関内", "市内ホテル", "羽田空港"],
    tips: "桜木町・みなとみらい両駅に分散する。終演時はみなとみらい大通り側の混雑を確認する。"
  },
  "パシフィコ横浜": {
    area: "みなとみらい", ward: "西区",
    lat: 35.4574, lng: 139.6352,
    station_access: "mid", long_distance: 0.8,
    typical_destinations: ["羽田空港", "新横浜駅", "横浜駅", "東京都心"],
    tips: "展示会・学会の閉場前後は荷物の多い出張客が中心。国立大ホールと展示ホールの終了時刻を分けて見る。"
  },
  "日産スタジアム": {
    area: "新横浜・小机", ward: "港北区",
    lat: 35.5100, lng: 139.6064,
    station_access: "far", long_distance: 0.6,
    typical_destinations: ["新横浜駅", "横浜駅", "川崎方面", "東京都心"],
    tips: "大規模開催時は周辺道路の規制が強い。規制区域と乗降場所を必ず確認し、小机・新横浜の分散退場を読む。"
  },
  "Yokohama BUNTAI": {
    area: "関内", ward: "中区",
    lat: 35.4397, lng: 139.6332,
    station_access: "near", long_distance: 0.4,
    typical_destinations: ["横浜駅", "みなとみらい", "市内ホテル"],
    tips: "関内駅至近。駅行列が伸びる大規模興行と雨天時を優先し、周辺の短距離回転を狙う。"
  }
};

window.VENUE_DEFAULT = {
  area: "横浜市内", ward: "横浜市",
  lat: null, lng: null,
  station_access: "mid", long_distance: 0.5,
  typical_destinations: ["横浜駅", "市内主要駅", "市内ホテル"],
  tips: "会場の公式案内と当日の交通規制を確認してください。"
};
