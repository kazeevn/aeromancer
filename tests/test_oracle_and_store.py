import math
import tempfile
import unittest
from pathlib import Path

from aeromancer import oracle
from aeromancer.device import Reading
from aeromancer.store import Store, device_of

START = 1_790_000_000.0


def breathing_room(hours=48, step=60):
    co2 = [(START + i * step, 700 + 400 * math.sin(i * step / 86400 * 2 * math.pi)) for i in range(hours * 3600 // step)]
    temp = [(t, 21 + v / 1000) for t, v in co2]
    return co2, temp


class OracleTest(unittest.TestCase):
    def test_all_findings(self):
        co2, temp = breathing_room()
        result = oracle.analyze(co2, temp, co2[0][0], co2[-1][0])
        ids = {f["id"] for f in result["findings"]}
        self.assertEqual(ids, {"aura", "moon", "mercury", "chakra", "schumann", "golden", "numerology", "zodiac", "signals", "horoscope"})
        for f in result["findings"]:
            self.assertTrue(f["headline"] and f["body"] and f["certainty"])

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
            self.assertEqual(len(result["findings"]), 10)
        self.assertEqual(oracle.analyze([], [], START, START + 1)["findings"], [])

    def test_voices_identify_signals(self):
        co2, _ = breathing_room()
        temp = [(t, 21 + math.sin((t - START) / 3600)) for t, _ in co2]  # unrelated to CO2
        signals = {
            "op_71": [(t, v - 60) for t, v in co2],
            "op_43": [(t + 1, 4000 - v * 10) for t, v in temp],
            "op_6d": [(t, 3247.0) for t, _ in co2],
            "op_6e": [(t, (i * 7919) % 13) for i, (t, _) in enumerate(co2)],
            "op_4f": [(t, 7000 + (t - START) / 3600) for t, _ in co2],
        }
        f = oracle.voices(signals, co2, temp, co2[0][0], co2[-1][0])
        by_op = {s["op"]: s for s in f["signals"]}
        self.assertEqual(by_op["0x71"]["persona"], "Echo of the Breath")
        self.assertEqual(by_op["0x43"]["persona"], "Frost Spirit")
        self.assertEqual(by_op["0x6d"]["persona"], "The Sleeper")
        self.assertEqual(by_op["0x6e"]["persona"], "The Trickster")
        self.assertEqual(by_op["0x4f"]["persona"], "The Ascender")
        self.assertEqual(oracle.voices({}, co2, temp, 0, 1)["headline"], "Silence")

    def test_numerology(self):
        self.assertEqual(oracle._digital_root(669), 3)
        self.assertEqual(oracle._digital_root(902), 11)


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

    def test_device_of(self):
        self.assertEqual(device_of("co2"), "zytemp")
        self.assertEqual(device_of("op_71"), "zytemp")
        self.assertEqual(device_of("blueair_co2"), "blueair")
        self.assertIsNone(device_of("nea_pm25_central"))


if __name__ == "__main__":
    unittest.main()
