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
| Week of creation | mean CO₂ per weekday, each under one of the seven lower sefirot in the order the Omer counts its days (Sunday Chesed … Shabbat Malkhut, a modern convention); which instruments read lower on Shabbat than the other days' average |
| Breaking of the vessels | seven vessels, one per lower sefira: zyTemp CO₂ ≥ 1000 ppm, Blueair VOC ≥ 300 ppb (the choir's comfort limit), indoor PM2.5 ≥ 15 and PM10 ≥ 45 µg/m³ and outdoor PM2.5 ≥ 15 µg/m³ (WHO 2021 24-hour guidelines), both humidities ≥ 70 %; times each reached its limit (shattered) and fell back below 95 % of it (mended), share of time above, longest stretch |
| Name-finding | each instrument's readings spelled one letter each (value modulo 22); each chant searched for 20 short Hebrew words, against how many the same letters would give shuffled |
| Nothing is a coincidence | CO₂'s peak, trough, mean, swing, latest reading, hour of the peak and minutes ≥ 1000 ppm, and every other instrument's peak and mean, each checked against traditional numbers (26, 72, 613, …) and the words' values: equal, reversed, contained in its digits, digit sum, or a multiple; how many of all those comparisons matched |

Atbash, Name-finding and the coincidences borrow their methods from Scott
Alexander's novel [Unsong](https://unsongbook.com/): letter substitution,
brute-force Name-finding, and the conviction that nothing is a coincidence.

## Prophecies

As in [the Oracle](oracle.md#prophecies), every finding also foretells,
counsels and reveals, from the same readings; the tree, gematria, Atbash and
the week are seers in [the council](prophecy.md).

| Finding | Foretold, and how | Counsel; revealed |
|---|---|---|
| Tree of Life | a Markov chain over the sefirot, each hourly cell (ten-minute ones under 12 h) placed by its CO₂ and its change from the cell before: the likeliest sefira next, and the path that joins them, with what the path's letter means (an ox, a house, …, a window) | the fewest paths from where the air is to Tiferet, Beauty (500–800 ppm and steady), by breadth-first search; where the chain dwells in the long run, and the letter of the most worn path |
| Gematria | at the pace of the last hour (least squares), when the CO₂ will spell the next word ahead of it in the lexicon, and the air rests there: rising past 1000 ppm it spells שבירת הכלים, the breaking of the vessels, at 1017 | what the word asks (an open window, חלון פתוח at 588, follows the haze); any instrument whose mean leans to the same word as the newest breath |
| Atbash | the mirror of the newest breath is the air to come | lighter or heavier air ahead, by the mirror; that Atbash undoes itself |
| Week of creation | tomorrow's mean CO₂, from the window's same weekday; the seer, the mean at the same weekday and hour | the lightest day for guests; the air's own Shabbat, the weekday its CO₂ varies least |
| Breaking of the vessels | at each instrument's pace over its last hour, when the next vessels shatter or are mended (below 95 % of the limit) | how to mend the one longest broken, or spare the next to break; when the household will have raised Luria's 288 sparks, at its pace of mending |
| Name-finding | the next Name the chant will speak and when: one over the chance its letters fall in a row (the chant's own letter frequencies), over its pace in letters a second | the virtue of the Name heard most often; how often all the instruments together would speak the Tetragrammaton, יהוה |
| Nothing is a coincidence | at the pace of the last hour, when the CO₂ passes the next sacred number or multiple of 26 ahead of it | to be in the room then; the sacred number its numbers match most often |

## Sources

As with [the Oracle's](oracle.md#sources), cited for what the traditions
say, not because it is so.

- **Tree of Life**: the tree the Golden Dawn drew after Athanasius Kircher's
  *Oedipus Aegyptiacus* (1652–54), its 22 paths' letters, and what each
  letter's name means: [Crowley], [*777*](https://archive.org/details/aleister-crowley-liber-777)
  (1909), Table I. The 32 paths of wisdom, ten sefirot and 22 letters:
  [Sefer Yetzirah 1:1–2](https://www.sefaria.org/Sefer_Yetzirah.1.1-2).
- **Gematria and Atbash**: Atbash hides Babel as Sheshach in [Jeremiah
  25:26](https://www.sefaria.org/Jeremiah.25.26) and 51:41, and the
  Chaldeans as Leb-kamai in 51:1, as Rashi explains each; both arts are in
  G. Scholem, *Kabbalah* (Keter, 1974).
- **Week of creation**: the seven lower sefirot in the order the counting of
  the Omer gives its days (Chesed, then Gevurah, and so on to Malkhut); laying
  them on Sunday to Shabbat is a modern convention, for which no classical
  source was found.
- **Breaking of the vessels**: G. Scholem, [*Major Trends in Jewish
  Mysticism*](https://archive.org/details/major-trends-in-jewish-mysticism-gershom-scholem-1961)
  (Schocken, 1954), seventh lecture, pp. 265–268: the vessels of the six
  sefirot below the upper three shattered, Malkhut's not quite so badly, and
  of the light caught in their fragments Luria counts 288 sparks (as does
  Hayyim Vital's *Pri Etz Chaim*). The limits: the WHO's 2021 guidelines.
- **Name-finding**: S. Alexander, *Unsong* (2015–17): Names found by chanting
  every combination in sweatshops ([ch. 1](https://unsongbook.com/chapter-1-dark-satanic-mills/))
  and by the program Llull ([ch. 4](https://unsongbook.com/chapter-4-tools-were-made-and-born-were-hands/)),
  and UNSONG, which licenses them ([ch. 2](https://unsongbook.com/chapter-2-arise-to-spiritual-strife/)).
  The Names' virtues here are new, after Unsong's (the Vital, Sentinel and
  Wakening Names, among others). Ramon Llull's combinatory art: M. Priani,
  ["Ramon Llull"](https://plato.stanford.edu/entries/llull/), Stanford
  Encyclopedia of Philosophy. The shuffled letters are the control the Bible
  code debate turned on: D. Witztum, E. Rips and Y. Rosenberg, Statistical
  Science 9(3): 429–438 (1994), doi:10.1214/ss/1177010393, against B. McKay,
  D. Bar-Natan, M. Bar-Hillel and G. Kalai, Statistical Science 14(2):
  150–173 (1999), doi:10.1214/ss/1009212243. The next Name's wait assumes the
  letters fall independently, the simplest of the chains A. A. Markov first
  counted in *Eugene Onegin* (1913). The golem woken by אמת and stilled by
  מת: G. Scholem, "The Idea of the Golem", in *On the Kabbalah and Its
  Symbolism* (Schocken, 1965).
- **Nothing is a coincidence**: Unsong's [Interlude ב, "The Code of the
  World"](https://unsongbook.com/interlude-%d7%91-the-code-of-the-world/);
  against it, P. Diaconis and F. Mosteller, "Methods for Studying
  Coincidences", Journal of the American Statistical Association 84(408):
  853–861 (1989), doi:10.1080/01621459.1989.10478847, whose law of truly large
  numbers the comparison count is there to show. The sacred numbers: 613 =
  248 + 365 commandments ([Makkot 23b](https://www.sefaria.org/Makkot.23b.18)),
  the 36 hidden righteous (Sanhedrin 97b, Sukkah 45b), the 50 gates of
  understanding (Rosh Hashanah 21b), the 13 attributes of mercy (Exodus
  34:6–7), the 72-fold Name of three verses of 72 letters (Exodus 14:19–21,
  as Rashi on Sukkah 45a counts them), and the 42-letter Name (Kiddushin 71a).
