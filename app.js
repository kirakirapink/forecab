/* FORECAB — スコアリングエンジン + UI */
"use strict";

const CATEGORY_LABEL = {
  exhibition: "展示会",
  concert: "ライブ",
  sports: "スポーツ",
  theater: "舞台・クラシック",
  festival: "催事・フェス",
};

const AUDIENCE_LABEL = {
  business: "ビジネス客",
  general: "一般客",
  youth: "若年層",
  family: "ファミリー",
  senior_wealthy: "年配・富裕層",
};

const { toMin, fmtMin, clamp } = window.FORECAB_SCORING;
const scoringCtx = () => ({ venues: window.VENUES || {}, venueDefault: window.VENUE_DEFAULT || {}, weather: (window.TAXI_APP_DATA && window.TAXI_APP_DATA.weather) || {} });
const scoreEvent = ev => window.FORECAB_SCORING.scoreEvent(ev, scoringCtx());
const demandWindows = window.FORECAB_SCORING.demandWindows;
const aimText = window.FORECAB_SCORING.aimText;
const venueOf = ev => window.FORECAB_SCORING.venueOf(ev, window.VENUES || {}, window.VENUE_DEFAULT || {});

/* ---------- ユーティリティ ---------- */

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function loadFeedback() {
  try {
    const raw = localStorage.getItem("forecab_feedback");
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (e) {
    return {};
  }
}

function saveFeedback(obj) {
  try {
    localStorage.setItem("forecab_feedback", JSON.stringify(obj));
  } catch (e) {
    // 保存できない環境では実績記録だけ無効化し、表示は継続する。
  }
}

function countdownText(ev, nowMin) {
  const startMin = toMin(ev.start);
  const endMin = toMin(ev.end);
  const endAbs = endMin <= startMin ? endMin + 1440 : endMin;
  const nowAbs = (endMin <= startMin && nowMin <= endMin) ? nowMin + 1440 : nowMin;
  const delta = endAbs - nowAbs;

  if (delta > 0) {
    const h = Math.floor(delta / 60);
    const m = delta % 60;
    return {
      text: `終演まであと${h > 0 ? `${h}時間${m}分` : `${m}分`}`,
      urgent: (0 <= delta && delta <= 45) || (-75 <= delta && delta < 0),
    };
  }

  if (delta >= -75) {
    return {
      text: delta === 0 ? "終演直後" : `終演から${Math.abs(delta)}分経過`,
      urgent: (0 <= delta && delta <= 45) || (-75 <= delta && delta < 0),
    };
  }

  return null;
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
  sort: "score",          // score | time | near | eff
  category: new Set(),     // 空 = 全部
  area: new Set(),
  userLatLng: null,
  locationDenied: false,
};

const NOW_VIEW_LOOKAHEAD_MIN = 90;
const NOW_VIEW_LIMIT = 3;
const NOW_VIEW_REFRESH_MS = 60 * 1000;

let map = null;
let markerLayerGroup = null;
let zoneLayerGroup = null;
let userLocationMarker = null;
let mapInitialized = false;
let nowViewTimer = null;

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

    const eventRows = venueEvents.map(e => `
      <div class="popup-event">
        <button class="popup-jump" data-id="${esc(e.id)}">${esc(e.name)}</button>
        <span>${esc(e.start)}-${esc(e.end)}</span>
      </div>
    `).join("");
    const marker = L.circleMarker(point, {
      radius: Math.round(8 + score / 100 * 6),
      color,
      fillColor: color,
      fillOpacity: 0.85,
      weight: 2,
    }).addTo(markerLayerGroup);

    marker.bindPopup(`
      <strong>${esc(venueName)}</strong><br>
      ${eventRows}
      スコア ${score}<br>
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
 * 現在地からイベント会場までの距離をkm単位で返す。
 * @param {object} ev イベント。
 * @returns {number} 距離(km)。取得不能時はInfinity。
 */
function distanceKmOf(ev) {
  if (!state.userLatLng) return Infinity;
  const lat = Number(ev && ev.venueInfo && ev.venueInfo.lat);
  const lng = Number(ev && ev.venueInfo && ev.venueInfo.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return Infinity;

  const km = haversineKm(state.userLatLng, { lat, lng });
  return Number.isFinite(km) ? km : Infinity;
}

/**
 * ブラウザの現在地取得を行い、成功時は状態・地図・距離表示へ反映する。
 * @param {Function} onSuccess 成功時コールバック。
 * @param {Function} onError 失敗時コールバック。
 * @returns {void}
 */
function requestUserLocation(onSuccess, onError) {
  if (!navigator.geolocation) {
    if (onError) onError();
    return;
  }

  navigator.geolocation.getCurrentPosition(position => {
    const lat = position.coords.latitude;
    const lng = position.coords.longitude;
    state.userLatLng = { lat, lng };
    state.locationDenied = false;
    try {
      sessionStorage.setItem("userLatLng", JSON.stringify(state.userLatLng));
    } catch (e) {
      // 保存できない環境でも現在セッションの表示は継続する。
    }
    if (map && window.L) {
      if (userLocationMarker) map.removeLayer(userLocationMarker);
      userLocationMarker = L.circleMarker([lat, lng], {
        radius: 8,
        color: "#1e88e5",
        fillColor: "#1e88e5",
        fillOpacity: 0.9,
      }).addTo(map);
      map.setView([lat, lng], 13);
    }
    updateDistances();
    if (onSuccess) onSuccess();
  }, () => {
    if (onError) onError();
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
  map.on("popupopen", e => {
    const popupEl = e.popup.getElement();
    if (!popupEl) return;
    popupEl.querySelectorAll(".popup-jump").forEach(button => {
      button.addEventListener("click", () => {
        const id = button.dataset.id;
        map.closePopup();
        if (!document.querySelector(`.event-card[data-id="${id}"]`)) {
          state.category.clear();
          state.area.clear();
          render();
        }
        scrollToEventCard(id);
      });
    });
  });
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
    requestUserLocation(null, () => {
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

function scrollToEventCard(eventId) {
  const card = document.querySelector(`.event-card[data-id="${eventId}"]`);
  // フィルタで一覧カードが無い場合は何もしない。
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.add("flash");
  setTimeout(() => card.classList.remove("flash"), 1500);
}

function renderNowView(nowOverrideMin) {
  const el = document.getElementById("now-view");
  if (!el) return;
  if (state.date !== todayISO()) {
    el.innerHTML = "";
    return;
  }

  const now = new Date();
  const nowMin = Number.isFinite(nowOverrideMin) ? nowOverrideMin : now.getHours() * 60 + now.getMinutes();
  const untilMin = nowMin + NOW_VIEW_LOOKAHEAD_MIN;
  const evs = eventsOfDay();
  const targetEvents = evs
    .filter(e => demandWindows(e, e.score.total / 100).some(w => w.from <= untilMin && w.to >= nowMin))
    .sort((a, b) => b.score.total - a.score.total)
    .slice(0, NOW_VIEW_LIMIT);

  if (targetEvents.length > 0) {
    el.innerHTML = `
      <h2 class="section-title"><span class="en">Right Now</span>今から狙う</h2>
      <div class="best3 now-view">` +
      targetEvents.map((e, i) => `
        <button class="best-card now-card" data-id="${e.id}">
          <div class="best-rank">${String(i + 1).padStart(2, "0")}</div>
          <div class="best-body">
            <div class="best-name">${esc(e.name)}</div>
            <div class="best-meta">${esc(e.venue)}</div>
            <div class="best-aim">${esc(aimText(e))}</div>
          </div>
          <div class="best-score">${e.score.total}</div>
        </button>`).join("") +
      `</div>`;
    el.querySelectorAll(".now-card").forEach(b =>
      b.addEventListener("click", () => scrollToEventCard(b.dataset.id))
    );
    return;
  }

  const futureWindows = [];
  evs.forEach(e => {
    demandWindows(e, e.score.total / 100).forEach(w => {
      if (w.from > nowMin) futureWindows.push({ event: e, from: w.from });
    });
  });
  futureWindows.sort((a, b) => a.from - b.from);
  const next = futureWindows[0];
  if (!next) {
    el.innerHTML = "";
    return;
  }

  // 現在は谷間なら、最も近い次ピークだけを軽く出す。
  el.innerHTML = `
    <h2 class="section-title"><span class="en">Right Now</span>今から狙う</h2>
    <div class="now-bridge">次のピークは <span class="now-bridge-time">${fmtMin(next.from)}</span> 頃 ／ ${esc(next.event.name)}</div>`;
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
    b.addEventListener("click", () => scrollToEventCard(b.dataset.id))
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

function renderWeekView() {
  const el = document.getElementById("week-view");
  const today = todayISO();
  const weather = (window.TAXI_APP_DATA && window.TAXI_APP_DATA.weather) || {};
  // DATESの時系列順をそのまま使い、各日の合計需要と代表イベントを作る。
  const dayRows = DATES.map(date => {
    const evs = EVENTS.filter(e => e.date === date);
    const dayTotal = evs.reduce((sum, e) => sum + e.score.total, 0);
    const topEvent = [...evs].sort((a, b) => b.score.total - a.score.total)[0] || null;
    return { date, evs, dayTotal, topEvent };
  });
  const maxTotal = Math.max(...dayRows.map(r => r.dayTotal), 0);
  const topRanks = new Map(
    [...dayRows]
      .filter(r => r.dayTotal > 0)
      .sort((a, b) => b.dayTotal - a.dayTotal)
      .slice(0, 3)
      .map((r, i) => [r.date, i + 1])
  );

  const weatherLabel = date => {
    const pop = Number(weather[date] && weather[date].pop_max);
    if (!Number.isFinite(pop)) return "";
    if (pop < 10) return "☀";
    if (pop < 30) return "☁";
    return `☔ ${pop}%`;
  };
  const shortName = name => {
    const s = String(name);
    return s.length > 12 ? `${s.slice(0, 12)}...` : s;
  };

  el.innerHTML = `
    <h2 class="section-title"><span class="en">Weekly Outlook</span>出る日の目安</h2>
    <div class="week-view">` +
    dayRows.map(row => {
      const { md, wd, dow } = dateLabel(row.date);
      const rank = topRanks.get(row.date);
      const width = maxTotal > 0 ? (row.dayTotal / maxTotal) * 100 : 0;
      const cls = [
        "week-row",
        row.date === state.date ? "active" : "",
        rank ? "ranked" : "",
        row.evs.length === 0 ? "no-events" : "",
        dow === 0 ? "sun" : dow === 6 ? "sat" : "",
      ].join(" ");
      const todayMark = row.date === today ? `<span class="week-today">TODAY</span>` : "";
      const rankBadge = rank ? `<span class="week-rank">${String(rank).padStart(2, "0")}</span>` : `<span class="week-rank blank"></span>`;
      const eventName = row.topEvent ? shortName(row.topEvent.name) : "イベントなし";
      const bar = row.evs.length > 0
        ? `<span class="week-bar" style="width:${width.toFixed(2)}%"></span>`
        : "";
      return `
        <button class="${cls}" data-date="${row.date}">
          <span class="week-date">${todayMark}<span class="md">${esc(md)}</span><span class="wd">(${esc(wd)})</span></span>
          ${rankBadge}
          <span class="week-meter">${bar}</span>
          <span class="week-total">${row.dayTotal}</span>
          <span class="week-event">${esc(eventName)}</span>
          <span class="week-weather">${esc(weatherLabel(row.date))}</span>
        </button>`;
    }).join("") +
    `</div>`;

  el.querySelectorAll(".week-row").forEach(b =>
    b.addEventListener("click", () => {
      state.date = b.dataset.date;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    })
  );
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
        <button class="sort-btn ${state.sort === "near" ? "on" : ""}" data-sort="near">近い順</button>
        <button class="sort-btn ${state.sort === "eff" ? "on" : ""}" data-sort="eff">効率順</button>
      </div>
      ${state.locationDenied ? `<div class="sort-note">現在地が取得できないため、近い順・効率順は使用できません</div>` : ""}
    </div>
    <div class="chip-row">${cats.map(c => chip(c, CATEGORY_LABEL[c] || c, state.category, "category")).join("")}</div>
    <div class="chip-row">${areas.map(a => chip(a, a, state.area, "area")).join("")}</div>`;

  el.querySelectorAll(".sort-btn").forEach(b =>
    b.addEventListener("click", () => {
      const nextSort = b.dataset.sort;
      if ((nextSort === "near" || nextSort === "eff") && !state.userLatLng) {
        state.locationDenied = false;
        requestUserLocation(() => {
          state.sort = nextSort;
          state.locationDenied = false;
          render();
        }, () => {
          state.locationDenied = true;
          render();
        });
        return;
      }
      state.sort = nextSort;
      if (nextSort === "near" || nextSort === "eff") state.locationDenied = false;
      render();
    })
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
  const feedback = loadFeedback()[e.id] || {};
  const hitOn = feedback.verdict === "hit" ? " on" : "";
  const missOn = feedback.verdict === "miss" ? " on" : "";
  return `
    <div class="breakdown">
      <div class="bd-title">スコア内訳（乗算モデル：需要指数 ${idx} ／ ピーク同時需要 約${peak.toLocaleString()}人）</div>
      ${rows}
    </div>
    ${dest}${tips}${notes}
    <div class="fb-row">
      <span class="detail-key">実績記録</span>
      <button class="fb-btn${hitOn}" data-id="${esc(e.id)}" data-verdict="hit">当たった</button>
      <button class="fb-btn${missOn}" data-id="${esc(e.id)}" data-verdict="miss">外れた</button>
    </div>`;
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
  const sorted = [...evs].sort((a, b) => {
    if (state.sort === "score") return b.score.total - a.score.total;
    if (state.sort === "near") {
      const akm = distanceKmOf(a);
      const bkm = distanceKmOf(b);
      if (!Number.isFinite(akm) && Number.isFinite(bkm)) return 1;
      if (Number.isFinite(akm) && !Number.isFinite(bkm)) return -1;
      if (akm !== bkm) return akm - bkm;
      return b.score.total - a.score.total;
    }
    if (state.sort === "eff") {
      const akm = distanceKmOf(a);
      const bkm = distanceKmOf(b);
      if (!Number.isFinite(akm) && Number.isFinite(bkm)) return 1;
      if (Number.isFinite(akm) && !Number.isFinite(bkm)) return -1;
      const aEff = a.score.total / Math.max(0.5, akm);
      const bEff = b.score.total / Math.max(0.5, bkm);
      if (aEff !== bEff) return bEff - aEff;
      return b.score.total - a.score.total;
    }
    return toMin(a.start) - toMin(b.start);
  });
  const showCountdown = state.date === todayISO();
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
              ${showCountdown ? `<span class="countdown" data-id="${esc(e.id)}"></span>` : ""}
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
  el.querySelectorAll(".fb-btn").forEach(button =>
    button.addEventListener("click", ev => {
      ev.preventDefault();
      const target = EVENTS.find(item => String(item.id) === button.dataset.id);
      if (!target) return;

      const feedback = loadFeedback();
      const current = feedback[target.id];
      if (current && current.verdict === button.dataset.verdict) {
        delete feedback[target.id];
      } else {
        feedback[target.id] = {
          date: target.date,
          name: target.name,
          venue: target.venue,
          score: target.score.total,
          verdict: button.dataset.verdict,
          recordedAt: new Date().toISOString(),
        };
      }
      saveFeedback(feedback);
      // 全再描画すると開いているカードが閉じるため、ボタン状態と一覧のみ更新する。
      const updated = loadFeedback()[target.id];
      button.closest(".fb-row").querySelectorAll(".fb-btn").forEach(b =>
        b.classList.toggle("on", Boolean(updated && updated.verdict === b.dataset.verdict))
      );
      renderFeedbackLog();
    })
  );
}

function renderFeedbackLog() {
  const el = document.getElementById("feedback-log");
  if (!el) return;

  const feedback = loadFeedback();
  const entries = Object.values(feedback);
  if (entries.length === 0) {
    el.innerHTML = "";
    return;
  }

  const rows = entries
    .sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))
    .map(item => {
      const d = new Date(`${item.date}T00:00:00`);
      const md = Number.isFinite(d.getTime()) ? `${d.getMonth() + 1}/${d.getDate()}` : esc(item.date || "-");
      const verdict = item.verdict === "hit" ? "当たった" : "外れた";
      return `<div class="fb-log-row">${md} ${esc(item.name || "")}（${esc(item.venue || "")}）スコア${esc(item.score == null ? "-" : item.score)} ── ${verdict}</div>`;
    }).join("");

  el.innerHTML = `
    <details class="fb-log">
      <summary>実績記録 ${entries.length}件</summary>
      <div class="fb-log-body">${rows}</div>
      <button id="fb-export" type="button">JSONをコピー</button>
    </details>`;

  const exportBtn = document.getElementById("fb-export");
  if (!exportBtn) return;
  exportBtn.addEventListener("click", () => {
    const json = JSON.stringify(loadFeedback(), null, 2);
    const original = exportBtn.textContent;
    const markCopied = () => {
      exportBtn.textContent = "コピーしました";
      setTimeout(() => {
        exportBtn.textContent = original;
      }, 2000);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(json).then(markCopied).catch(() => {
        prompt("コピーしてください", json);
      });
      return;
    }
    prompt("コピーしてください", json);
  });
}

