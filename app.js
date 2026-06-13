/* FORECAB — スコアリングエンジン + UI */
"use strict";

/* ===========================================================
 * スコアリングモデル（合計0〜100点 → 星0〜5）
 *
 *   規模(0-40)    : 来場者数。対数スケール（100人=0点、10万人=40点）
 *   客層(0-20)    : タクシー利用率・客単価の期待値
 *   時間帯(0-20)  : 終演が遅いほど高得点（終電後は最大）。展示会は常時出入りで底上げ
 *   駅事情(0-10)  : 駅が遠い・弱い・混む会場ほどタクシーに流れる
 *   長距離(0-10)  : 空港・近県・都心横断などロング期待
 *   ×種別補正     : 展示会1.10（ビジネス経費移動・手荷物）〜 催事0.85（電車中心）
 * =========================================================== */

const CATEGORY_LABEL = {
  exhibition: "展示会",
  concert: "ライブ",
  sports: "スポーツ",
  theater: "舞台・クラシック",
  festival: "催事・フェス",
};

const CATEGORY_FACTOR = {
  exhibition: 1.10,
  theater: 1.05,
  concert: 1.00,
  sports: 0.92,  // 駅至近スタジアムが多く電車比率高
  festival: 0.85,
};

const AUDIENCE_LABEL = {
  business: "ビジネス客",
  general: "一般客",
  youth: "若年層",
  family: "ファミリー",
  senior_wealthy: "年配・富裕層",
};

const AUDIENCE_SPEND = {  // 0-20
  senior_wealthy: 20,
  business: 18,
  general: 10,
  family: 8,
  youth: 5,
};

const AUDIENCE_HINT = {
  business: "経費移動が多くタクシー利用率高",
  senior_wealthy: "タクシー利用率は最高クラス",
  general: "利用率は普通。規模で勝負",
  family: "子連れ・荷物で短距離需要が出る",
  youth: "電車中心で利用率低め",
};

const ACCESS_SCORE = { near: 3, mid: 6, far: 10 };
const ACCESS_LABEL = { near: "駅近（電車に流れやすい）", mid: "駅やや遠 or 終演時大混雑", far: "駅遠・路線弱（タクシー有利）" };

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

function timingScore(ev) {
  const end = toMin(ev.end);
  if (ev.category === "exhibition") {
    // 終日出入りがあるため底上げ。閉場が夕方以降ならピークも乗る
    return clamp(12 + (end >= toMin("17:00") ? 3 : 0), 0, 20);
  }
  let base;
  if (end < toMin("18:00")) base = 4;
  else if (end < toMin("20:00")) base = 8;
  else if (end < toMin("21:00")) base = 12;
  else if (end < toMin("22:00")) base = 16;
  else if (end < toMin("23:00")) base = 19;
  else base = 20; // 終電が怪しい時間帯はタクシー一択になる
  if (ev.category === "festival") base = Math.max(0, base - 4);
  return base;
}

function scoreEvent(ev) {
  const v = venueOf(ev);
  const att = Math.max(1, Number(ev.attendance) || 1);
  const volume = clamp((Math.log10(att) - 2) / 3, 0, 1) * 40;
  const spend = AUDIENCE_SPEND[ev.audience] ?? 10;
  const timing = timingScore(ev);
  const access = ACCESS_SCORE[v.station_access] ?? 6;
  const longdist = clamp(v.long_distance ?? 0.3, 0, 1) * 10;
  const factor = CATEGORY_FACTOR[ev.category] ?? 1.0;

  const total = clamp((volume + spend + timing + access + longdist) * factor, 0, 100);
  const stars = Math.round((total / 20) * 2) / 2; // 半星刻み

  return {
    total: Math.round(total),
    stars,
    factor,
    breakdown: [
      { label: "規模",     score: Math.round(volume),  max: 40, hint: `${att.toLocaleString()}人規模` },
      { label: "客層",     score: spend,               max: 20, hint: AUDIENCE_HINT[ev.audience] || "" },
      { label: "時間帯",   score: timing,              max: 20, hint: ev.category === "exhibition" ? "終日出入りあり" : `終演 ${ev.end}` },
      { label: "駅事情",   score: access,              max: 10, hint: ACCESS_LABEL[v.station_access] || "" },
      { label: "長距離",   score: Math.round(longdist), max: 10, hint: (v.typical_destinations || []).slice(0, 2).join("・") || "データなし" },
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
};

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
  let nowLine = "";
  if (state.date === todayISO()) {
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const rangeLo = lo * BIN, rangeHi = (hi + 1) * BIN;
    if (nowMin >= rangeLo && nowMin <= rangeHi) {
      const pct = ((nowMin - rangeLo) / (rangeHi - rangeLo)) * 100;
      nowLine = `<div class="hm-now" style="left:${pct.toFixed(2)}%"><span>NOW</span></div>`;
    }
  }

  el.innerHTML = `
    <h2 class="section-title"><span class="en">Demand Timeline</span>時間帯別需要指数
      <span class="peak-note">ピーク ${fmtMin(peakBin * BIN)}前後</span>
    </h2>
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
      <div class="bd-bar"><div class="bd-fill" style="width:${(b.score / b.max) * 100}%"></div></div>
      <div class="bd-score">${b.score}<span class="bd-max">/${b.max}</span></div>
      <div class="bd-hint">${esc(b.hint)}</div>
    </div>`).join("");
  const v = e.venueInfo;
  const dest = (v.typical_destinations || []).length
    ? `<div class="detail-row"><span class="detail-key">主要行き先</span>${v.typical_destinations.map(d => `<span class="dest">${esc(d)}</span>`).join("")}</div>` : "";
  const tips = v.tips ? `<div class="detail-row"><span class="detail-key">現場メモ</span>${esc(v.tips)}</div>` : "";
  const notes = e.notes ? `<div class="detail-row"><span class="detail-key">備考</span>${esc(e.notes)}</div>` : "";
  return `
    <div class="breakdown">
      <div class="bd-title">スコア内訳（種別補正 ×${e.score.factor.toFixed(2)}）</div>
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
  el.innerHTML = `<span class="footer-brand">FORECAB</span> ${src} ・ 更新 ${esc(meta.generated_at || "-")}<br>
    スコアは公開情報ベースの参考値です。実際の需要・交通規制・営業区域は現場の判断を優先してください。`;
}

function render() {
  renderTabs();
  renderSummary();
  renderHeatmap();
  renderControls();
  renderList();
  renderFooter();
}

render();
