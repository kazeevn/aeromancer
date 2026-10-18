import datetime as dt
import math
import tempfile
import unittest
from pathlib import Path

from aeromancer import pressure
from aeromancer.device import Reading
from aeromancer.store import Store

HOME = (1.35, 103.85)  # as in test_weather
# Ogimet's CSV, as served on 2026-10-18
SYNOPS = {
    "48698": "48698,2026,10,18,06,00,AAXX 18064 48698 01540 71409 10318 20247 30079 40095 60001 70522 81838 333 60007 81820 85277=\n",
    "48679": "48679,2026,10,18,06,00,AAXX 18064 48679 11440 71504 10329 20254 30049 40086 57031 60001 70522 83232 333 83818 83364 87078==\n",
    "96091": "96091,2026,10,18,06,00,AAXX 18064 96091 31457 61605 10333 20235 30076 40098 58028 70444 8421/ 333 56009 57801 84817 84460 80860=\n",
}
AIRPORTS = {  # id -> (name, latitude, longitude, elevation), as aviationweather.gov lists them
    "WSSS": ("Singapore/Changi Intl, 4, SG", 1.368, 103.982, 17),
    "WSAP": ("Singapore/Pays, 4, SG", 1.36, 103.909, 20),
    "WSSL": ("Singapore/Seletar Arpt, 2, SG", 1.417, 103.866, 11),
    "WMKJ": ("Johore Bharu/Senai Arpt, JH, MY", 1.641, 103.67, 38),
    "WIDD": ("Batam/Hang Nadim, RI, ID", 1.121, 104.119, 26),
    "WIDN": ("Tanjung Pinang Arpt, RI, ID", 0.923, 104.532, 18),
}
T06 = dt.datetime(2026, 10, 18, 6, tzinfo=dt.timezone.utc).timestamp()


def metar(icao, ts, qnh, temp=32, dewp=24, kind="METAR"):
    name, lat, lon, elev = AIRPORTS[icao]
    hhmm = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%d%H%MZ")
    return {
        "icaoId": icao, "obsTime": int(ts), "temp": temp, "dewp": dewp, "altim": qnh, "metarType": kind,
        "rawOb": f"{kind} {icao} {hhmm} 19006KT 7000 FEW020 {temp}/{dewp} Q{qnh}", "lat": lat, "lon": lon, "elev": elev, "name": name,
    }


class FakeMetar:
    """Every airport on each hour, with QNH from ``field(ts, icao)`` (shape observed 2026-10-18)."""

    def __init__(self, field, until):
        self.field, self.until, self.asked = field, until, []

    def __call__(self, stations, end, hours):
        self.asked.append((end, hours))
        first = math.ceil((end - hours * 3600) / 3600) * 3600
        return [
            metar(i, t, self.field(t, i))
            for t in range(int(first), int(min(end, self.until)) + 1, 3600)
            for i in stations
        ]


class PressureTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.store = Store(self.dir / "x.sqlite3")
        self.addCleanup(self.store.close)

    def values(self, quantity):
        return [(ts, v) for ts, _, v in self.store.rows(quantity, 0, 2e9)]

    def test_load_altitude(self):
        path = self.dir / "zytemp.toml"
        self.assertIsNone(pressure.load_altitude(path))
        path.write_text('model = "x"\n')
        self.assertIsNone(pressure.load_altitude(path))
        path.write_text("altitude_m = 25.5\n")
        self.assertEqual(pressure.load_altitude(path), 25.5)
        path.write_text('altitude_m = "30 m"\n')
        with self.assertRaisesRegex(ValueError, "metres"):
            pressure.load_altitude(path)

    def test_parse_synop(self):
        readings = pressure.parse_synop("".join(SYNOPS.values()))
        got = {r.quantity: r.value for r in readings}
        self.assertEqual({r.ts for r in readings}, {T06})
        self.assertEqual(got["synop_msl_48698"], 1009.5)
        self.assertEqual(got["synop_pressure_48698"], 1007.9)
        self.assertEqual(got["synop_temperature_48698"], 31.8)
        self.assertEqual(got["synop_dewpoint_48698"], 24.7)
        self.assertEqual(got["synop_msl_48679"], 1008.6)
        self.assertEqual(got["synop_msl_96091"], 1009.8)
        self.assertEqual(len(readings), 12)  # nothing from section 3, whose groups also start with 1-8

    def test_parse_synop_edge_cases(self):
        self.assertEqual(pressure.parse_synop(""), [])
        self.assertEqual(pressure.parse_synop("48698,2026,10,18,03,00,AAXX 18034 48698 NIL=\n"), [])
        # 99 knots of wind add a 00fff group; 29UUU is humidity, not dew point; 3//// is missing pressure.
        line = "48698,2026,10,18,03,00,AAXX 18034 48698 01540 79999 00105 11012 29080 3//// 49985 333 10326=\n"
        got = {r.quantity: r.value for r in pressure.parse_synop(line)}
        self.assertEqual(got, {"synop_temperature_48698": -1.2, "synop_msl_48698": 998.5})
        with self.assertRaisesRegex(ValueError, "Ogimet"):
            pressure.parse_synop("Status: 501 Sorry, the server is too busy\n")

    def test_parse_metar(self):
        data = [metar("WSAP", T06, 1009), metar("WSSS", T06 + 600, 1008, kind="SPECI")]
        readings, stations = pressure.parse_metar(data)
        self.assertEqual(
            readings,
            [Reading(T06, "metar_qnh_WSAP", 1009.0), Reading(T06, "metar_temperature_WSAP", 32.0), Reading(T06, "metar_dewpoint_WSAP", 24.0)],
        )
        self.assertEqual(stations, [("WSAP", "Singapore/Pays, 4, SG", 1.36, 103.909, 20)])
        with self.assertRaisesRegex(ValueError, "METAR"):
            pressure.parse_metar({"error": "x"})

    def test_metar_msl(self):
        # At sea level, the middle of the hPa it was rounded down from.
        self.assertAlmostEqual(pressure.metar_msl(1009, 0, 305), 1009.5)
        # Up at 38 m in 30 °C air, the standard atmosphere's 15 °C overstates it by about 0.3 hPa.
        tv = pressure.virtual_temperature(32, 24)
        self.assertAlmostEqual(pressure.metar_msl(1009, 38, tv), 1009.5 - 0.29, delta=0.03)
        # 9 m per hPa here: 30 m up is about 3.4 hPa less.
        self.assertAlmostEqual(pressure.descend(1009.5, -30, tv), 1009.5 - 3.4, delta=0.1)

    def test_fit_plane(self):
        def field(x, y):
            return 1009 + 0.01 * x - 0.02 * y

        where = ((20, 5), (10, 15), (-5, 40), (30, -20))
        # Precise reports outweigh the prior on the gradient.
        self.assertAlmostEqual(pressure.fit_plane([(x, y, field(x, y), 0.01) for x, y in where]), 1009, delta=0.01)
        # Rounded ones don't: a 1 hPa step at one station barely tilts the plane, so home gets near their mean.
        steps = [(x, y, 1009.5 + (x == 30), 0.3) for x, y in where]
        self.assertAlmostEqual(pressure.fit_plane(steps), 1009.75, delta=0.2)
        self.assertIsNone(pressure.fit_plane(steps[:2]))

    def test_poll_stores_raw_and_home(self):
        def gradient(lat, lon):  # sea level, hPa: 0.5 hPa more per degree north
            return 1009.3 + 0.5 * (lat - HOME[0])

        def qnh(ts, icao):  # rounded down, as from a barometer at sea level in the standard atmosphere
            _, lat, lon, elev = AIRPORTS[icao]
            station = pressure.descend(gradient(lat, lon), -elev, pressure.virtual_temperature(32, 24))
            return math.floor(station / (1 - 0.0065 * elev / 288.15) ** 5.2559)

        def synop(station, start, end):
            return "".join(text for text in SYNOPS.values() if text.startswith(station) and start < T06 <= end)

        api = FakeMetar(qnh, T06)
        now = T06 + 1200
        n = pressure.poll_once(self.store, HOME, 30.0, now=now, get_synop=synop, get_metar=api, pause=0)
        self.assertEqual(len(api.asked), 7)  # a week back, a day a request
        self.assertEqual(n, 7 * 24 * 6 * 3 + 12)
        self.assertEqual(self.values("synop_msl_48698"), [(T06, 1009.5)])
        self.assertEqual(self.store.elevations()["WMKJ"], 38)
        self.assertIn("WSAP", self.store.stations())

        msl = dict(self.values("home_pressure_msl"))
        self.assertEqual(len(msl), 7 * 24)
        self.assertEqual(max(msl), T06)
        before = T06 - 3600  # METARs only: QNH rounding
        self.assertAlmostEqual(msl[before], gradient(*HOME), delta=0.3)
        at_home = dict(self.values("home_pressure"))
        self.assertAlmostEqual(msl[before] - at_home[before], 3.4, delta=0.1)
        # The SYNOPs replace the METARs of the same airports: Changi's 1009.5 among them.
        self.assertNotAlmostEqual(msl[T06], gradient(*HOME), delta=0.1)

        # Nothing new: nothing stored twice, and the hours stay.
        api.asked.clear()
        self.assertEqual(pressure.poll_once(self.store, HOME, 30.0, now=now, get_synop=synop, get_metar=api, pause=0), 0)
        self.assertEqual([h for h, _ in api.asked], [now])  # back to LATE before the newest
        self.assertEqual(dict(self.values("home_pressure_msl")), msl)

    def test_one_source_failing_keeps_the_other(self):
        def broken(station, start, end):
            raise OSError("Ogimet down")

        api = FakeMetar(lambda ts, icao: 1009, T06)
        with self.assertRaisesRegex(OSError, "Ogimet"):
            pressure.poll_once(self.store, HOME, None, now=T06 + 60, get_synop=broken, get_metar=api, pause=0)
        self.assertEqual(len(self.values("home_pressure_msl")), 7 * 24)
        self.assertEqual(self.values("home_pressure"), [])  # without the altitude, sea level only


if __name__ == "__main__":
    unittest.main()
