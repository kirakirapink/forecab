import importlib
import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from region_config import REGIONS  # noqa: E402
from fetch_events import stable_event_id  # noqa: E402


def load_payload(path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text.split("=", 1)[1].strip().removesuffix(";"))


def regional_venue_names(path):
    text = path.read_text(encoding="utf-8")
    object_text = text.split("window.VENUES =", 1)[1].split("window.VENUE_DEFAULT", 1)[0]
    return set(re.findall(r'^  "([^"]+)": \{$', object_text, re.MULTILINE))


class RegionConfigurationTests(unittest.TestCase):
    def test_regions_have_separate_output_weather_and_sources(self):
        self.assertEqual(set(REGIONS), {"tokyo", "yokohama", "osaka"})
        self.assertEqual(len({config["output"] for config in REGIONS.values()}), 3)
        self.assertEqual(
            {config["weather_area_code"] for config in REGIONS.values()},
            {"130000", "140000", "270000"},
        )
        self.assertIn("k_arena", REGIONS["yokohama"]["sources"])
        self.assertIn("osaka_johall", REGIONS["osaka"]["sources"])
        self.assertNotIn("bigsight", REGIONS["yokohama"]["sources"])

    def test_region_pages_and_manifests_reference_local_assets(self):
        for region in REGIONS:
            page = (ROOT / region / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'id: "{region}"', page)
            self.assertIn(f'/forecab/{region}/', page)
            self.assertIn('id="region-ribbon"', page)
            manifest = json.loads((ROOT / region / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["start_url"], "./")
            self.assertEqual(manifest["scope"], "./")

    def test_generated_region_payloads_match_pages_and_venue_masters(self):
        paths = {
            "tokyo": (ROOT / "data/events.js", ROOT / "venues.js"),
            "yokohama": (ROOT / "data/yokohama/events.js", ROOT / "regional/yokohama-venues.js"),
            "osaka": (ROOT / "data/osaka/events.js", ROOT / "regional/osaka-venues.js"),
        }
        for region, (data_path, venues_path) in paths.items():
            payload = load_payload(data_path)
            venues = regional_venue_names(venues_path)
            self.assertEqual(payload["region"], region)
            self.assertTrue(payload["events"])
            self.assertEqual({event["venue"] for event in payload["events"]} - venues, set())
            self.assertTrue(all(event["id"].startswith(f"{region}-") for event in payload["events"]))

    def test_stable_ids_do_not_depend_on_fetch_order_and_include_region(self):
        event = {"date": "2026-09-01", "venue": "会場", "name": "公演", "start": "18:00"}
        self.assertEqual(stable_event_id("tokyo", event), stable_event_id("tokyo", dict(event)))
        self.assertNotEqual(stable_event_id("tokyo", event), stable_event_id("yokohama", event))

    def test_weather_url_is_region_parameterized(self):
        weather = importlib.import_module("sources.weather")
        self.assertIn("{area_code}", weather.URL)

    def test_root_redirects_to_tokyo(self):
        root_page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertRegex(root_page, re.compile(r'location\.replace\(target\)'))
        self.assertIn('"./tokyo/"', root_page)


if __name__ == "__main__":
    unittest.main()
