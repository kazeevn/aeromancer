# The Tree of Life

A second section of the dashboard reads your air through Kabbalah, on the
same terms as [the Oracle](oracle.md); `python3 -m aeromancer kabbalah --range 7d`
prints it. It uses every instrument: the zyTemp's CO₂, temperature and
humidity; the Blueair's readings and settings; NEA's outdoor PM2.5; and the
nearest station's temperature, humidity, rain and wind speed (not wind
direction, whose average means nothing). It leaves out the Blueair's CO₂,
which is recorded but is an estimate from its VOC sensor that doesn't follow
real CO₂ ([study](archive/blueair-eco2.md)). The tree walks on the zyTemp's
CO₂.

| Finding | What is actually computed |
|---|---|
| Tree of Life | each CO₂ reading placed on a sefira by its level (height on the tree) and its smoothed trend (the pillar: Severity rising, Balance steady below 0.5 ppm/min, Mercy falling); time spent in each, and how often the air moved along each of the 22 paths (Golden Dawn letters) or leapt between sefirot no path joins; every other instrument's mean while the air was in each sefira, and the one that differs most between sefirot (relative to its own spread) |
| Gematria | mean ppm as a Hebrew numeral, and the word in a small lexicon whose standard (mispar hechrachi) value is nearest it and the latest reading; the sum of all instruments' rounded means, units ignored, and its nearest word |
| Atbash | the mean's Hebrew numeral with the alphabet swapped end for end (א↔ת, ב↔ש, …), its value and nearest word; and the instrument whose mirrored mean lands closest to another instrument's mean |
| Week of creation | mean CO₂ per weekday, each under its sefira as in the counting of the Omer (Sunday Chesed … Shabbat Malkhut); which instruments read lower on Shabbat than the other days' average |
| Breaking of the vessels | seven vessels, one per lower sefira: zyTemp CO₂ ≥ 1000 ppm, Blueair VOC ≥ 300 ppb (the choir's comfort limit), indoor PM2.5 ≥ 15 and PM10 ≥ 45 µg/m³ and outdoor PM2.5 ≥ 15 µg/m³ (WHO 2021 24-hour guidelines), both humidities ≥ 70 %; times each reached its limit (shattered) and fell back below 95 % of it (mended), share of time above, longest stretch |
| Name-finding | each instrument's readings spelled one letter each (value modulo 22); each chant searched for 20 short Hebrew words, against how many the same letters would give shuffled |
| Nothing is a coincidence | CO₂'s peak, trough, mean, swing, latest reading, hour of the peak and minutes ≥ 1000 ppm, and every other instrument's peak and mean, each checked against traditional numbers (26, 72, 613, …) and the words' values: equal, reversed, contained in its digits, digit sum, or a multiple; how many of all those comparisons matched |

Atbash, Name-finding and the coincidences borrow their methods from Scott
Alexander's novel [Unsong](https://unsongbook.com/): letter substitution,
brute-force Name-finding, and the conviction that nothing is a coincidence.
