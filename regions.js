/* FORECAB — 地域メタデータ（全地域共通） */
"use strict";

(function (root) {
  const regions = {
    tokyo: {
      id: "tokyo",
      label: "東京",
      tag: "東京イベント需要予報",
      tagEn: "Tokyo Event Demand Forecast",
      mapCenter: [35.681, 139.767],
      mapZoom: 12,
      href: "../tokyo/",
    },
    yokohama: {
      id: "yokohama",
      label: "横浜",
      tag: "横浜イベント需要予報",
      tagEn: "Yokohama Event Demand Forecast",
      mapCenter: [35.459, 139.632],
      mapZoom: 12,
      href: "../yokohama/",
    },
    osaka: {
      id: "osaka",
      label: "大阪",
      tag: "大阪イベント需要予報",
      tagEn: "Osaka Event Demand Forecast",
      mapCenter: [34.684, 135.501],
      mapZoom: 12,
      href: "../osaka/",
    },
  };

  const requested = String(root.FORECAB_REGION_ID || "tokyo").toLowerCase();
  root.FORECAB_REGIONS = regions;
  root.FORECAB_REGION = regions[requested] || regions.tokyo;
})(window);
