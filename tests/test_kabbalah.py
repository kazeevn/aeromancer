import math
import unittest

from aeromancer import kabbalah

START = 1_790_000_000.0


def breathing_room(days=8, step=300):
    return [(START + i * step, 700 + 400 * math.sin(i * step / 86400 * 2 * math.pi)) for i in range(days * 86400 // step)]


class GematriaTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(kabbalah.gematria("חי"), 18)
        self.assertEqual(kabbalah.gematria("שלום"), 376)
        self.assertEqual(kabbalah.gematria("קבלה"), 137)
        self.assertEqual(kabbalah.gematria("אור אין סוף"), 414)  # spaces count nothing, final forms their letter

    def test_numerals(self):
        self.assertEqual(kabbalah.hebrew_numeral(1), "א׳")
        self.assertEqual(kabbalah.hebrew_numeral(15), "ט״ו")
        self.assertEqual(kabbalah.hebrew_numeral(16), "ט״ז")
        self.assertEqual(kabbalah.hebrew_numeral(734), "תשל״ד")
        self.assertEqual(kabbalah.hebrew_numeral(999), "תתקצ״ט")
        self.assertEqual(kabbalah.hebrew_numeral(5786), "ה׳תשפ״ו")
        self.assertEqual(kabbalah.hebrew_numeral(2000), "ב׳")
        with self.assertRaises(ValueError):
            kabbalah.hebrew_numeral(0)

    def test_numerals_sum_to_their_value(self):
        for n in range(1, 3000):  # the thousands are written by their count, so 1234 adds up to 1 + 234
            self.assertEqual(kabbalah.gematria(kabbalah.hebrew_numeral(n)), n // 1000 + n % 1000)

    def test_nearest_word(self):
        f = kabbalah.gematria_reading([(START, 858.0)])
        self.assertEqual((f["word"], f["value"]), ("נשמת חיים", 858))


class TreeTest(unittest.TestCase):
    def test_tree_shape(self):
        names = {s[0] for s in kabbalah.SEFIROT}
        self.assertEqual(len(names), 10)
        self.assertEqual(len(kabbalah.PATHS), 22)
        self.assertEqual(len({frozenset((a, b)) for *_, a, b in kabbalah.PATHS}), 22)
        self.assertTrue(all(a in names and b in names for *_, a, b in kabbalah.PATHS))

    def test_sefira_of(self):
        self.assertEqual(kabbalah.sefira_of(450, "steady"), "Keter")
        self.assertEqual(kabbalah.sefira_of(3000, "steady"), "Malkhut")
        self.assertEqual(kabbalah.sefira_of(700, "rising"), "Gevurah")
        self.assertEqual(kabbalah.sefira_of(1500, "falling"), "Netzach")

    def test_residency_and_bands(self):
        f = kabbalah.tree_of_life(breathing_room())
        self.assertAlmostEqual(sum(s["share"] for s in f["sefirot"]), 1)
        by_name = {s["name"]: s for s in f["sefirot"]}
        self.assertEqual((by_name["Keter"]["lower"], by_name["Keter"]["upper"]), (None, 500))
        self.assertEqual((by_name["Tiferet"]["lower"], by_name["Tiferet"]["upper"]), (500, 800))
        self.assertEqual((by_name["Hod"]["lower"], by_name["Hod"]["upper"]), (1000, None))
        self.assertGreater(sum(p["count"] for p in f["paths"]), 0)

    def test_steady_air_stays_on_the_middle_pillar(self):
        f = kabbalah.tree_of_life([(START + i * 60, 900.0) for i in range(100)])
        self.assertEqual(f["headline"], "Yesod (יסוד)")
        self.assertEqual((f["leaps"], sum(p["count"] for p in f["paths"])), (0, 0))


class UnsongTest(unittest.TestCase):
    def test_chant_and_name_finding(self):
        co2 = [(START + i, v) for i, v in enumerate([415.0, 401.0, 403.0])]  # 19, 5, 7 modulo 22
        self.assertEqual(kabbalah.chant(co2), "רוח")
        f = kabbalah.llull({"co2": co2})
        self.assertEqual(f["names"][0]["word"], "רוח")
        self.assertEqual((f["excerpt"], f["mark"], f["excerpt_cut"]), ("רוח", [0, 3], [False, False]))
        self.assertEqual(kabbalah.llull({"co2": [(START, 400.0)]})["names"], [])

    def test_final_letters_are_found_in_their_plain_form(self):
        # מים ends in a final mem, which the chant spells as an ordinary one.
        co2 = [(START + i, 396.0 + kabbalah.ALEPHBET.index(c)) for i, c in enumerate("ממימ")]
        self.assertIn("מים", [n["word"] for n in kabbalah.llull({"co2": co2})["names"]])

    def test_atbash(self):
        self.assertEqual("ששך".translate(kabbalah.FINALS).translate(kabbalah.ATBASH), "בבל")  # Jeremiah 25:26
        f = kabbalah.temurah([(START, 734.0)])  # תשל״ד
        self.assertEqual((f["plain"], f["mirror"], f["value"]), ("תשלד", "אבכק", 123))

    def test_coincidence_ways(self):
        self.assertTrue(kabbalah._coincides(26, 26, "exact"))
        self.assertTrue(kabbalah._coincides(731, 137, "mirror"))
        self.assertTrue(kabbalah._coincides(1137, 137, "hidden"))
        self.assertFalse(kabbalah._coincides(137, 137, "hidden"))  # that is merely exact
        self.assertTrue(kabbalah._coincides(994, 22, "digits"))
        self.assertTrue(kabbalah._coincides(1300, 26, "multiple"))
        self.assertFalse(kabbalah._coincides(12, 4, "multiple"))  # too small a number to be sacred by division

    def test_exact_coincidences_come_first(self):
        f = kabbalah.coincidences([(START, 613.0), (START + 60, 613.0)])
        self.assertEqual((f["coincidences"][0]["way"], f["coincidences"][0]["sacred"]), ("exact", 613))
        self.assertEqual(len({c["fact"] for c in f["coincidences"]}), len(f["coincidences"]))


class FindingsTest(unittest.TestCase):
    def test_all_findings(self):
        co2 = breathing_room()
        result = kabbalah.analyze({"co2": co2}, co2[-1][0])
        self.assertEqual([f["id"] for f in result["findings"]], ["tree", "gematria", "temurah", "week", "vessels", "llull", "coincidences"])
        for f in result["findings"]:
            self.assertTrue(f["headline"] and f["body"] and f["certainty"])
        week = next(f for f in result["findings"] if f["id"] == "week")
        self.assertTrue(all(d["mean"] is not None for d in week["days"]))

    def test_tiny_and_empty_inputs(self):
        for co2 in ([(START, 600.0)], [(START + i, 600.0) for i in range(30)]):
            self.assertEqual(len(kabbalah.analyze({"co2": co2}, co2[-1][0])["findings"]), 7)
        self.assertEqual(kabbalah.analyze({}, START)["findings"], [])
        self.assertEqual(kabbalah.analyze({"co2": [], "temperature": [(START, 20.0)]}, START)["findings"], [])

    def test_vessels(self):
        co2 = [(START + i * 60, v) for i, v in enumerate([800, 1010, 980, 1020, 900, 1100, 1100])]
        v = kabbalah.vessel(co2, 1000)
        self.assertEqual((v["shattered"], v["mended"], v["broken"]), (2, 1, True))  # 980 is within the hysteresis
        self.assertAlmostEqual(v["exile_share"], 4 / 6)
        self.assertEqual(v["longest"], 180)
        pm = [(START + i * 60, v) for i, v in enumerate([10, 20, 10, 10])]
        f = kabbalah.vessels({"co2": co2, "blueair_pm25": pm, "temperature": pm})  # temperature has no vessel
        self.assertEqual([(r["key"], r["sefira"]) for r in f["vessels"]], [("co2", "Chesed"), ("blueair_pm25", "Tiferet")])
        self.assertEqual((f["shattered"], f["mended"]), (3, 2))


def room_with_everything():
    """The breathing room, with every other instrument following it or the clock."""
    co2 = breathing_room()
    series = {key: [(t, 1 + abs(v - 700) / 40 + i) for t, v in co2[::3]] for i, key in enumerate(kabbalah.INSTRUMENTS)}
    series["co2"] = co2
    return series


class AllInstrumentsTest(unittest.TestCase):
    def test_every_finding_uses_them(self):
        series = room_with_everything()
        result = kabbalah.analyze(series, series["co2"][-1][0])
        self.assertEqual(result["breath"], "co2")
        self.assertEqual([i["key"] for i in result["instruments"]], list(kabbalah.INSTRUMENTS))
        by_id = {f["id"]: f for f in result["findings"]}
        self.assertIn("walks closest in its footsteps", by_id["tree"]["body"])
        self.assertTrue(all(len(s["means"]) == len(kabbalah.INSTRUMENTS) - 1 for s in by_id["tree"]["sefirot"] if s["share"]))
        self.assertIn(f"all {len(kabbalah.INSTRUMENTS)} instruments", by_id["gematria"]["body"])
        self.assertIn("reflections of one another", by_id["temurah"]["body"])
        self.assertIn("On Shabbat", by_id["week"]["body"])
        self.assertEqual(len(by_id["vessels"]["vessels"]), len(kabbalah.VESSELS))
        self.assertEqual(len(by_id["llull"]["voices"]), len(kabbalah.INSTRUMENTS))
        facts = {c["fact"] for c in by_id["coincidences"]["coincidences"]}
        self.assertEqual(by_id["coincidences"]["comparisons"] % len(kabbalah.COINCIDENCE_WAYS), 0)
        self.assertGreater(by_id["coincidences"]["comparisons"], kabbalah.coincidences(series["co2"])["comparisons"])
        self.assertTrue(facts)

    def test_blueair_estimate_stands_in_for_a_silent_zytemp(self):
        series = room_with_everything()
        series["blueair_co2"], series["co2"] = series["co2"], []
        result = kabbalah.analyze(series, series["blueair_co2"][-1][0])
        self.assertEqual(result["breath"], "blueair_co2")
        self.assertIn("estimated CO\u2082", result["findings"][0]["body"])

    def test_malkhut_heeds_the_haze(self):
        kingdom = [(START + i * 60, 1500.0) for i in range(30)]
        self.assertIn("Open a window", kabbalah.tree_of_life(kingdom)["body"])
        self.assertIn("haze", kabbalah.tree_of_life(kingdom, outdoor_pm25=117)["body"])
        self.assertNotIn("Open a window", kabbalah.analyze({"co2": kingdom}, kingdom[-1][0], 117)["findings"][0]["body"])

    def test_tree_means_follow_the_sefira(self):
        co2 = [(START + i * 60, 450.0 if i < 50 else 1500.0) for i in range(100)]  # Keter, then Malkhut
        warm = [(t, 20.0 if v < 1000 else 30.0) for t, v in co2]
        f = kabbalah.tree_of_life(co2, {"temperature": warm})
        by_name = {s["name"]: s for s in f["sefirot"]}
        self.assertAlmostEqual(by_name["Keter"]["means"]["temperature"], 20.0)
        self.assertAlmostEqual(by_name["Malkhut"]["means"]["temperature"], 30.0)
        self.assertEqual(by_name["Chokhmah"]["means"], {})  # the air never falls, so never visits Mercy

    def test_shuffled_chance_uses_the_chants_own_letters(self):
        hits, expected = kabbalah._listen("א" * 50)  # no Name is spelled with aleph alone
        self.assertEqual((hits, expected), ({}, 0.0))
        hits, expected = kabbalah._listen("אשאשאש")
        self.assertEqual(hits["אש"], [0, 2, 4])
        self.assertAlmostEqual(expected, 5 * 0.5 * 0.5)  # 5 places for a two-letter word, each letter half the chant


if __name__ == "__main__":
    unittest.main()
