import fs from "node:fs";
import vm from "node:vm";

const SITE_URL = "https://kirakirapink.github.io/forecab/";
const JST_OFFSET_MS = 9 * 60 * 60 * 1000;
const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

const dryRun = process.argv.includes("--dry-run");

function readText(path) {
  return fs.readFileSync(new URL(path, import.meta.url), "utf8");
}

// ブラウザ用のグローバル代入形式を Node の VM 内で再利用する。
function loadPayload() {
  const sandbox = {};
  const context = vm.createContext({ window: sandbox });
  [
    ["../scoring.js", "scoring.js"],
    ["../venues.js", "venues.js"],
    ["../data/events.js", "data/events.js"],
  ].forEach(([path, filename]) => {
    vm.runInContext(readText(path), context, { filename });
  });
  return {
    scoring: sandbox.FORECAB_SCORING,
    venues: sandbox.VENUES || {},
    venueDefault: sandbox.VENUE_DEFAULT || {},
    payload: sandbox.TAXI_APP_DATA || {},
  };
}

function todayInJst(now = new Date()) {
  const shifted = new Date(now.getTime() + JST_OFFSET_MS);
  const year = shifted.getUTCFullYear();
  const month = shifted.getUTCMonth() + 1;
  const day = shifted.getUTCDate();
  return {
    iso: `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
    label: `${month}/${day} ${WEEKDAYS[shifted.getUTCDay()]}`,
  };
}

function compactWeatherText(value) {
  return String(value || "").replace(/[\s　]+/g, " ").trim();
}

function weatherLine(weather) {
  if (!weather) return null;
  const parts = [];
  const name = compactWeatherText(weather.weather);
  const pop = Number(weather.pop_max);
  const tmax = Number(weather.temp_max);
  const tmin = Number(weather.temp_min);
  if (name) parts.push(name);
  if (Number.isFinite(pop)) parts.push(`降水${pop}%`);
  if (Number.isFinite(tmax) || Number.isFinite(tmin)) {
    const temps = [];
    if (Number.isFinite(tmax)) temps.push(`最高${tmax}℃`);
    if (Number.isFinite(tmin)) temps.push(`最低${tmin}℃`);
    parts.push(temps.join(" "));
  }
  return parts.length ? `天気: ${parts.join(" ／ ")}` : null;
}

function buildMessage() {
  const { scoring, venues, venueDefault, payload } = loadPayload();
  const { iso, label } = todayInJst();
  const events = Array.isArray(payload.events) ? payload.events : [];
  const weather = payload.weather || {};
  const ctx = { venues, venueDefault, weather };
  const lines = [`🚕 FORECAB 本日の焦点（${label}）`];

  const ranked = events
    .filter(ev => ev.date === iso)
    .map((ev, index) => ({ ev, index, score: scoring.scoreEvent(ev, ctx) }))
    .sort((a, b) => (b.score.total - a.score.total) || (a.index - b.index))
    .slice(0, 3);

  if (ranked.length === 0) {
    lines.push("本日の対象イベントはありません");
  } else {
    ranked.forEach((item, index) => {
      const venue = scoring.venueOf(item.ev, venues, venueDefault);
      lines.push(`${String(index + 1).padStart(2, "0")} ${item.ev.name} ／ ${venue.name || item.ev.venue} ── スコア${item.score.total} ── ${scoring.aimText(item.ev)}`);
    });
  }

  const wxLine = weatherLine(weather[iso]);
  if (wxLine) lines.push(wxLine);

  lines.push(SITE_URL);

  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  errors.forEach(err => {
    lines.push(`⚠ 取得エラー: ${err}`);
  });

  return lines.join("\n");
}

async function postToDiscord(content) {
  const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
  if (!webhookUrl) {
    console.log("DISCORD_WEBHOOK_URL 未設定のため配信をスキップ");
    return;
  }

  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    const body = await response.text();
    console.error(`Discord配信失敗: HTTP ${response.status} ${response.statusText}`);
    console.error(body);
    process.exit(1);
  }
}

const message = buildMessage();
if (dryRun) {
  console.log(message);
} else {
  await postToDiscord(message);
}
