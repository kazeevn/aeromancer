import json
import math
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aeromancer import astro, lore, nea, oracle, server
from aeromancer.device import Reading
from aeromancer.store import Placement, Store, device_of, indoor_only, outdoor_intakes, samples_air

START = 1_790_000_000.0
HOUR = 3600
BASE_IDS = {"aura", "moon", "mercury", "chakra", "schumann", "golden", "numerology", "zodiac", "signals", "horoscope"}
HOUSEHOLD_IDS = {"iching", "society", "choir", "souls", "births", "clock", "elements", "winds", "ward"}
PLACED = [Placement(1, 0, "zytemp", "living room", "table"), Placement(2, 0, "blueair", "bedroom", "")]


def ts(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def breathing_room(hours=48, step=60):
    co2 = [(START + i * step, 700 + 400 * math.sin(i * step / 86400 * 2 * math.pi)) for i in range(hours * 3600 // step)]
    temp = [(t, 21 + v / 1000) for t, v in co2]
    return co2, temp


def daily(times, peak_utc_hour, mean, amplitude):
    return [(t, mean + amplitude * math.cos(2 * math.pi * (t - peak_utc_hour * HOUR) / 86400)) for t in times]


def household(hours=48):
    """Everything besides the meter, as ``analyze`` takes it: ``(others, regions)``."""
    times = [START + i * 300 for i in range(hours * 12)]
    hourly = times[6::12]  # NEA's, stamped mid-hour
    others = {
        "blueair_pm25": daily(times, 8, 40, 20),
        "blueair_voc": [(t, 300 + 100 * math.sin(t / 5000)) for t in times],
        "blueair_temperature": daily(times, 5, 29, 1),
        "blueair_humidity": daily(times, 17, 60, 5),
        "outdoor_pm25": daily(hourly, 7, 120, 40),
        "outdoor_temperature": daily(times, 6.5, 30, 2),
        "outdoor_humidity": daily(times, 18.5, 80, 8),
        "outdoor_wind_speed": [(t, 1.5 + math.sin(t / 7000)) for t in times],
        "outdoor_wind_direction": [(t, 225 + 20 * math.sin(t / 3000)) for t in times],
        "outdoor_rain": [(t, 1.2 if i == 100 else 0.0) for i, t in enumerate(times)],
    }
    regions = {r: daily(hourly, 7, 80 + 20 * k, 30) for k, r in enumerate(lore.ELEMENTS)}
    return others, regions


class OracleTest(unittest.TestCase):
    def test_all_findings(self):
        co2, temp = breathing_room()
        result = oracle.analyze(co2, temp, co2[0][0], co2[-1][0])
        ids = {f["id"] for f in result["findings"]}
        self.assertEqual(ids, BASE_IDS | {"iching", "society", "choir", "souls", "clock"})
        for f in result["findings"]:
            self.assertTrue(f["headline"] and f["body"] and f["certainty"])

    def test_the_whole_household(self):
        co2, temp = breathing_room()
        others, regions = household()
        born = {"zytemp": START - 86400, "blueair": START - 2 * 86400, "island": START - 7 * 86400}
        result = oracle.analyze(co2, temp, co2[0][0], co2[-1][0], others=others, regions=regions, placements=PLACED, born=born, home=(1.35, 103.85))
        self.assertEqual({f["id"] for f in result["findings"]}, BASE_IDS | HOUSEHOLD_IDS)
        for f in result["findings"]:
            self.assertTrue(f["headline"] and f["body"] and f["certainty"], f["id"])
        json.dumps(result, allow_nan=False)  # what the dashboard is sent
        horoscope = next(f for f in result["findings"] if f["id"] == "horoscope")
        self.assertIn("I Ching", horoscope["body"])

    def test_schumann_finds_daily_rhythm(self):
        co2, temp = breathing_room()
        f = oracle.schumann(co2)
        self.assertAlmostEqual(f["period_s"] / 86400, 1, delta=0.05)

    def test_chakra_shares_sum_to_one(self):
        co2, _ = breathing_room()
        self.assertAlmostEqual(sum(b["share"] for b in oracle.chakra_residency(co2)["bands"]), 1)

    def test_tiny_and_flat_inputs(self):
        for co2 in ([(START, 600.0)], [(START + i, 600.0) for i in range(30)]):
            result = oracle.analyze(co2, [], co2[0][0], co2[-1][0])
            self.assertLessEqual(BASE_IDS, {f["id"] for f in result["findings"]})
            for f in result["findings"]:
                self.assertTrue(f["headline"] and f["body"], f["id"])
        self.assertEqual(oracle.analyze([], [], START, START + 1)["findings"], [])
        others, regions = household(hours=1)
        result = oracle.analyze([], [], START, START + HOUR, others=others, regions=regions)  # no meter, a short window
        for f in result["findings"]:
            self.assertTrue(f["headline"] and f["body"], f["id"])
        json.dumps(result, allow_nan=False)

    def test_voices_identify_signals(self):
        co2, _ = breathing_room()
        temp = [(t, 21 + math.sin((t - START) / 3600)) for t, _ in co2]  # unrelated to CO2
        signals = {
            "op_4f": [(t, v - 60) for t, v in co2],
            "op_52": [(t + 1, 4000 - v * 10) for t, v in temp],
            "op_57": [(t, (i * 7919) % 13) for i, (t, _) in enumerate(co2)],
            "op_56": [(t, 7000 + (t - START) / 3600) for t, _ in co2],
            "op_6d": [(t, 3247.0) for t, _ in co2],  # constant
            "op_4a": [(co2[0][0], 711.0), (co2[-1][0], 710.0)],  # sent only at power-up
            "op_71": [(t, v - 60) for t, v in co2],  # explained
        }
        f = oracle.voices(signals, co2, temp, co2[0][0], co2[-1][0])
        by_op = {s["op"]: s for s in f["signals"]}
        self.assertEqual(set(by_op), {"0x4f", "0x52", "0x57", "0x56"})
        self.assertEqual(by_op["0x4f"]["persona"], "Echo of the Breath")
        self.assertEqual(by_op["0x52"]["persona"], "Frost Spirit")
        self.assertEqual(by_op["0x57"]["persona"], "The Trickster")
        self.assertEqual(by_op["0x56"]["persona"], "The Ascender")
        self.assertEqual(oracle.voices({}, co2, temp, 0, 1)["headline"], "Silence")

    def test_airing_heeds_the_haze(self):
        self.assertIn("Open a window", oracle.airing(None))  # no outdoor data: assume the outside is fine
        self.assertIn("Open a window", oracle.airing(oracle.AIRING_PM25 - 1))
        hazy = oracle.airing(117)
        self.assertNotIn("Open a window", hazy)
        self.assertIn("117 µg/m³", hazy)
        root = [(START + i * 60, 2500.0) for i in range(30)]  # Root chakra, which used to say "Open a window"
        self.assertNotIn("Open a window", oracle.chakra_residency(root, 117)["body"])
        self.assertIn("Open a window", oracle.chakra_residency(root)["body"])

    def test_numerology(self):
        self.assertEqual(oracle._digital_root(669), 3)
        self.assertEqual(oracle._digital_root(902), 11)



class HouseholdTest(unittest.TestCase):
    def test_iching_lines_follow_their_casters(self):
        end = START + 10 * HOUR + 600
        rising = lambda base: [(end - 3 * HOUR + i * 60, base + i) for i in range(170)]
        falling = lambda base: [(end - 3 * HOUR + i * 60, base - i * 0.01) for i in range(170)]
        series = {"co2": rising(800), "temperature": rising(20), "blueair_pm25": falling(50), "outdoor_pm25": rising(100), "outdoor_wind_speed": falling(5)}
        f = oracle.iching(series, end)
        waxing = astro.moon_age(end // HOUR * HOUR) < astro.SYNODIC_MONTH / 2
        expected = [True, True, False, True, False, waxing]
        self.assertEqual([line["yang"] for line in f["lines"]], expected)
        self.assertEqual(f["number"], lore.hexagram(expected))
        self.assertFalse(any(line["changing"] for line in f["lines"][:5]))  # steady changes are young lines
        self.assertEqual(f["trigrams"][0]["lines"], expected[:3])

    def test_iching_changing_and_silent_lines(self):
        end = START + 10 * HOUR
        jump = [(end - 6 * HOUR + i * 60, 800 + i + (9 * (i - 300) if i >= 300 else 0)) for i in range(360)]  # ten times faster in the last hour
        f = oracle.iching({"co2": jump}, end)
        self.assertEqual(f["lines"][0]["value"], 9)
        self.assertEqual([line["coins"] for line in f["lines"]], [False, True, True, True, True, False])
        if f["becomes"]:
            self.assertNotEqual(f["becomes"]["number"], f["number"])
        self.assertIsNone(oracle.iching({}, end))  # all coins and no data is not a reading

    def test_society_finds_soulmates_and_nemeses(self):
        times = [START + i * 300 for i in range(2 * 288)]
        guests = {
            "co2": [(t, math.sin(t / 5000)) for t in times],
            "blueair_voc": [(t, 2 * math.sin(t / 5000) + 0.01 * math.cos(t)) for t in times],
            "outdoor_humidity": [(t, -math.sin(t / 5000)) for t in times],
        }
        f = oracle.society(guests, times[0], times[-1], PLACED)
        self.assertEqual(set(f["soulmates"]), {"co2", "blueair_voc"})
        self.assertEqual(set(f["nemeses"]), {"co2", "outdoor_humidity"})
        members = [m["id"] for m in f["members"]]
        self.assertIn("sun", members)
        self.assertNotIn("moon", members)  # less than a week: it would only stand in for time
        self.assertIn("live apart, in the living room and the bedroom", f["body"])
        self.assertNotIn("sun", [m["id"] for m in oracle.society(guests, times[-1] - 6 * HOUR, times[-1])["members"]])

    def test_choir_mood_follows_the_air(self):
        times = [START + i * 300 for i in range(12 * 12)]
        flat = lambda v: [(t, v) for t in times]
        good_in, bad_in = {"co2": flat(550), "temperature": flat(24)}, {"co2": flat(1900), "temperature": flat(30)}
        good_out, bad_out = {"outdoor_pm25": flat(8)}, {"outdoor_pm25": flat(180)}
        songs = {
            (i, o): oracle.choir({**inside, **outside})
            for i, inside in (("good", good_in), ("bad", bad_in))
            for o, outside in (("good", good_out), ("bad", bad_out))
        }
        self.assertEqual({k: f["headline"] for k, f in songs.items()}, {
            ("good", "good"): "Serenade", ("good", "bad"): "Sanctuary", ("bad", "good"): "Longing", ("bad", "bad"): "Dirge",
        })
        modes = {k: {a["id"]: a["mode"] for a in f["airs"]} for k, f in songs.items()}
        self.assertLess(modes["good", "bad"]["inside"], modes["good", "bad"]["outside"])  # a bright house in a dark world
        self.assertGreater(modes["bad", "good"]["inside"], modes["bad", "good"]["outside"])  # and the other way round
        self.assertEqual(lore.MODES[modes["bad", "bad"]["inside"]][0], "Locrian")
        bpm = {k: f["tempo"]["bpm"] for k, f in songs.items()}
        self.assertGreater(bpm["good", "good"], bpm["good", "bad"])
        self.assertGreater(bpm["good", "bad"], bpm["bad", "good"])  # the air inside weighs more on the tempo
        self.assertGreater(bpm["bad", "good"], bpm["bad", "bad"])
        sanctuary = {a["id"]: a for a in songs["good", "bad"]["airs"]}
        self.assertEqual((sanctuary["inside"]["shift"], sanctuary["outside"]["shift"]), (0, -12))  # the heavy world sinks
        self.assertEqual(sanctuary["outside"]["worst"], "outdoor_pm25")
        self.assertIn("differ in", songs["good", "bad"]["body"])

    def test_choir_leitmotifs_trace_their_guests(self):
        times = [START + i * 300 for i in range(12 * 12)]
        rising = [(t, 500 + 300 * i / len(times)) for i, t in enumerate(times)]
        f = oracle.choir({"co2": rising})
        breath = next(t for t in f["themes"] if t["id"] == "co2")
        phrase = [m for b, m, _, _ in breath["notes"] if b < oracle.PHRASE_BEATS]
        self.assertEqual(phrase, sorted(phrase))
        self.assertGreater(phrase[-1], phrase[0])
        self.assertEqual(breath["theme"], "breath")
        self.assertEqual(len(f["sections"]), 2)  # a lone house sings its phrase twice
        # The level matters now: the same line, higher, is a heavier song.
        heavy = oracle.choir({"co2": [(t, v + 1000) for t, v in rising]})
        self.assertGreater(heavy["airs"][0]["mode"], f["airs"][0]["mode"])
        self.assertGreater(heavy["themes"][0]["notes"][0][3], breath["notes"][0][3])  # and the sufferer sings louder

    def test_choir_ground_rain_and_wind(self):
        times = [START + i * 300 for i in range(12 * 12)]
        f = oracle.choir({
            "co2": [(t, 600) for t in times],
            "blueair_fan_speed": [(t, 3) for t in times],
            "outdoor_rain": [(t, 0.5) for t in times],  # 6 mm/h
            "outdoor_wind_speed": [(t, 0.2) for t in times],  # calm
        })
        themes = {t["id"]: t for t in f["themes"]}
        sections = len(f["sections"])
        self.assertEqual(len(themes["blueair_fan_speed"]["notes"]), 2 * 3 * 4)  # three pulses each two beats, in both of its sections
        self.assertEqual(len(themes["outdoor_rain"]["notes"]), 2 * 6 * oracle.PHRASE_BEATS)  # as many drops as it allows
        self.assertEqual(themes["outdoor_wind_speed"]["notes"], [])
        self.assertEqual(sections, 3)
        self.assertIn("ground bass", f["body"])
        self.assertIn("Raindrop", f["body"])
        self.assertNotIn("Aeolian harp", f["body"])
        self.assertEqual(f["airs"][1]["worst"], "outdoor_rain")

    def test_choir_tonic_from_the_rhythms(self):
        f = oracle.choir({"co2": [(START + i * 60, 800 + 50 * math.sin(2 * math.pi * i / 120)) for i in range(12 * 60)]})
        self.assertAlmostEqual(f["earth"]["cents"], 25, delta=1)  # 7.83 Hz raised 6 octaves is a sharp B
        self.assertEqual(f["earth"]["note"], "B")
        self.assertIsNotNone(oracle._tonic({"co2": [(START + i * 60, math.sin(i / 20)) for i in range(12 * 60)]}))
        short = oracle.choir({"co2": [(START, 800), (START + 600, 820)]})
        self.assertEqual(short["tonic"], 11)  # with no rhythm to go on, the Earth's B
        self.assertTrue(short["key"].startswith("B "))

    def test_key_finding(self):
        self.assertEqual(oracle._key([60, 64, 67]), (0, "major"))  # C E G
        self.assertEqual(oracle._key([57, 60, 64, 69]), (9, "minor"))  # A C E A

    def test_souls_from_a_known_crowd(self):
        souls, air_changes, volume = 1.5, 1.0, oracle.ROOM_VOLUMES["living room"]
        c, co2 = oracle.OUTDOOR_CO2, []
        for i in range(6 * 60):  # six hours from fresh air, a reading a minute
            co2.append((START + i * 60, c))
            c += (souls * oracle.EXHALED * 1000 / volume - air_changes * (c - oracle.OUTDOOR_CO2)) / 60
        f = oracle.souls(co2, PLACED, co2[-1][0])
        self.assertTrue(f["fitted"])
        self.assertAlmostEqual(f["air_changes"], air_changes, delta=0.05)
        self.assertAlmostEqual(f["souls"], souls, delta=0.1)
        self.assertEqual((f["room"], f["volume"]), ("living room", 60))
        self.assertEqual(oracle.souls(co2[:3])["souls"], None)

    def test_births_and_the_fire_horse(self):
        born = {"zytemp": ts("2026-10-17T10:42"), "blueair": ts("2026-02-16T12:00")}  # 20:00 in China, the eve of the new year
        f = oracle.births(born, ts("2026-10-17T20:00"))
        meter, purifier = f["members"]
        self.assertEqual((meter["element"], meter["animal"]), ("Fire", "Horse"))
        self.assertEqual((purifier["element"], purifier["animal"]), ("Wood", "Snake"))
        self.assertEqual(f["headline"], "2 members")
        self.assertTrue(all(r["critical"] for r in meter["rhythms"]))  # born this morning: every cycle at zero
        family = oracle.births({"zytemp": ts("2026-10-17T10:42"), "blueair": ts("2026-10-16T12:00")}, ts("2026-10-18T00:00"))
        self.assertEqual(family["headline"], "A family of Fire Horses")
        self.assertIn("1966", family["body"])
        self.assertIsNone(oracle.births({}, START))

    def test_clock_places_rhythms_and_aspects(self):
        times = [START + i * 600 for i in range(2 * 144)]
        guests = {"outdoor_temperature": daily(times, 6, 30, 2), "outdoor_humidity": daily(times, 14, 80, 8)}  # 8 h, 120°, apart
        f = oracle.clock(guests, times[0], times[-1], home=(0.0, 0.0))
        planets = {p["id"]: p for p in f["planets"]}
        noon_utc = times[-1] // 86400 * 86400
        self.assertAlmostEqual(planets["outdoor_temperature"]["hour"], astro.solar_hours(noon_utc + 6 * HOUR, 0.0), delta=0.05)
        self.assertEqual(planets["outdoor_temperature"]["house"], lore.house(planets["outdoor_temperature"]["hour"]))
        self.assertEqual((planets["sun"]["hour"], planets["sun"]["house"]), (12.0, 10))
        trines = [{a["a"], a["b"]} for a in f["aspects"] if a["kind"] == "trine"]
        self.assertIn({"outdoor_temperature", "outdoor_humidity"}, trines)
        self.assertEqual(len(f["hours"]), 24)
        self.assertIn(f["ruler"], astro.CHALDEAN)
        recent = {"co2": [(START, 1.0), (START + HOUR, 2.0)]}
        self.assertIn("window this short", oracle.clock(recent, START, START + HOUR)["body"])
        self.assertIn("not yet lived a full day", oracle.clock(recent, START + HOUR - 86400, START + HOUR)["body"])

    def test_elements_and_the_flow_of_qi(self):
        times = [START + 1800 + i * HOUR for i in range(48)]
        wave = [math.sin(i / 3) for i in range(60)]
        levels = {"west": (150, 2), "east": (100, 1), "north": (60, 0), "south": (90, 0), "central": (110, 0)}  # (mean, hours ahead)
        regions = {r: [(t, mean + 20 * wave[i + ahead]) for i, t in enumerate(times)] for r, (mean, ahead) in levels.items()}
        f = oracle.elements(regions)
        self.assertEqual((f["excess"], f["colour"], f["weakest"]), ("Metal", "red", "north"))  # Fire melts Metal
        self.assertEqual(f["flow"]["first"], "west")
        self.assertEqual([e["element"] for e in f["elements"]], list(lore.GENERATES))
        self.assertEqual(oracle.elements({"west": regions["west"]})["headline"], "Incomplete")
        self.assertIsNone(oracle.elements({}))

    def test_winds(self):
        times = [START + i * 300 for i in range(100)]
        direction = [(t, 225.0 if i % 4 else 90.0) for i, t in enumerate(times)]
        speed = [(t, 0.2 if i % 10 == 0 else 2.0) for i, t in enumerate(times)]
        rain = [(t, 0.5 if i == 50 else 0.0) for i, t in enumerate(times)]
        f = oracle.winds(direction, speed, rain)
        prevailing = f["sectors"][f["prevailing"]]
        self.assertEqual((prevailing["abbr"], prevailing["wind"], prevailing["trigram"][0]), ("SW", "Lips", "Kun"))
        self.assertAlmostEqual(f["calm"], 0.1)
        self.assertAlmostEqual(f["rain_mm"], 0.5)
        self.assertIsNone(oracle.winds([]))

    def test_ward(self):
        outdoor = [(START + 1800 + h * HOUR, 100 + 10 * math.sin(h)) for h in range(24)]
        indoor = [(START + m * 300, 0.3 * (100 + 10 * math.sin((m * 300 - 1800) / HOUR))) for m in range(24 * 12)]
        f = oracle.ward(indoor, outdoor, PLACED)
        self.assertAlmostEqual(f["strength"], 0.7, delta=0.03)
        self.assertEqual((f["lag_h"], f["breaches"], f["band"]), (0, 0, "II"))
        self.assertIn("in the bedroom", f["body"])
        self.assertIsNone(oracle.ward([], outdoor))
        # Moved to draw outside air, its readings since are left out; the room is where it last read the house's.
        moved = PLACED + [Placement(3, START + 20 * HOUR, "blueair", "living room", "", True)]
        f = oracle.ward(indoor_only("blueair_pm25", indoor, moved), outdoor, moved)
        self.assertIn("in the bedroom", f["body"])
        self.assertLess(f["hours"][-1][0], START + 20 * HOUR)

    def test_horoscope_minds_the_haze(self):
        co2, _ = breathing_room()
        findings = [{"id": "moon", "headline": "Full Moon"}, {"id": "mercury", "retrograde": False, "shadow": None}]
        bodies = lambda haze: [oracle.horoscope(co2, START + day * 86400, findings, haze)["body"] for day in range(40)]
        self.assertTrue(any("air out the bedroom" in b for b in bodies(None)))
        self.assertFalse(any("air out" in b for b in bodies(120.0)))

    def test_mercury_in_shadow(self):
        end = ts("2026-10-17T12:00")
        f = oracle.mercury([(end - 60, 1100.0), (end, 1100.0)], end - HOUR, end)
        self.assertEqual((f["headline"], f["shadow"]["kind"]), ("Direct, in shadow", "pre"))
        self.assertIn("half the blame", f["body"])
        self.assertLess(f["cycle"]["shadow_start"], end, f["cycle"]["retrograde"])


class RunOracleTest(unittest.TestCase):
    def test_from_the_database(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            t0 = time.time() - 30 * HOUR
            readings = []
            for i in range(30 * 12):
                t = t0 + i * 300
                readings += [
                    Reading(t, "co2", 800 + 200 * math.sin(i / 20)),
                    Reading(t, "temperature", 25 + math.sin(i / 30)),
                    Reading(t, "blueair_pm25", 30 + 10 * math.sin(i / 25)),
                    Reading(t, "blueair_temperature", 29 + math.cos(i / 40)),
                    Reading(t, "nea_temperature_S1", 30 + 2 * math.sin(i / 50)),
                    Reading(t, "nea_humidity_S1", 80 - 5 * math.sin(i / 50)),
                    Reading(t, "nea_wind_speed_S1", 2 + math.sin(i / 7)),
                    Reading(t, "nea_wind_direction_S1", 200 + 30 * math.sin(i / 9)),
                    Reading(t, "nea_rain_S2", 0.4 if i == 300 else 0.0),
                ]
                if i % 12 == 6:
                    readings += [Reading(t, nea.PREFIX + r, 100 + 10 * k + 20 * math.sin(i / 40)) for k, r in enumerate(nea.REGIONS)]
            store.add(readings)
            store.add_stations([("S1", "Station 1", 1.351, 103.85), ("S2", "Station 2", 1.36, 103.85)])
            store.place(0, "zytemp", "living room", "table")
            store.place(0, "blueair", "bedroom")
            self.assertEqual(store.first_ts("blueair_*"), t0)
            result = server.run_oracle(store, "24h", "central", (1.35, 103.85))
            by_id = {f["id"]: f for f in result["findings"]}
            self.assertLessEqual(HOUSEHOLD_IDS | {"horoscope"}, set(by_id))
            self.assertAlmostEqual(by_id["winds"]["rain_mm"], 0.4)  # from the nearest station that measures rain
            self.assertEqual(by_id["births"]["members"][0]["born"], t0)
            json.dumps(result, allow_nan=False)
            store.close()


class StoreTest(unittest.TestCase):
    def test_bucketed_series(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            store.add(Reading(START + i, "co2", 400 + i) for i in range(100))
            store.add([Reading(START, "temperature", 20.0)])
            rows = store.series("co2", START, START + 99, 10)
            self.assertEqual(len(rows), 10)
            ts, mean, lo, hi = rows[0]
            self.assertEqual((lo, hi), (400, 409))
            self.assertAlmostEqual(mean, 404.5)
            self.assertEqual(store.latest()["co2"][1], 499)
            self.assertEqual(store.latest_of("co2"), (START + 99, 499))
            self.assertEqual(store.latest_of("co2", before=START + 50), (START + 49, 449))
            self.assertIsNone(store.latest_of("co2", before=START))
            led = store.series("co2", START + 50, START + 99, 10, lead=True)
            self.assertEqual(led[0], (START + 49, 449, 449, 449))
            self.assertEqual(led[1:], store.series("co2", START + 50, START + 99, 10))
            self.assertEqual(store.series("co2", START, START + 99, 10, lead=True), rows)  # nothing before
            self.assertEqual(store.series("co2", START + 200, START + 300, 10, lead=True), [])  # nothing in it
            self.assertEqual(store.count(), 101)
            self.assertEqual(store.signal_names(), [])
            store.add([Reading(START, "op_71", 1.0), Reading(START, "op_6d", 2.0), Reading(START, "humidity", 3.0)])
            self.assertEqual(store.signal_names(), ["op_6d", "op_71"])
            store.close()

    def test_placements(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            self.assertIsNone(store.placement_at("zytemp", START))
            store.place(0, "zytemp", "living room", "table")
            store.place(0, "blueair", "bedroom")
            wrong = store.place(START + 50, "zytemp", "bedroom", "on the purifier")
            store.place(START + 100, "zytemp", "bedroom", "floor, by the intake")
            self.assertEqual(store.placement_at("zytemp", START).room, "living room")
            self.assertEqual(store.placement_at("zytemp", START + 60).spot, "on the purifier")
            self.assertTrue(store.unplace(wrong))
            self.assertFalse(store.unplace(wrong))
            self.assertEqual(store.placement_at("zytemp", START + 60).room, "living room")
            self.assertEqual(store.placement_at("zytemp", START + 100).spot, "floor, by the intake")
            self.assertEqual(store.placement_at("blueair", START + 100).room, "bedroom")
            store.place(START + 100, "zytemp", "bedroom", "floor, 10 cm from the intake")  # a correction
            self.assertEqual(store.placement_at("zytemp", START + 100).spot, "floor, 10 cm from the intake")
            self.assertEqual([p.device for p in store.placements()], ["zytemp", "blueair", "zytemp", "zytemp"])
            self.assertEqual(len(store.placements("zytemp")), 3)
            with self.assertRaises(ValueError):
                store.place(START, "zytmp", "bedroom")
            store.close()

    def test_outdoor_intake(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.sqlite3"
            old = sqlite3.connect(path)  # a database from before the flag
            old.execute("CREATE TABLE placements (id INTEGER PRIMARY KEY, ts REAL NOT NULL, device TEXT NOT NULL, room TEXT NOT NULL, spot TEXT NOT NULL)")
            old.execute("INSERT INTO placements (ts, device, room, spot) VALUES (0, 'blueair', 'bedroom', '')")
            old.commit()
            old.close()
            reader = Store(path, readonly=True)  # the dashboard, before the recorder adds the flag
            self.assertFalse(reader.placements()[0].outdoor_intake)
            reader.close()
            store = Store(path)
            store.place(START + 100, "blueair", "living room", "by the door", outdoor_intake=True)
            self.assertEqual([p.outdoor_intake for p in store.placements()], [False, True])
            self.assertTrue(store.placement_at("blueair", START + 100).outdoor_intake)
            store.place(START + 200, "blueair", "bedroom")
            store.place(START + 300, "blueair", "living room", outdoor_intake=True)
            store.place(START + 400, "blueair", "kitchen", outdoor_intake=True)  # moved, still drawing outside air
            spans = outdoor_intakes(store.placements(), "blueair")
            self.assertEqual(spans, [(START + 100, START + 200), (START + 300, math.inf)])
            self.assertEqual(outdoor_intakes(store.placements(), "zytemp"), [])
            points = [(START + t, 1.0) for t in (0, 100, 150, 200, 250, 300, 500)]
            self.assertEqual([t - START for t, _ in indoor_only("blueair_pm25", points, store.placements())], [0, 200, 250])
            self.assertEqual(indoor_only("blueair_fan_speed", points, store.placements()), points)  # a setting, not the air
            self.assertEqual(indoor_only("co2", points, store.placements()), points)  # the meter's own placements
            store.close()
        self.assertTrue(samples_air("blueair_temperature") and samples_air("co2"))
        self.assertFalse(samples_air("blueair_auto_mode") or samples_air("blueair_fan_usage_4") or samples_air("nea_pm25_west"))

    def test_divinations_leave_out_outside_air(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            now = time.time()
            store.add([Reading(now - 3600 + m * 300, "blueair_pm25", 5.0 if m < 6 else 40.0) for m in range(12)])
            store.place(0, "blueair", "bedroom")
            store.place(now - 1800, "blueair", "living room", outdoor_intake=True)
            _, _, _, points = server._divination_window(store, "2h")
            self.assertEqual({v for _, v in points("blueair_pm25")}, {5.0})
            store.close()

    def test_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.sqlite3"
            with self.assertRaises(FileNotFoundError):
                Store(path, readonly=True)
            self.assertFalse(path.exists())  # and did not create it
            writer = Store(path)
            writer.add([Reading(START, "co2", 500.0)])
            reader = Store(path, readonly=True)
            self.assertEqual(reader.latest()["co2"], (START, 500.0))
            writer.add([Reading(START + 1, "co2", 600.0)])  # the recorder carries on while the dashboard reads
            self.assertEqual(reader.latest()["co2"], (START + 1, 600.0))
            for write in (
                lambda: reader.add([Reading(START + 2, "co2", 700.0)]),
                lambda: reader.place(START, "zytemp", "bedroom"),
                lambda: reader.add_stations([("S1", "x", 1.0, 2.0)]),
                lambda: reader.db.execute("CREATE TABLE IF NOT EXISTS other (x)"),
            ):
                with self.assertRaises(sqlite3.OperationalError):
                    write()
            self.assertEqual(writer.count(), 2)
            reader.close()
            writer.close()

    def test_device_of(self):
        self.assertEqual(device_of("co2"), "zytemp")
        self.assertEqual(device_of("op_71"), "zytemp")
        self.assertEqual(device_of("blueair_co2"), "blueair")
        self.assertIsNone(device_of("nea_pm25_central"))


if __name__ == "__main__":
    unittest.main()