function updateCountdowns(nowOverrideMin) {
  const now = new Date();
  const nowMin = Number.isFinite(nowOverrideMin) ? nowOverrideMin : now.getHours() * 60 + now.getMinutes();
  document.querySelectorAll(".countdown").forEach(el => {
    if (state.date !== todayISO()) {
      el.textContent = "";
      el.hidden = true;
      el.classList.remove("urgent");
      return;
    }

    const ev = EVENTS.find(e => String(e.id) === el.dataset.id);
    const c = ev ? countdownText(ev, nowMin) : null;
    el.textContent = c ? c.text : "";
    el.hidden = !c;
    el.classList.toggle("urgent", Boolean(c && c.urgent));
  });
}

function renderFooter() {
  const el = document.getElementById("footer");
  const meta = window.TAXI_APP_DATA || {};
  const src = meta.source === "demo"
    ? "表示中のイベントはデモデータ（架空）です"
    : `データソース: ${esc(meta.source || "不明")}`;
  const errors = Array.isArray(meta.errors) ? meta.errors : [];
  const errorLine = errors.length
    ? `<div class="footer-errors">&#9888; データ取得エラー: ${errors.map(err => {
        const s = String(err);
        return esc(s.length > 60 ? `${s.slice(0, 57)}...` : s);
      }).join(" ／ ")}</div>`
    : "";

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

  el.innerHTML = `${errorLine}${wxLine}<span class="footer-brand">FORECAB</span> ${src} ・ 更新 ${esc(meta.generated_at || "-")}<br>
    スコアは公開情報ベースの参考値です。実際の需要・交通規制・営業区域は現場の判断を優先してください。`;
}

function render() {
  renderFreshnessBanner();
  renderTabs();
  renderNowView();
  renderSummary();
  renderHeatmap();
  renderWeekView();
  renderControls();
  renderList();
  renderFeedbackLog();
  renderFooter();
  updateCountdowns();
}

function startNowViewAutoRefresh() {
  if (nowViewTimer !== null) return;
  nowViewTimer = setInterval(() => {
    // 今日タブの表示中だけ、現在時刻セクションを軽量更新する。
    if (state.date === todayISO()) renderNowView();
    updateCountdowns();
  }, NOW_VIEW_REFRESH_MS);
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

startNowViewAutoRefresh();
render();
