/* FORECAB — ブラウザ / Node 共用スコアリングエンジン */
"use strict";

(function (root) {
/* ===========================================================
 * スコアリングモデル（乗算式）→ 星0〜5
 *
 *   需要指数 = 集客 × 退場集中度 × タクシー利用率 × 駅事情
 *            × 時間プレミアム × 長距離プレミアム × 気象プレミアム
 *
 *     集客           : イベント来場者数の絶対値
 *     退場集中度     : ピーク前後の同時退場比率（カテゴリ別）
 *     タクシー利用率 : 客層別の退場者→タクシー流入率
 *     駅事情         : 駅遠ほど捕捉率が上がる（near<mid<far）
 *     時間プレミアム : 終演〜終電マージン。深夜ほど確実にタクシー
 *     長距離プレミアム: 1.0 + 0.5 × 長距離期待度。空港・遠郊外需要の単価補正
 *     気象プレミアム : 気象庁予報を反映。雨1.4 / 雪1.8 / 猛暑1.1 / 極寒1.1
 *
 *   表示スコア(0〜100)は需要指数を対数正規化したもの。
 *   needs と revenue の両方を「需要 × 価値」の乗算で表現するのが旧加点式との違い。
 * =========================================================== */

// 退場集中度: ピーク時に同時に出る観客の比率
const EXIT_RATE = {
  sports: 0.85,      // 試合終了で一斉退場
  theater: 0.80,    // 拍手の後にまとまって退場
  concert: 0.75,    // アンコール後にまとまる
  festival: 0.35,   // 引け際にばらつく
  exhibition: 0.18, // 終日出入りで分散
};

const EXIT_HINT = {
  sports: "試合終了で一斉退場",
  theater: "拍手の後にまとまって退場",
  concert: "アンコール後にまとまる",
  festival: "引け際にばらつく",
  exhibition: "終日出入りで分散",
};

// 退場者のうちタクシーに流れる比率（客層別）
const TAXI_USE_RATE = {
  senior_wealthy: 0.45, // 歌舞伎・オペラ・能の常連は確実
  business: 0.22,       // 経費移動・手荷物・時間価値
  family: 0.10,         // 子連れ短距離需要
  general: 0.06,        // 通常の電車優位層
  youth: 0.03,          // 電車・徒歩中心
};

const AUDIENCE_HINT = {
  senior_wealthy: "年配・富裕層は利用率最高クラス",
  business: "経費移動・手荷物でタクシー比率高",
  family: "子連れ・荷物で短距離需要",
  general: "利用率は限定的。規模で稼ぐ",
  youth: "電車中心で利用率低め",
};

// 駅事情によるタクシー捕捉率。駅遠ほど高い
const ACCESS_FACTOR = { near: 0.55, mid: 1.0, far: 1.5 };
const ACCESS_LABEL = {
  near: "駅近で電車に流れやすい",
  mid: "駅やや遠 or 終演時大混雑",
  far: "駅遠・路線弱でタクシー有利",
};

// 気象庁weatherCode先頭1桁 → 係数。雨300番台=1.4、雪400番台=1.8
function _codeFactor(code) {
  if (!code) return null;
  const c = String(code);
  if (c.startsWith("4")) return { f: 1.8, hint: "雪予報でタクシー一択" };
  if (c.startsWith("3")) return { f: 1.4, hint: "雨予報で電車・徒歩を回避" };
  return null;
}

function hourlySliceFor(fc, minOfDay) {
  const hourly = fc && fc.hourly;
  if (!Array.isArray(hourly) || hourly.length === 0) return null;
  return hourly.find(h => {
    const start = Number(h.start_min);
    const end = Number(h.end_min);
    return Number.isFinite(start) && Number.isFinite(end) && start <= minOfDay && minOfDay < end;
  }) || null;
}

function weatherFactor(ev, weatherDict) {
  const wx = weatherDict || {};
  const fc = wx[ev.date];
  if (!fc) return { f: 1.0, hint: "予報なし（基準値）", weather: null, pop: null };

  let f = 1.0;
  const parts = [];
  const cf = _codeFactor(fc.weather_code);
  const pop = Number(fc.pop_max);
  const tmax = Number(fc.temp_max);
  const tmin = Number(fc.temp_min);
  const popN = Number.isFinite(pop) ? pop : 0;
  const startMin = toMin(ev.start);
  const endMin = toMin(ev.end);
  const exitPeakMin = endMin < startMin ? 1439 : endMin;
  const slice = hourlySliceFor(fc, exitPeakMin);
  const slicePop = slice ? Number(slice.pop) : NaN;
  const useSlicePop = Number.isFinite(slicePop);
  const effPop = useSlicePop ? slicePop : popN;
  const sliceLabel = useSlicePop ? `${fmtMin(slice.start_min)}-${fmtMin(slice.end_min % 1440 || 1440)}` : null;

  if (cf && (!slice || slicePop >= 30)) {
    f = cf.f;
    parts.push(cf.hint + `（${sliceLabel ? `${sliceLabel} ` : ""}降水${effPop}%）`);
  } else if (effPop >= 60) {
    f = 1.3;
    parts.push(sliceLabel ? `${sliceLabel} 降水${effPop}%で電車回避層増` : `降水確率${effPop}%で電車回避層増`);
  } else if (effPop >= 30) {
    f = 1.1;
    parts.push(sliceLabel ? `${sliceLabel} 降水${effPop}%でやや増` : `降水確率${effPop}%でやや増`);
  } else {
    const w = (fc.weather || "").replace(/[\s　]+/g, " ").trim();
    parts.push(w ? `${w.slice(0, 18)} / ${sliceLabel ? `${sliceLabel} ` : ""}降水${effPop}%` : (sliceLabel ? `${sliceLabel} 降水${effPop}%` : "標準"));
  }

  if (Number.isFinite(tmax) && tmax >= 35) { f *= 1.1; parts.push(`最高${tmax}℃で駅遠を回避`); }
  if (Number.isFinite(tmin) && tmin <= 0)  { f *= 1.1; parts.push(`最低${tmin}℃で屋外を回避`); }

  f = Math.min(2.0, Number(f.toFixed(2)));
  return { f, hint: parts.join(" / "), weather: fc.weather || null, pop: effPop, tmax, tmin };
}

/* ---------- ユーティリティ ---------- */

function toMin(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}
function fmtMin(min) {
  min = ((min % 1440) + 1440) % 1440;
  return `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
}
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function venueOf(ev, venues, venueDefault) {
  return Object.assign({}, venueDefault, venues[ev.venue] || {});
}

/* ---------- スコアリング ---------- */

// 終演時刻 → 時間プレミアム係数。終電マージンが薄いほど大きい
function timeWindowFactor(ev) {
  if (ev.category === "exhibition") {
    const end = toMin(ev.end);
    if (end < toMin("17:00")) return 0.7;
    if (end < toMin("19:00")) return 0.9;
    return 1.1;
  }
  const startMin = toMin(ev.start);
  const endMin = toMin(ev.end);
  // 終演が日跨ぎ（深夜帯）の場合は終電喪失で最大係数
  if (endMin < startMin) return 2.5;
  const end = endMin;
  if (end < toMin("18:00")) return 0.5;
  if (end < toMin("20:00")) return 0.8;
  if (end < toMin("21:00")) return 1.0;
  if (end < toMin("22:00")) return 1.3;
  if (end < toMin("23:00")) return 1.6;
  if (end < toMin("23:45")) return 2.0;
  return 2.5; // 終電喪失でタクシー一択
}

function timeHint(ev) {
  if (ev.category === "exhibition") {
    const end = toMin(ev.end);
    if (end < toMin("17:00")) return "閉場が早く電車優位";
    if (end < toMin("19:00")) return "夕方閉場で需要中程度";
    return "夜閉場で需要が立つ";
  }
  const endMin = toMin(ev.end);
  const startMin = toMin(ev.start);
  if (endMin < startMin) return "深夜帯で終電喪失";
  const end = endMin;
  if (end < toMin("18:00")) return "終演早く電車優位";
  if (end < toMin("20:00")) return "終電まで余裕大";
  if (end < toMin("21:00")) return "終電まで余裕";
  if (end < toMin("22:00")) return "終電2-3h前で需要本格化";
  if (end < toMin("23:00")) return "終電1-2h前で需要強";
  if (end < toMin("23:45")) return "終電怪しい時間帯";
  return "終電喪失でタクシー一択";
}

function scoreEvent(ev, ctx) {
  const v = venueOf(ev, ctx.venues, ctx.venueDefault);
  const att = Math.max(1, Number(ev.attendance) || 1);
  const exit = EXIT_RATE[ev.category] ?? 0.5;
  const useRate = TAXI_USE_RATE[ev.audience] ?? 0.06;
  const access = ACCESS_FACTOR[v.station_access] ?? 1.0;
  const timeF = timeWindowFactor(ev);
  const longProb = clamp(v.long_distance ?? 0.3, 0, 1);
  const longF = 1.0 + 0.5 * longProb;
  const wx = weatherFactor(ev, ctx.weather);

  // ピーク同時タクシー需要(人) = 集客 × 退場集中度 × タクシー利用率 × 駅事情
  const peakDemand = att * exit * useRate * access;
  // 需要指数 = ピーク需要 × 時間プレミアム × 長距離プレミアム × 気象プレミアム
  const demandIndex = peakDemand * timeF * longF * wx.f;
  // 0〜100 へ対数正規化（demandIndex 500 → 約50点、2000 → 約75点、10000 → 上限近傍）
  const total = clamp(-21 + 30 * Math.log10(demandIndex + 1), 0, 100);
  const stars = Math.round((total / 20) * 2) / 2; // 半星刻み

  const destHint = (v.typical_destinations || []).slice(0, 2).join("・") || "標準的な需要";

  return {
    total: Math.round(total),
    stars,
    peakDemand,
    demandIndex,
    weather: wx,
    breakdown: [
      { label: "規模",           strength: clamp(Math.log10(att + 1) / 5, 0, 1) * 100,
        value: `${att.toLocaleString()}人`, hint: "集客の絶対数（対数スケール）" },
      { label: "退場集中度",     strength: exit * 100,
        value: `×${exit.toFixed(2)}`,        hint: EXIT_HINT[ev.category] || "退場の集中度" },
      { label: "客層タクシー率", strength: clamp(useRate / 0.45, 0, 1) * 100,
        value: `×${useRate.toFixed(2)}`,     hint: AUDIENCE_HINT[ev.audience] || "" },
      { label: "駅距離補正",     strength: clamp((access - 0.55) / 0.95, 0, 1) * 100,
        value: `×${access.toFixed(2)}`,      hint: ACCESS_LABEL[v.station_access] || "" },
      { label: "終演時間",       strength: clamp((timeF - 0.5) / 2.0, 0, 1) * 100,
        value: `×${timeF.toFixed(2)}`,       hint: timeHint(ev) },
      { label: "長距離期待",     strength: longProb * 100,
        value: `×${longF.toFixed(2)}`,       hint: destHint },
      { label: "気象プレミアム", strength: clamp((wx.f - 1.0) / 1.0, 0, 1) * 100,
        value: `×${wx.f.toFixed(2)}`,        hint: wx.hint },
    ],
  };
}

/* 狙い目時間帯のテキストと、ヒートマップ用の需要ウィンドウ */
function demandWindows(ev, weight) {
  const s = toMin(ev.start);
  let e = toMin(ev.end);
  if (e <= s) e += 1440; // 日跨ぎ
  if (ev.category === "exhibition") {
    return [
      { from: s, to: e, w: weight * 0.45 },
      { from: e - 60, to: e + 45, w: weight * 0.85 },
    ];
  }
  if (ev.category === "festival") {
    return [
      { from: s, to: e, w: weight * 0.3 },
      { from: e - 30, to: e + 60, w: weight * 0.55 },
    ];
  }
  // 終演集中型（ライブ・スポーツ・舞台）
  return [
    { from: s - 90, to: s - 15, w: weight * 0.35 }, // 開演前の送り込み
    { from: e - 15, to: e + 75, w: weight * 1.0 },  // 終演の波
  ];
}

function aimText(ev) {
  const e = toMin(ev.end);
  if (ev.category === "exhibition") {
    return `常時流入 ${ev.start}–${ev.end} ／ ピーク ${fmtMin(e - 60)}–${fmtMin(e + 30)}`;
  }
  if (ev.category === "festival") {
    return `引け際需要 ${fmtMin(e - 30)}–${fmtMin(e + 60)}`;
  }
  return `終演後需要 ${fmtMin(e - 15)}–${fmtMin(e + 75)}`;
}

root.FORECAB_SCORING = {
  scoreEvent,
  demandWindows,
  aimText,
  venueOf,
  toMin,
  fmtMin,
  clamp,
  EXIT_RATE,
  EXIT_HINT,
  TAXI_USE_RATE,
  AUDIENCE_HINT,
  ACCESS_FACTOR,
  ACCESS_LABEL,
  _codeFactor,
  weatherFactor,
  hourlySliceFor,
  timeWindowFactor,
  timeHint,
};
})(typeof window !== "undefined" ? window : globalThis);
