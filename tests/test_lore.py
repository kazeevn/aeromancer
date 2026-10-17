import unittest

from aeromancer import lore

YANG, YIN = (True,) * 3, (False,) * 3
FIRE, WATER = (True, False, True), (False, True, False)


class IChingTest(unittest.TestCase):
    def test_king_wen_numbers_each_hexagram_once(self):
        numbers = sorted(lore.hexagram(list(lower + upper)) for lower in lore.TRIGRAMS for upper in lore.TRIGRAMS)
        self.assertEqual(numbers, list(range(1, 65)))
        self.assertEqual(len(lore.HEXAGRAMS), 64)

    def test_known_hexagrams(self):
        self.assertEqual(lore.hexagram(list(YANG + YANG)), 1)
        self.assertEqual(lore.hexagram(list(YIN + YIN)), 2)
        self.assertEqual(lore.hexagram(list(YANG + YIN)), 11)  # Earth over Heaven: Peace
        self.assertEqual(lore.hexagram(list(YIN + YANG)), 12)  # Heaven over Earth: Standstill
        self.assertEqual(lore.hexagram(list(FIRE + WATER)), 63)  # Water over Fire: After Completion
        self.assertEqual(lore.hexagram(list(WATER + FIRE)), 64)
        self.assertEqual(lore.HEXAGRAMS[59 - 1], "Dispersion")


class CorrespondencesTest(unittest.TestCase):
    def test_houses_follow_the_sun(self):
        self.assertEqual(lore.house(12.0), 10)  # culminating
        self.assertEqual(lore.house(5.0), 1)  # about to rise
        self.assertEqual(lore.house(7.0), 12)  # just risen
        self.assertEqual(lore.house(19.0), 6)  # just set
        self.assertEqual(lore.house(0.5), 3)

    def test_chinese_years(self):
        self.assertEqual(lore.chinese_year(2026), ("Fire", "Horse"))
        self.assertEqual(lore.chinese_year(1966), ("Fire", "Horse"))
        self.assertEqual(lore.chinese_year(2024), ("Wood", "Dragon"))

    def test_winds_and_elements(self):
        south = next(w for w in lore.WINDS if w[0] == "S")
        self.assertEqual(lore.TRIGRAMS[south[3]][:2], ("Li", "Fire"))
        for element in lore.GENERATES:  # each overcomes the one two steps on in the generating cycle
            self.assertEqual(lore.OVERCOMES[element], lore.GENERATES[lore.GENERATES[element]])


if __name__ == "__main__":
    unittest.main()
