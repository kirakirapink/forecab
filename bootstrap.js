/* FORECAB — 地域ページ共通ブートストラップ */
"use strict";

(function () {
  const page = window.FORECAB_PAGE || {};
  const root = page.root || "..";
  const bust = `?t=${Date.now()}`;
  const fallback = {
    generated_at: "",
    source: "読み込みエラー",
    region: page.id || "",
    events: [],
    weather: {},
    errors: ["イベントデータを読み込めませんでした"],
  };

  window.FORECAB_REGION_ID = page.id || "tokyo";

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`script load failed: ${src}`));
      document.body.appendChild(script);
    });
  }

  function parsePayload(text) {
    const eq = text.indexOf("=");
    if (eq < 0) throw new Error("events.js の形式が不正です");
    return JSON.parse(text.slice(eq + 1).trim().replace(/;\s*$/, ""));
  }

  const assetsPromise = Promise.all([
    loadScript(`${root}/regions.js${bust}`),
    loadScript(`${root}/scoring.js${bust}`),
    loadScript(`${root}/${page.venues}${bust}`),
  ]);
  const dataPromise = fetch(`${root}/${page.data}${bust}`, { cache: "no-store" })
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.text();
    })
    .then(parsePayload);

  // 失敗時も全アセットの成否が確定するまで待ち、app.jsとの読み込み競合を防ぐ。
  Promise.allSettled([assetsPromise, dataPromise])
    .then(results => {
      const assets = results[0];
      const data = results[1];
      if (assets.status === "rejected") {
        console.error("FORECAB の共通アセット読み込みに失敗:", assets.reason);
      }
      if (data.status === "fulfilled") {
        window.TAXI_APP_DATA = data.value;
        return;
      }
      const error = data.reason;
      console.error("FORECAB の初期化に失敗:", error);
      window.TAXI_APP_DATA = Object.assign({}, fallback, {
        errors: [`イベントデータを読み込めませんでした: ${error.message || error}`],
      });
    })
    .then(() => loadScript(`${root}/app.js${bust}`))
    .catch(error => console.error("FORECAB のUI読み込みに失敗:", error));
})();
