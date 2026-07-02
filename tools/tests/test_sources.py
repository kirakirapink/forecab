import datetime
import importlib
import re
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS_DIR))

from sources import base  # noqa: E402


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

URL_FIXTURES = {
    "https://npb.jp/games/2026/schedule_06_detail.html": "npb_schedule_2026_06.html",
    "https://www.bigsight.jp/visitor/event/": "bigsight_list_p1.html",
    "https://www.tokyo-dome.co.jp/dome/event/schedule.html": "dome_schedule.html",
    "https://ariake-arena.tokyo/event/": "ariake_current.html",
    "https://ariake-arena.tokyo/event/next/": "ariake_next.html",
    "https://www.nntt.jac.go.jp/calendar/topcalendar.json": "nntt_topcalendar.json",
    "https://www.kabuki-bito.jp/theaters/kabukiza/": "kabukiza_theaters_kabukiza.html",
    "https://jns-e.com/event/page/202606/": "national_stadium_2026_06.html",
    "https://jams.med.or.jp/members-a/index.html": "medical_society_members.html",
    "https://www.ntj.jac.go.jp/nou/": "nougakudo_top.html",
    "https://www.t-i-forum.co.jp/visitors/event/": "forum_event.html",
    "https://www.zepp.co.jp/hall/haneda/schedule/": "zepp_haneda.html",
    "https://www.zepp.co.jp/hall/divercity/schedule/": "zepp_divercity.html",
    "https://www.shopping-sumitomo-rd.com/tokyo_garden_theater/schedule/": "garden_theater.html",
}

VALID_CATEGORIES = {"exhibition", "concert", "sports", "theater", "festival"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def fixture_http_get(url):
    filename = URL_FIXTURES.get(url)
    if not filename:
        raise base.SourceError(f"No offline fixture registered for {url}")
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8", errors="replace")


def fixed_datetime_module(year, month, day):
    class FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(year, month, day)

    return types.SimpleNamespace(date=FixedDate, timedelta=datetime.timedelta)


@contextmanager
def offline_source(module_name, today=None):
    with tempfile.TemporaryDirectory() as tmpdir:
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(base, "CACHE_DIR", Path(tmpdir)))
            stack.enter_context(mock.patch.object(base, "http_get", side_effect=fixture_http_get))
            stack.enter_context(mock.patch("urllib.request.urlopen", side_effect=AssertionError("network disabled")))
            module = importlib.reload(importlib.import_module(f"sources.{module_name}"))
            if today is not None:
                stack.enter_context(mock.patch.object(module, "datetime", fixed_datetime_module(*today)))
            yield module


class EventAssertions(unittest.TestCase):
    def assert_valid_event(self, event):
        self.assertRegex(event["date"], DATE_RE)
        self.assertIsInstance(event["venue"], str)
        self.assertTrue(event["venue"].strip())
        self.assertIsInstance(event["name"], str)
        self.assertTrue(event["name"].strip())
        self.assertRegex(event["start"], TIME_RE)
        self.assertRegex(event["end"], TIME_RE)
        self.assertGreater(event["attendance"], 0)
        self.assertIn(event["category"], VALID_CATEGORIES)


