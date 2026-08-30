"""FORECABの地域別データ生成設定。"""

REGIONS = {
    "tokyo": {
        "label": "東京",
        "weather_label": "東京地方",
        "weather_area_code": "130000",
        "output": "data/events.js",  # 旧URL・既存運用との互換を維持
        "manual_csv": "data/manual_events.csv",
        "sources": (
            "npb", "bigsight", "dome", "ariake", "zepp", "garden_theater",
            "nntt", "kabukiza", "national_stadium", "medical_society",
            "nougakudo", "yoyogi", "takarazuka", "annual", "forum",
        ),
    },
    "yokohama": {
        "label": "横浜",
        "weather_label": "神奈川県東部",
        "weather_area_code": "140000",
        "output": "data/yokohama/events.js",
        "manual_csv": "data/yokohama/manual_events.csv",
        "sources": ("npb", "k_arena", "yokohama_arena", "zepp"),
    },
    "osaka": {
        "label": "大阪",
        "weather_label": "大阪府",
        "weather_area_code": "270000",
        "output": "data/osaka/events.js",
        "manual_csv": "data/osaka/manual_events.csv",
        "sources": ("npb", "kyocera_dome", "osaka_johall", "zepp"),
    },
}
