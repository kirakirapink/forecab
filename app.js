/* FORECAB — スコアリングエンジン + UI */
"use strict";

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

const CATEGORY_LABEL = {
  exhibition: "展示会",
  concert: "ライブ",
  sports: "スポーツ",
  theater: "舞台・クラシック",
  festival: "催事・フェス",
};

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

const AUDIENCE_LABEL = {
  business: "ビジネス客",
  general: "一般客",
  youth: "若年層",
  family: "ファミリー",
  senior_wealthy: "年配・富裕層",
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

function weatherFactor(ev) {
  const wx = (window.TAXI_APP_DATA && window.TAXI_APP_DATA.weather) || {};
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
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function venueOf(ev) {
  return Object.assign({}, window.VENUE_DEFAULT, window.VENUES[ev.venue] || {});
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

function scoreEvent(ev) {
  const v = venueOf(ev);
  const att = Math.max(1, Number(ev.attendance) || 1);
  const exit = EXIT_RATE[ev.category] ?? 0.5;
  const useRate = TAXI_USE_RATE[ev.audience] ?? 0.06;
  const access = ACCESS_FACTOR[v.station_access] ?? 1.0;
  const timeF = timeWindowFactor(ev);
  const longProb = clamp(v.long_distance ?? 0.3, 0, 1);
  const longF = 1.0 + 0.5 * longProb;
  const wx = weatherFactor(ev);

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

/* ---------- データ準備 ---------- */

const STALE_HOURS = 26;
const RAW = (window.TAXI_APP_DATA && window.TAXI_APP_DATA.events) || [];
const EVENTS = RAW.map(ev => {
  const sc = scoreEvent(ev);
  return Object.assign({}, ev, { score: sc, venueInfo: venueOf(ev) });
});

const DATES = [...new Set(EVENTS.map(e => e.date))].sort();

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function defaultDate() {
  const today = todayISO();
  if (DATES.includes(today)) return today;
  const future = DATES.find(d => d > today);
  return future || DATES[DATES.length - 1] || today;
}

const state = {
  date: defaultDate(),
  sort: "score",          // score | time
  category: new Set(),     // 空 = 全部
  area: new Set(),
  userLatLng: null,
};

let map = null;
let markerLayerGroup = null;
let zoneLayerGroup = null;
let userLocationMarker = null;
let mapInitialized = false;

/**
 * Haversine formulaで2点間の距離をkm単位で返す。
 * @param {{lat: number, lng: number}} a 始点の緯度経度。
 * @param {{lat: number, lng: number}} b 終点の緯度経度。
 * @returns {number} 2点間の距離(km)。
 */
function haversineKm(a, b) {
  const lat1 = Number(a.lat);
  const lng1 = Number(a.lng);
  const lat2 = Number(b.lat);
  const lng2 = Number(b.lng);
  if (![lat1, lng1, lat2, lng2].every(Number.isFinite)) return NaN;

  const toRad = deg => deg * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const sLat1 = toRad(lat1);
  const sLat2 = toRad(lat2);
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(sLat1) * Math.cos(sLat2) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

/**
 * 会場マーカーとホットゾーン円を全削除し、描画用レイヤーを作り直す。
 * @returns {void}
 */
function clearMapLayers() {
  if (!map || !window.L) return;
  if (markerLayerGroup) map.removeLayer(markerLayerGroup);
  if (zoneLayerGroup) map.removeLayer(zoneLayerGroup);
  zoneLayerGroup = L.layerGroup().addTo(map);
  markerLayerGroup = L.layerGroup().addTo(map);
}

/**
 * state.dateにイベントがある会場だけを地図へ描画する。
 * @returns {void}
 */
function renderMap() {
  if (!map || !window.L) return;
  clearMapLayers();

  const evs = eventsOfDay();
  if (evs.length === 0 || !window.VENUES) return;

  Object.entries(window.VENUES).forEach(([venueName, venue]) => {
    const lat = Number(venue.lat);
    const lng = Number(venue.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

    const venueEvents = evs.filter(e => e.venue === venueName);
    if (venueEvents.length === 0) return;

    const score = Math.max(...venueEvents.map(e => e.score.total));
    const color = score >= 70 ? "#d32f2f"
      : score >= 50 ? "#f57c00"
      : score >= 30 ? "#fbc02d"
      : "#757575";
    const point = [lat, lng];

    if (score >= 30) {
      L.circle(point, {
        radius: 300 + score * 15,
        fillColor: color,
        fillOpacity: 0.10 + score / 400,
        stroke: false,
      }).addTo(zoneLayerGroup);
    }

    const eventNames = venueEvents.map(e => esc(e.name)).join("<br>");
    const eventTimes = venueEvents.map(e => `${esc(e.start)}-${esc(e.end)}`).join("<br>");
    const marker = L.circleMarker(point, {
      radius: Math.round(8 + score / 100 * 6),
      color,
      fillColor: color,
      fillOpacity: 0.85,
      weight: 2,
    }).addTo(markerLayerGroup);

    marker.bindPopup(`
      <strong>${esc(venueName)}</strong><br>
      ${eventNames}<br>
      スコア ${score}<br>
      ${eventTimes}
    `);
  });
}

/**
 * 現在地がある場合、イベントカードに現在地から会場までの距離を反映する。
 * @returns {void}
 */
function updateDistances() {
  document.querySelectorAll(".event-card[data-id]").forEach(card => {
    const venueEl = card.querySelector(".card-venue");
    if (!venueEl) return;

    let label = venueEl.querySelector(".distance-label");
    if (!label) {
      label = document.createElement("span");
      label.className = "distance-label";
      venueEl.appendChild(label);
    }

    if (!state.userLatLng) {
      label.hidden = true;
      label.textContent = "";
      return;
    }

    const ev = EVENTS.find(e => e.id === card.dataset.id);
    const lat = Number(ev && ev.venueInfo && ev.venueInfo.lat);
    const lng = Number(ev && ev.venueInfo && ev.venueInfo.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      label.hidden = true;
      label.textContent = "";
      return;
    }

    const km = haversineKm(state.userLatLng, { lat, lng });
    if (!Number.isFinite(km)) {
      label.hidden = true;
      label.textContent = "";
      return;
    }

    label.hidden = false;
    label.textContent = `あなたから ${km.toFixed(1)} km`;
  });
}

/**
 * Leaflet地図を1回だけ初期化し、現在地ボタンと保存済み位置を接続する。
 * @returns {void}
 */
function initVenueMap() {
  if (mapInitialized || !window.L || !document.getElementById("venue-map")) return;
  mapInitialized = true;
  map = L.map("venue-map").setView([35.681, 139.767], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  clearMapLayers();
  renderMap();

  const locationBtn = document.getElementById("get-location-btn");
  const errorEl = document.getElementById("location-error");
  const markerOptions = {
    radius: 8,
    color: "#1e88e5",
    fillColor: "#1e88e5",
    fillOpacity: 0.9,
  };

  try {
    const saved = sessionStorage.getItem("userLatLng");
    if (saved) {
      const parsed = JSON.parse(saved);
      const lat = Number(parsed.lat);
      const lng = Number(parsed.lng);
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        state.userLatLng = { lat, lng };
        if (userLocationMarker) map.removeLayer(userLocationMarker);
        userLocationMarker = L.circleMarker([lat, lng], markerOptions).addTo(map);
        updateDistances();
      }
    }
  } catch (e) {
    try {
      sessionStorage.removeItem("userLatLng");
    } catch (err) {}
  }

  if (!locationBtn) return;
  locationBtn.addEventListener("click", () => {
    if (errorEl) errorEl.textContent = "";
    if (!navigator.geolocation) {
      if (errorEl) errorEl.textContent = "位置取得に失敗";
      return;
    }

    navigator.geolocation.getCurrentPosition(position => {
      const lat = position.coords.latitude;
      const lng = position.coords.longitude;
      state.userLatLng = { lat, lng };
      try {
        sessionStorage.setItem("userLatLng", JSON.stringify(state.userLatLng));
      } catch (e) {
        // 保存できない環境でも現在セッションの表示は継続する。
      }
      if (userLocationMarker) map.removeLayer(userLocationMarker);
      userLocationMarker = L.circleMarker([lat, lng], markerOptions).addTo(map);
      map.setView([lat, lng], 13);
      updateDistances();
    }, () => {
      if (errorEl) errorEl.textContent = "位置取得に失敗";
    });
  });
}

/* ---------- レンダリング ---------- */

const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

function dateLabel(iso) {
  const d = new Date(iso + "T00:00:00");
  return { md: `${d.getMonth() + 1}/${d.getDate()}`, wd: WEEKDAYS[d.getDay()], dow: d.getDay() };
}

function starsHtml(stars) {
  let html = "";
  for (let i = 1; i <= 5; i++) {
    const fill = clamp(stars - (i - 1), 0, 1) * 100;
    html += `<span class="star"><span class="star-fill" style="width:${fill}%">★</span><span class="star-bg">★</span></span>`;
  }
  return `<span class="stars" title="${stars}/5">${html}</span>`;
}

function renderFreshnessBanner() {
  const el = document.getElementById("freshness-banner");
  const meta = window.TAXI_APP_DATA || {};
  const gen = new Date(meta.generated_at);

  if (!meta.generated_at || isNaN(gen.getTime())) {
    el.textContent = "⚠ データの更新時刻が確認できません。表示内容が古い可能性があります";
    el.hidden = false;
    return;
  }

  if (Date.now() - gen.getTime() > STALE_HOURS * 3600 * 1000) {
    const mdhm = `${gen.getMonth() + 1}/${gen.getDate()} ${String(gen.getHours()).padStart(2, "0")}:${String(gen.getMinutes()).padStart(2, "0")}`;
    el.innerHTML = esc(`⚠ データが更新されていません（最終更新 ${mdhm}）。予報が古い可能性があります`);
    el.hidden = false;
    return;
  }

  el.hidden = true;
}

function renderTabs() {
  const el = document.getElementById("date-tabs");
  const today = todayISO();
  el.innerHTML = DATES.map(d => {
    const { md, wd, dow } = dateLabel(d);
    const cls = [
      "date-tab",
      d === state.date ? "active" : "",
      dow === 0 ? "sun" : dow === 6 ? "sat" : "",
    ].join(" ");
    const todayMark = d === today ? `<span class="today-mark">TODAY</span>` : "";
    return `<button class="${cls}" data-date="${d}">${todayMark}<span class="md">${md}</span><span class="wd">(${wd})</span></button>`;
  }).join("");
  el.querySelectorAll("button").forEach(b =>
    b.addEventListener("click", () => { state.date = b.dataset.date; render(); })
  );
}

function eventsOfDay() {
  return EVENTS.filter(e => e.date === state.date);
}

function filteredEvents() {
  return eventsOfDay().filter(e =>
    (state.category.size === 0 || state.category.has(e.category)) &&
    (state.area.size === 0 || state.area.has(e.venueInfo.area))
  );
}

function renderSummary() {
  const el = document.getElementById("summary");
  const top = [...eventsOfDay()].sort((a, b) => b.score.total - a.score.total).slice(0, 3);
  if (top.length === 0) {
    el.innerHTML = `<div class="empty">この日のイベントデータがありません</div>`;
    return;
  }
  el.innerHTML = `
    <h2 class="section-title"><span class="en">Priority</span>重点3件</h2>
    <div class="best3">` +
    top.map((e, i) => `
      <button class="best-card" data-id="${e.id}">
        <div class="best-rank">${String(i + 1).padStart(2, "0")}</div>
        <div class="best-body">
          <div class="best-name">${esc(e.name)}</div>
          <div class="best-meta">${esc(e.venue)}</div>
          <div class="best-aim">${esc(aimText(e))}</div>
        </div>
        <div class="best-score">${e.score.total}</div>
      </button>`).join("") +
    `</div>`;
  el.querySelectorAll(".best-card").forEach(b =>
    b.addEventListener("click", () => {
      const card = document.querySelector(`.event-card[data-id="${b.dataset.id}"]`);
      if (card) {
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.classList.add("flash");
        setTimeout(() => card.classList.remove("flash"), 1500);
      }
    })
  );
}

function renderHeatmap() {
  const el = document.getElementById("heatmap");
  const evs = eventsOfDay();
  if (evs.length === 0) { el.innerHTML = ""; return; }

  const BIN = 30, NBINS = Math.ceil((26 * 60) / BIN); // 0:00〜26:00を30分刻み
  const bins = new Array(NBINS).fill(0);
  evs.forEach(e => {
    demandWindows(e, e.score.total / 100).forEach(w => {
      for (let b = Math.floor(w.from / BIN); b <= Math.floor((w.to - 1) / BIN); b++) {
        if (b >= 0 && b < NBINS) bins[b] += w.w;
      }
    });
  });

  let lo = bins.findIndex(v => v > 0), hi = NBINS - 1;
  while (hi > 0 && bins[hi] === 0) hi--;
  if (lo < 0) { el.innerHTML = ""; return; }
  lo = Math.max(0, lo - 1); hi = Math.min(NBINS - 1, hi + 1);

  const max = Math.max(...bins, 0.001);
  const peakBin = bins.indexOf(Math.max(...bins));

  let bars = "", labels = "";
  for (let b = lo; b <= hi; b++) {
    const h = Math.round((bins[b] / max) * 100);
    const heat = bins[b] / max;
    const cls = heat > 0.75 ? "hot" : heat > 0.4 ? "warm" : "cool";
    bars += `<div class="hm-bar-wrap" title="${fmtMin(b * BIN)} 需要 ${Math.round(heat * 100)}%"><div class="hm-bar ${cls}" style="height:${Math.max(h, 3)}%"></div></div>`;
    labels += `<div class="hm-label">${(b * BIN) % 120 === 0 ? fmtMin(b * BIN).replace(":00", "") + "時" : ""}</div>`;
  }

  // 今日を表示中なら現在時刻のラインを重ねる
  const rangeLo = lo * BIN, rangeHi = (hi + 1) * BIN, rangeSpan = rangeHi - rangeLo;
  let nowLine = "";
  if (state.date === todayISO()) {
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    if (nowMin >= rangeLo && nowMin <= rangeHi) {
      const pct = ((nowMin - rangeLo) / rangeSpan) * 100;
      nowLine = `<div class="hm-now" style="left:${pct.toFixed(2)}%"><span>NOW</span></div>`;
    }
  }

  // 天気帯: 6時間毎の降水確率を時間軸に沿って表示
  const fc = ((window.TAXI_APP_DATA && window.TAXI_APP_DATA.weather) || {})[state.date];
  let wxStrip = "";
  if (fc && Array.isArray(fc.hourly) && fc.hourly.length > 0) {
    const slices = fc.hourly
      .map(h => {
        const s = Math.max(rangeLo, h.start_min);
        const e = Math.min(rangeHi, h.end_min);
        if (e <= s) return "";
        const left = ((s - rangeLo) / rangeSpan) * 100;
        const width = ((e - s) / rangeSpan) * 100;
        const pop = Number(h.pop) || 0;
        const cls = pop >= 60 ? "wx-rain-heavy" : pop >= 30 ? "wx-rain-mid" : pop >= 10 ? "wx-rain-light" : "wx-clear";
        const icon = pop >= 30 ? "☔" : pop >= 10 ? "☁" : "☀";
        const lbl = pop >= 10 ? `${icon} ${pop}%` : icon;
        const title = `${fmtMin(h.start_min)}-${fmtMin(h.end_min % 1440 || 1440)} 降水${pop}%`;
        return `<div class="wx-slice ${cls}" style="left:${left.toFixed(2)}%;width:${width.toFixed(2)}%" title="${title}"><span class="wx-lbl">${lbl}</span></div>`;
      })
      .join("");
    if (slices) wxStrip = `<div class="hm-weather">${slices}</div>`;
  } else if (fc && fc.pop_max != null) {
    // 時間帯別データが無い（週間予報範囲）→ 1日全体の最大降水確率を1枚で表示
    const pop = Number(fc.pop_max) || 0;
    const cls = pop >= 60 ? "wx-rain-heavy" : pop >= 30 ? "wx-rain-mid" : pop >= 10 ? "wx-rain-light" : "wx-clear";
    const icon = pop >= 30 ? "☔" : pop >= 10 ? "☁" : "☀";
    const lbl = pop >= 10 ? `${icon} 日中最大 ${pop}%` : `${icon} 概ね晴れ`;
    wxStrip = `<div class="hm-weather"><div class="wx-slice wx-fallback ${cls}" style="left:0%;width:100%" title="日中最大降水${pop}%"><span class="wx-lbl">${lbl}</span></div></div>`;
  }

  el.innerHTML = `
    <h2 class="section-title"><span class="en">Demand Timeline</span>時間帯別需要指数
      <span class="peak-note">ピーク ${fmtMin(peakBin * BIN)}前後</span>
    </h2>
    ${wxStrip}
    <div class="hm-chart">${bars}${nowLine}</div>
    <div class="hm-labels">${labels}</div>`;
}

function renderControls() {
  const el = document.getElementById("controls");
  const cats = [...new Set(eventsOfDay().map(e => e.category))];
  const areas = [...new Set(eventsOfDay().map(e => e.venueInfo.area))];

  const chip = (val, label, set, kind) =>
    `<button class="chip ${set.has(val) ? "on" : ""}" data-kind="${kind}" data-val="${esc(val)}">${esc(label)}</button>`;

  el.innerHTML = eventsOfDay().length === 0 ? "" : `
    <div class="control-row">
      <div class="sort-toggle">
        <button class="sort-btn ${state.sort === "score" ? "on" : ""}" data-sort="score">スコア順</button>
        <button class="sort-btn ${state.sort === "time" ? "on" : ""}" data-sort="time">時間順</button>
      </div>
    </div>
    <div class="chip-row">${cats.map(c => chip(c, CATEGORY_LABEL[c] || c, state.category, "category")).join("")}</div>
    <div class="chip-row">${areas.map(a => chip(a, a, state.area, "area")).join("")}</div>`;

  el.querySelectorAll(".sort-btn").forEach(b =>
    b.addEventListener("click", () => { state.sort = b.dataset.sort; render(); })
  );
  el.querySelectorAll(".chip").forEach(b =>
    b.addEventListener("click", () => {
      const set = b.dataset.kind === "category" ? state.category : state.area;
      set.has(b.dataset.val) ? set.delete(b.dataset.val) : set.add(b.dataset.val);
      render();
    })
  );
}

function breakdownHtml(e) {
  const rows = e.score.breakdown.map(b => `
    <div class="bd-row">
      <div class="bd-label">${b.label}</div>
      <div class="bd-bar"><div class="bd-fill" style="width:${b.strength.toFixed(0)}%"></div></div>
      <div class="bd-score">${esc(b.value)}</div>
      <div class="bd-hint">${esc(b.hint)}</div>
    </div>`).join("");
  const v = e.venueInfo;
  const dest = (v.typical_destinations || []).length
    ? `<div class="detail-row"><span class="detail-key">主要行き先</span>${v.typical_destinations.map(d => `<span class="dest">${esc(d)}</span>`).join("")}</div>` : "";
  const tips = v.tips ? `<div class="detail-row"><span class="detail-key">現場メモ</span>${esc(v.tips)}</div>` : "";
  const notes = e.notes ? `<div class="detail-row"><span class="detail-key">備考</span>${esc(e.notes)}</div>` : "";
  const peak = Math.round(e.score.peakDemand);
  const idx = Math.round(e.score.demandIndex);
  return `
    <div class="breakdown">
      <div class="bd-title">スコア内訳（乗算モデル：需要指数 ${idx} ／ ピーク同時需要 約${peak.toLocaleString()}人）</div>
      ${rows}
    </div>
    ${dest}${tips}${notes}`;
}

function renderList() {
  const el = document.getElementById("event-list");
  const evs = filteredEvents();
  if (eventsOfDay().length === 0) {
    el.innerHTML = `<div class="empty-big">この日のデータがありません。<br>
      <code>python3 tools/make_demo_data.py</code> でデモデータを再生成できます。</div>`;
    return;
  }
  if (evs.length === 0) {
    el.innerHTML = `<div class="empty">フィルタに合うイベントがありません</div>`;
    return;
  }
  const sorted = [...evs].sort((a, b) =>
    state.sort === "score"
      ? b.score.total - a.score.total
      : toMin(a.start) - toMin(b.start)
  );
  el.innerHTML = sorted.map(e => `
    <details class="event-card" data-id="${e.id}">
      <summary>
        <div class="card-grid">
          <div class="card-score">
            <div class="score-num">${e.score.total}</div>
            ${starsHtml(e.score.stars)}
          </div>
          <div class="card-info">
            <div class="card-top-row">
              <span class="cat-badge cat-${e.category}">${CATEGORY_LABEL[e.category] || esc(e.category)}</span>
              <span class="card-time">${e.start}–${e.end}</span>
              <span class="expand-hint">詳細</span>
            </div>
            <div class="card-name">${esc(e.name)}</div>
            <div class="card-venue">${esc(e.venue)}<span class="card-area">${esc(e.venueInfo.area)}</span></div>
            <div class="card-facts">約${Number(e.attendance).toLocaleString()}人<span class="sep">／</span>${AUDIENCE_LABEL[e.audience] || esc(e.audience)}</div>
            <div class="card-aim">${esc(aimText(e))}</div>
          </div>
        </div>
      </summary>
      ${breakdownHtml(e)}
    </details>`).join("");
}

function renderFooter() {
  const el = document.getElementById("footer");
  const meta = window.TAXI_APP_DATA || {};
  const src = meta.source === "demo"
    ? "表示中のイベントはデモデータ（架空）です"
    : `データソース: ${esc(meta.source || "不明")}`;

  // 表示中の日付の気象を出す（今日の場合「本日」、それ以外は日付）
  const wx = (meta.weather || {})[state.date];
  let wxLine = "";
  if (wx) {
    const w = (wx.weather || "").replace(/[\s　]+/g, " ").trim();
    const pop = Number.isFinite(Number(wx.pop_max)) ? `降水${wx.pop_max}%` : "";
    const t = [];
    if (wx.temp_max != null) t.push(`最高${wx.temp_max}℃`);
    if (wx.temp_min != null) t.push(`最低${wx.temp_min}℃`);
    const isToday = state.date === todayISO();
    wxLine = `<div class="footer-wx">${isToday ? "本日" : esc(state.date)}の予報 ／ ${esc(w || "")} ／ ${esc(pop)} ／ ${esc(t.join(" "))}</div>`;
  }

  el.innerHTML = `${wxLine}<span class="footer-brand">FORECAB</span> ${src} ・ 更新 ${esc(meta.generated_at || "-")}<br>
    スコアは公開情報ベースの参考値です。実際の需要・交通規制・営業区域は現場の判断を優先してください。`;
}

function render() {
  renderFreshnessBanner();
  renderTabs();
  renderSummary();
  renderHeatmap();
  renderControls();
  renderList();
  renderFooter();
}

/**
 * 既存UIの再描画後に地図と距離表示を同期する。
 * @returns {void}
 */
const renderWithMap = function () {
  renderBase();
  renderMap();
  updateDistances();
};

const renderBase = render;
render = renderWithMap;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initVenueMap, { once: true });
} else {
  initVenueMap();
}

render();
