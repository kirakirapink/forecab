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
    "https://www.zepp.co.jp/hall/shinjuku/schedule/": "zepp_shinjuku.html",
    "https://www.shopping-sumitomo-rd.com/tokyo_garden_theater/schedule/": "garden_theater.html",
    "https://www.jpnsport.go.jp/yoyogi/event/tabid/59/Default.aspx": "yoyogi_gym1.html",
    "https://kageki.hankyu.co.jp/revue/index.html": "takarazuka_revue.html",
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

    def test_zepp_fetches_from_three_hall_fixtures(self):
        with offline_source("zepp") as zepp:
            events = zepp.fetch()
        venues = {event["venue"] for event in events}
        self.assertIn("Zepp Haneda", venues)
        self.assertIn("Zepp DiverCity", venues)
        self.assertIn("Zepp Shinjuku", venues)
        self.assertGreaterEqual(len([e for e in events if e["venue"] == "Zepp Haneda"]), 20)
        self.assertGreaterEqual(len([e for e in events if e["venue"] == "Zepp DiverCity"]), 20)
        self.assertGreaterEqual(len([e for e in events if e["venue"] == "Zepp Shinjuku"]), 20)
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
        self.assertTrue(any(
            e["venue"] == "Zepp Shinjuku"
            and e["start"] == "18:30"
            and "HIKAGE Pre. P.H.S Vol.4" in e["name"]
            for e in events
        ))
        self.assert_valid_event(events[0])

    def test_yoyogi_fetches_first_gym_events(self):
        with offline_source("yoyogi", today=(2026, 7, 4)) as yoyogi:
            events = yoyogi.fetch()
        self.assertEqual(
            len([e for e in events if e["venue"] == "国立代々木競技場 第一体育館"]),
            4,
        )
        self.assertTrue(all(e["start"] == "17:00" and e["end"] == "20:30" for e in events))
        self.assertEqual(
            {e["date"] for e in events if e["name"] == "KAWAII LAB. SESSION 2026 SUMMER"},
            {"2026-07-10", "2026-07-11"},
        )
        self.assert_valid_event(events[0])

    def test_yoyogi_infers_next_january_from_december_listing(self):
        with offline_source("yoyogi", today=(2026, 12, 20)) as yoyogi:
            rows = list(yoyogi._parse_rows(
                '<table class="event-calendar">'
                "<tr><td>12/31(木)</td><td>年末ライブ</td></tr>"
                "<tr><td>1/2(土)</td><td>新春ライブ</td></tr>"
                "</table>",
                yoyogi.datetime.date.today(),
            ))
        self.assertEqual(rows, [("2026-12-31", "年末ライブ"), ("2027-01-02", "新春ライブ")])

    def test_takarazuka_expands_tokyo_theater_runs_without_mondays(self):
        with offline_source("takarazuka") as takarazuka:
            events = takarazuka.fetch()
        self.assertGreaterEqual(len(events), 250)
        self.assertTrue(any(
            e["date"] == "2026-07-04"
            and e["name"] == "月組『RYOFU』"
            and e["start"] == "15:30"
            and e["end"] == "18:30"
            for e in events
        ))
        self.assertFalse(any(e["date"] == "2026-07-06" and e["name"] == "月組『RYOFU』" for e in events))
        self.assertTrue(any(
            e["date"] == "2027-02-07"
            and e["name"] == "花組『エリザベート－愛と死の輪舞（ロンド）－』"
            and "土日は11時回あり" in e["notes"]
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