class SourceFixtureTests(EventAssertions):
    def test_npb_fetches_from_june_schedule_fixture(self):
        weekend_dates = {
            datetime.date(2026, 6, day).isoformat()
            for day in range(1, 31)
            if datetime.date(2026, 6, day).weekday() >= 5
        }
        with offline_source("npb") as npb:
            events = npb.fetch(2026, 6, weekend_dates)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_bigsight_fetches_from_list_fixture(self):
        with offline_source("bigsight") as bigsight:
            events = bigsight.fetch(pages=1)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_dome_fetches_from_schedule_fixture(self):
        with offline_source("dome") as dome:
            events = dome.fetch()
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_ariake_fetches_from_current_and_next_fixtures(self):
        # ariake.py infers the year from date.today(), so pin it to the capture window.
        with offline_source("ariake", today=(2026, 6, 20)) as ariake:
            events = ariake.fetch()
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_zepp_fetches_from_haneda_and_divercity_fixtures(self):
        with offline_source("zepp") as zepp:
            events = zepp.fetch()
        venues = {event["venue"] for event in events}
        self.assertIn("Zepp Haneda", venues)
        self.assertIn("Zepp DiverCity", venues)
        self.assertGreaterEqual(len([e for e in events if e["venue"] == "Zepp Haneda"]), 20)
        self.assertGreaterEqual(len([e for e in events if e["venue"] == "Zepp DiverCity"]), 20)
        self.assertTrue(any(
            e["date"] == "2026-07-03"
            and e["venue"] == "Zepp Haneda"
            and e["start"] == "19:00"
            and "BLUE ENCOUNT" in e["name"]
            for e in events
        ))
        self.assertTrue(any(
            e["date"] == "2026-07-03"
            and e["venue"] == "Zepp DiverCity"
            and e["start"] == "19:00"
            and "East Of Eden" in e["name"]
            for e in events
        ))
        self.assert_valid_event(events[0])

    def test_garden_theater_fetches_and_expands_periods(self):
        with offline_source("garden_theater", today=(2026, 7, 3)) as garden_theater:
            events = garden_theater.fetch()
        self.assertGreaterEqual(len(events), 20)
        self.assert_valid_event(events[0])
        akanishi_dates = {
            e["date"] for e in events
            if e["venue"] == "東京ガーデンシアター" and "JIN AKANISHI HEART LIVE 2026" in e["name"]
        }
        self.assertEqual(akanishi_dates, {"2026-07-03", "2026-07-04", "2026-07-05"})
        self.assertTrue(any(
            e["date"] == "2026-07-24"
            and e["start"] == "18:00"
            and e["end"] == "21:00"
            and "サマーステップコンサート" in e["name"]
            for e in events
        ))

    def test_nntt_fetches_from_calendar_fixture(self):
        # The cached NNTT payload is JSON and contains 2027/08 performances.
        with offline_source("nntt", today=(2027, 8, 1)) as nntt:
            events = nntt.fetch(days_ahead=20)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_kabukiza_fetches_from_theater_fixture(self):
        with offline_source("kabukiza", today=(2026, 6, 20)) as kabukiza:
            events = kabukiza.fetch(days_ahead=45)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_national_stadium_fetches_from_month_fixture(self):
        with offline_source("national_stadium", today=(2026, 6, 20)) as national_stadium:
            events = national_stadium.fetch(months_ahead=1)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_medical_society_fetches_from_members_fixture(self):
        with offline_source("medical_society", today=(2026, 6, 20)) as medical_society:
            events = medical_society.fetch(days_ahead=120)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_nougakudo_fetches_from_top_fixture(self):
        with offline_source("nougakudo", today=(2026, 6, 20)) as nougakudo:
            events = nougakudo.fetch(days_ahead=120)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])

    def test_forum_fetches_from_event_fixture(self):
        with offline_source("forum", today=(2026, 6, 20)) as forum:
            events = forum.fetch(days_ahead=120)
        self.assertGreaterEqual(len(events), 1)
        self.assert_valid_event(events[0])


class AnnualFixtureTests(EventAssertions):
    def test_annual_fetches_from_csv_fixture(self):
        annual = importlib.reload(importlib.import_module("sources.annual"))
        fixed_datetime = fixed_datetime_module(2026, 7, 1)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network disabled")):
            with mock.patch.object(annual, "datetime", fixed_datetime):
                with mock.patch.object(annual, "CSV_PATH", FIXTURE_DIR / "annual_master.csv"):
                    events = annual.fetch(days_ahead=31)
        self.assertEqual(len(events), 2)
        self.assert_valid_event(events[0])
        self.assertEqual(events[0]["name"], "Annual Test Festival")


if __name__ == "__main__":
    unittest.main()
